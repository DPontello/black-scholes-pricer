"""V&V da volatilidade implícita (Sprint 5) — ver docs/VV-PLAN.md.

Oráculo primário: o próprio kernel BS (ida e volta sigma -> preço -> sigma ->
preço). A tolerância em sigma é propagada pelo condicionamento da inversão
(Δsigma ≈ Δpreço / vega, helper ``iv_sigma_abs_tol``); a do preço reavaliado
vem da cota do solver. O oráculo independente (scipy) vive em
``tests/oracle/scipy_oracle.py``.

Camadas: contrato de status (cada desfecho com teste dedicado), entradas
ilegais, ida e volta em grade determinística, rótulos do solver,
propriedades Hypothesis (ida e volta no domínio identificável; preço
arbitrário sempre vira status, nunca exceção nem NaN), casos de borda
(preço exatamente nos limites, vega ~0, tau minúsculo) e camada
*published* do golden (preço de livro -> sigma do livro).

Todas as tolerâncias vêm de ``tests/_tolerances.py`` — nenhuma inline.
"""

import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from options_engine.domain.kernel.black_scholes import bs_outputs, bs_price
from options_engine.domain.kernel.implied_vol import (
    METHOD_BISECTION,
    METHOD_CLOSED_FORM,
    METHOD_NEWTON,
    METHOD_NEWTON_BISECTION,
    METHOD_NONE,
    ImpliedVolResult,
    ImpliedVolStatus,
    implied_vol,
)
from options_engine.domain.model.errors import InvalidKernelInputError
from tests._tolerances import (
    ABS_IV_ROUNDTRIP_PRICE_FLOOR,
    ABS_IV_SIGMA,
    EPS_MACHINE,
    IV_ROUNDOFF_ULPS,
    assert_close,
    iv_sigma_abs_tol,
)

IVParams = tuple[float, float, float, float, float, float]  # s, k, tau, r, sigma, q

# Caso de referência do contrato de limites: call ITM com carry (q > 0) e a
# put espelhada — o limite inferior é o intrínseco DESCONTADO, não S - K.
_S, _K_ITM_CALL, _TAU, _R, _Q = 100.0, 90.0, 0.5, 0.05, 0.02
# Um centavo: a menor distância economicamente relevante a um limite.
_ONE_CENT = 0.01
# Parâmetro do SOLVER sob teste (não é tolerância de comparação da suíte):
# precisão de cotação de vol, 0.01 ponto.
_QUOTE_PRECISION_SIGMA_TOL = 1e-4


def _strike_at_std_moneyness(
    s: float, tau: float, r: float, sigma: float, q: float, z: float
) -> float:
    """Strike a ``z`` desvios-padrão do forward: ln(F/K) = z·sigma·sqrt(tau).

    Parametrizar a moneyness em desvios (e não em K/S) mantém a grade no
    domínio onde sigma é identificável em qualquer tau: z > 0 é call ITM.
    """
    forward = s * math.exp((r - q) * tau)
    return forward * math.exp(-z * sigma * math.sqrt(tau))


def _assert_round_trip(params: IVParams, *, is_call: bool) -> ImpliedVolResult:
    """sigma -> preço -> implied_vol -> sigma' -> preço' (mesmo kernel)."""
    s, k, tau, r, sigma, q = params
    out = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call)
    result = implied_vol(out.price, s, k, tau, r, q, is_call=is_call)
    label = f"{'call' if is_call else 'put'} {params!r} -> {result!r}"
    assert result.status is ImpliedVolStatus.CONVERGED, label
    assert result.sigma is not None, label
    scale = max(s, k)
    repriced = bs_price(s, k, tau, r, result.sigma, q, is_call=is_call)
    assert_close(
        repriced,
        out.price,
        rel=0.0,
        abs_=ABS_IV_ROUNDTRIP_PRICE_FLOOR * scale,
        label=f"preço reavaliado: {label}",
    )
    assert_close(
        result.sigma,
        sigma,
        rel=0.0,
        abs_=iv_sigma_abs_tol(IV_ROUNDOFF_ULPS * EPS_MACHINE * scale, out.vega_per_vol_unit),
        label=f"sigma recuperado: {label}",
    )
    return result


def _assert_unsolved(result: ImpliedVolResult, status: ImpliedVolStatus) -> None:
    """Status da checagem prévia: sem sigma, sem iteração, sem método."""
    assert result == ImpliedVolResult(None, status, 0, METHOD_NONE)


# ---------------------------------------------------------------------------
# 1. CONTRATO DE STATUS — cada desfecho com teste dedicado
# ---------------------------------------------------------------------------


class TestStatusExpired:
    """tau == 0: o preço é o intrínseco para qualquer sigma — não identificável."""

    @pytest.mark.parametrize("price", [0.0, 10.0, 15.0, 500.0])
    @pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
    def test_qualquer_preco_no_vencimento_e_expired(self, price: float, is_call: bool) -> None:
        # Inclui o intrínseco exato (10.0), acima dele e acima de qualquer
        # limite: o vencimento é decidido antes da checagem de limites.
        _assert_unsolved(
            implied_vol(price, 110.0, 100.0, 0.0, _R, _Q, is_call=is_call),
            ImpliedVolStatus.EXPIRED,
        )


class TestStatusBelowIntrinsic:
    """price < intrínseco descontado max(±(S·e^(-q·tau) - K·e^(-r·tau)), 0)."""

    def test_call_abaixo_do_intrinseco_descontado(self) -> None:
        lower = _S * math.exp(-_Q * _TAU) - _K_ITM_CALL * math.exp(-_R * _TAU)
        result = implied_vol(lower - _ONE_CENT, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=True)
        _assert_unsolved(result, ImpliedVolStatus.BELOW_INTRINSIC)

    def test_put_abaixo_do_intrinseco_descontado(self) -> None:
        s, k = _K_ITM_CALL, _S  # put ITM espelhada
        lower = k * math.exp(-_R * _TAU) - s * math.exp(-_Q * _TAU)
        result = implied_vol(lower - _ONE_CENT, s, k, _TAU, _R, _Q, is_call=False)
        _assert_unsolved(result, ImpliedVolStatus.BELOW_INTRINSIC)


class TestStatusAboveUpperBound:
    """price >= S·e^(-q·tau) (call) ou K·e^(-r·tau) (put): só sigma -> inf alcança."""

    @pytest.mark.parametrize("excess", [0.0, _ONE_CENT], ids=["no-limite", "acima"])
    def test_call(self, excess: float) -> None:
        upper = _S * math.exp(-_Q * _TAU)
        result = implied_vol(upper + excess, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=True)
        _assert_unsolved(result, ImpliedVolStatus.ABOVE_UPPER_BOUND)

    @pytest.mark.parametrize("excess", [0.0, _ONE_CENT], ids=["no-limite", "acima"])
    def test_put(self, excess: float) -> None:
        upper = _K_ITM_CALL * math.exp(-_R * _TAU)
        result = implied_vol(upper + excess, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=False)
        _assert_unsolved(result, ImpliedVolStatus.ABOVE_UPPER_BOUND)


class TestStatusConverged:
    def test_hull_recupera_sigma_por_newton_puro(self) -> None:
        """Caso Hull 15.6: a partir do chute MK/BS a inversão é Newton puro."""
        result = _assert_round_trip((42.0, 40.0, 0.5, 0.10, 0.20, 0.0), is_call=True)
        assert result.method == METHOD_NEWTON
        assert result.iterations >= 1

    def test_preco_no_limite_inferior_e_sigma_zero_em_forma_fechada(self) -> None:
        """O limite inferior é atingido em sigma = 0 — é solução, não ausência dela."""
        lower = bs_price(_S, _K_ITM_CALL, _TAU, _R, 0.0, _Q, is_call=True)
        result = implied_vol(lower, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=True)
        # Igualdade exata: ramo de forma fechada, sem aritmética.
        assert result == ImpliedVolResult(0.0, ImpliedVolStatus.CONVERGED, 0, METHOD_CLOSED_FORM)


class TestStatusNoConvergence:
    def test_iteracoes_esgotadas_devolvem_none_nunca_o_ultimo_iterado(self) -> None:
        """Sem convergência não há número a reportar (ROADMAP: nunca inventado)."""
        price = bs_price(100.0, 100.0, 1.0, 0.05, 0.20, is_call=True)
        result = implied_vol(price, 100.0, 100.0, 1.0, 0.05, is_call=True, max_iterations=1)
        assert result == ImpliedVolResult(None, ImpliedVolStatus.NO_CONVERGENCE, 1, METHOD_NEWTON)

    def test_tau_com_bracket_irrepresentavel_nao_itera(self) -> None:
        """tau < ~5.6e-305: sigma_max² transbordaria float64 em d1 do kernel.

        Achado de projeto: sem a guarda, o kernel avaliaria sigma² = inf e
        devolveria um preço sem significado, e o solver "convergiria" para
        lixo — o status honesto é NO_CONVERGENCE.
        """
        result = implied_vol(1.0, 100.0, 100.0, 1e-310, 0.05, is_call=True)
        _assert_unsolved(result, ImpliedVolStatus.NO_CONVERGENCE)


# ---------------------------------------------------------------------------
# 2. ENTRADAS ILEGAIS -> InvalidKernelInputError (nunca ValueError cru)
# ---------------------------------------------------------------------------


class TestIllegalInputs:
    @pytest.mark.parametrize(
        ("price", "s", "k", "tau", "r", "q"),
        [
            (-0.01, 100.0, 100.0, 1.0, 0.05, 0.0),
            (math.nan, 100.0, 100.0, 1.0, 0.05, 0.0),
            (math.inf, 100.0, 100.0, 1.0, 0.05, 0.0),
            (5.0, 0.0, 100.0, 1.0, 0.05, 0.0),
            (5.0, -1.0, 100.0, 1.0, 0.05, 0.0),
            (5.0, math.nan, 100.0, 1.0, 0.05, 0.0),
            (5.0, 100.0, 0.0, 1.0, 0.05, 0.0),
            (5.0, 100.0, -5.0, 1.0, 0.05, 0.0),
            (5.0, 100.0, 100.0, -1e-12, 0.05, 0.0),
            (5.0, 100.0, 100.0, math.nan, 0.05, 0.0),
            (5.0, 100.0, 100.0, 1.0, math.nan, 0.0),
            (5.0, 100.0, 100.0, 1.0, 0.05, math.inf),
            # Validação herdada do kernel: fator de desconto fora de exp().
            (5.0, 100.0, 100.0, 30.0, -1e7, 0.0),
        ],
    )
    @pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
    def test_entradas_de_mercado_ilegais(
        self, price: float, s: float, k: float, tau: float, r: float, q: float, is_call: bool
    ) -> None:
        with pytest.raises(InvalidKernelInputError):
            implied_vol(price, s, k, tau, r, q, is_call=is_call)

    def test_preco_ilegal_e_rejeitado_mesmo_no_vencimento(self) -> None:
        """A validação precede o atalho de tau == 0."""
        with pytest.raises(InvalidKernelInputError):
            implied_vol(-1.0, 100.0, 100.0, 0.0, 0.05, is_call=True)

    @pytest.mark.parametrize("sigma_tol", [0.0, -1e-12, math.nan, math.inf])
    def test_sigma_tol_ilegal(self, sigma_tol: float) -> None:
        with pytest.raises(InvalidKernelInputError):
            implied_vol(10.0, 100.0, 100.0, 1.0, 0.05, is_call=True, sigma_tol=sigma_tol)

    @pytest.mark.parametrize("max_iterations", [0, -3])
    def test_max_iterations_ilegal(self, max_iterations: int) -> None:
        with pytest.raises(InvalidKernelInputError):
            implied_vol(10.0, 100.0, 100.0, 1.0, 0.05, is_call=True, max_iterations=max_iterations)


# ---------------------------------------------------------------------------
# 3. IDA E VOLTA EM GRADE DETERMINÍSTICA
# ---------------------------------------------------------------------------
# ITM/ATM/OTM (z em desvios-padrão do forward), tau de 1 dia útil a 10 anos,
# r de 0 a 0.15 (CDI alto), q nulo e positivo, call e put.

_GRID: list[IVParams] = [
    (100.0, _strike_at_std_moneyness(100.0, tau, r, sigma, q, z), tau, r, sigma, q)
    for tau in (1.0 / 252.0, 0.1, 1.0, 10.0)
    for sigma in (0.05, 0.25, 0.8)
    for z in (-2.5, -1.0, 0.0, 1.0, 2.5)
    for r in (0.0, 0.05, 0.15)
    for q in (0.0, 0.04)
]


def _grid_id(params: IVParams) -> str:
    _, k, tau, r, sigma, q = params
    return f"k{k:.4g}-t{tau:.3g}-v{sigma:g}-r{r:g}-q{q:g}"


@pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
@pytest.mark.parametrize("params", _GRID, ids=_grid_id)
def test_ida_e_volta_em_grade(params: IVParams, is_call: bool) -> None:
    _assert_round_trip(params, is_call=is_call)


# ---------------------------------------------------------------------------
# 4. SOLVER — rótulos de método e parâmetros
# ---------------------------------------------------------------------------


def test_otm_profundo_usa_bissecao_como_salvaguarda() -> None:
    """Curva muito plana (vega ~1e-2): a regra da metade troca passos por bisseção."""
    result = _assert_round_trip((100.0, 150.0, 0.25, 0.05, 0.20, 0.0), is_call=True)
    assert result.method == METHOD_NEWTON_BISECTION


def test_vega_nulo_no_chute_forca_bissecao() -> None:
    """ATM-forward (ln(F/K) = 0) com valor-tempo de 1 subnormal: o chute vale 0.

    Em sigma = 0 o kernel cai no ramo determinístico com vega = 0 — o passo
    de Newton é infinito e o primeiro passo TEM de ser bisseção (sem
    ZeroDivisionError). Com uma iteração só, o rótulo registra isso.
    """
    tiniest = math.ulp(0.0)
    result = implied_vol(tiniest, 100.0, 100.0, 1.0, 0.0, is_call=True, max_iterations=1)
    assert result == ImpliedVolResult(None, ImpliedVolStatus.NO_CONVERGENCE, 1, METHOD_BISECTION)


def test_sigma_tol_frouxo_converge_em_menos_iteracoes() -> None:
    """``sigma_tol`` é contrato: |sigma - raiz| <= sigma_tol (a menos de ulps)."""
    params = (100.0, 100.0, 1.0, 0.05, 0.20, 0.0)
    s, k, tau, r, sigma, q = params
    out = bs_outputs(s, k, tau, r, sigma, q, is_call=True)
    loose_tol = _QUOTE_PRECISION_SIGMA_TOL
    loose = implied_vol(out.price, s, k, tau, r, q, is_call=True, sigma_tol=loose_tol)
    default = _assert_round_trip(params, is_call=True)
    assert loose.status is ImpliedVolStatus.CONVERGED
    assert loose.sigma is not None
    assert loose.iterations < default.iterations
    noise = iv_sigma_abs_tol(IV_ROUNDOFF_ULPS * EPS_MACHINE * s, out.vega_per_vol_unit)
    assert abs(loose.sigma - sigma) <= loose_tol + noise


# ---------------------------------------------------------------------------
# 5. PROPRIEDADES (Hypothesis)
# ---------------------------------------------------------------------------
# Domínio de identificabilidade: fora dele o valor-tempo cai abaixo do ulp do
# preço e o preço não carrega informação sobre sigma (limitações no docstring
# de implied_vol.py) — não é tolerância, é o domínio da propriedade.
_MAX_STD_MONEYNESS = 3.0  # |ln(F/K)| <= 3 desvios-padrão da vol total
_MAX_TOTAL_VOL = 3.0  # sigma·sqrt(tau) <= 3


@st.composite
def _identifiable_params(draw: st.DrawFn) -> IVParams:
    s = draw(st.floats(1.0, 5000.0))
    tau = draw(st.floats(1.0 / 252.0, 30.0))
    sigma = draw(st.floats(0.01, min(2.0, _MAX_TOTAL_VOL / math.sqrt(tau))))
    z = draw(st.floats(-_MAX_STD_MONEYNESS, _MAX_STD_MONEYNESS))
    r = draw(st.floats(-0.05, 0.20))  # inclui r negativo e CDI alto
    q = draw(st.one_of(st.just(0.0), st.floats(0.0, 0.12)))
    return s, _strike_at_std_moneyness(s, tau, r, sigma, q, z), tau, r, sigma, q


def _regime(z: float, tau: float, r: float, sigma: float, q: float) -> IVParams:
    return 100.0, _strike_at_std_moneyness(100.0, tau, r, sigma, q, z), tau, r, sigma, q


# Regimes nomeados, sempre exercitados além do sorteio (corpus explícito):
# ATM curto com r alto, ITM longo com carry, OTM curto, OTM longo com carry.
_NAMED_REGIMES = [
    _regime(0.0, 1.0 / 252.0, 0.15, 0.30, 0.0),
    _regime(2.0, 30.0, 0.15, 0.25, 0.04),
    _regime(-2.5, 1.0 / 252.0, 0.05, 0.50, 0.0),
    _regime(-2.0, 10.0, 0.15, 0.40, 0.04),
]

_RoundTripTest = Callable[[IVParams, bool], None]


def _with_named_regimes(test: _RoundTripTest) -> _RoundTripTest:
    """Aplica ``@example`` para cada regime nomeado, em call e put."""
    for params in _NAMED_REGIMES:
        for is_call in (True, False):
            test = example(params=params, is_call=is_call)(test)
    return test


@_with_named_regimes
@given(params=_identifiable_params(), is_call=st.booleans())
def test_ida_e_volta_hypothesis(params: IVParams, is_call: bool) -> None:
    _assert_round_trip(params, is_call=is_call)


@given(params=_identifiable_params(), is_call=st.booleans(), fraction=st.floats(0.0, 1.5))
def test_qualquer_preco_vira_status_nunca_excecao_nem_nan(
    params: IVParams, is_call: bool, fraction: float
) -> None:
    """Preço arbitrário em [0, 1.5·limite superior]: o status segue os limites.

    Critério de aceite da Sprint 5: fora dos limites -> status próprio, sem
    exceção e sem NaN; dentro -> CONVERGED e o preço é reproduzido.
    """
    s, k, tau, r, _, q = params
    upper = s * math.exp(-q * tau) if is_call else k * math.exp(-r * tau)
    lower = bs_price(s, k, tau, r, 0.0, q, is_call=is_call)
    price = fraction * upper
    result = implied_vol(price, s, k, tau, r, q, is_call=is_call)
    if price < lower:
        _assert_unsolved(result, ImpliedVolStatus.BELOW_INTRINSIC)
    elif price >= upper:
        _assert_unsolved(result, ImpliedVolStatus.ABOVE_UPPER_BOUND)
    else:
        assert result.status is ImpliedVolStatus.CONVERGED, result
        assert result.sigma is not None
        assert math.isfinite(result.sigma)
        assert result.sigma >= 0.0
        repriced = bs_price(s, k, tau, r, result.sigma, q, is_call=is_call)
        assert_close(
            repriced,
            price,
            rel=0.0,
            abs_=ABS_IV_ROUNDTRIP_PRICE_FLOOR * max(s, k),
            label=f"preço reavaliado: {params!r} is_call={is_call} -> {result!r}",
        )


# ---------------------------------------------------------------------------
# 6. CASOS DE BORDA
# ---------------------------------------------------------------------------


def _assert_converged_and_repriced(
    price: float, s: float, k: float, tau: float, r: float, q: float, *, is_call: bool
) -> ImpliedVolResult:
    """CONVERGED e o preço de entrada é reproduzido (sem sigma de referência)."""
    result = implied_vol(price, s, k, tau, r, q, is_call=is_call)
    assert result.status is ImpliedVolStatus.CONVERGED, result
    assert result.sigma is not None
    repriced = bs_price(s, k, tau, r, result.sigma, q, is_call=is_call)
    assert_close(
        repriced,
        price,
        rel=0.0,
        abs_=ABS_IV_ROUNDTRIP_PRICE_FLOOR * max(s, k),
        label=f"preço reavaliado -> {result!r}",
    )
    return result


class TestPriceExactlyAtBounds:
    """Preço exatamente no intrínseco, a 1 ulp dos limites e entre os dois intrínsecos."""

    @pytest.mark.parametrize(
        ("s", "k", "is_call"),
        [
            (_S, _K_ITM_CALL, True),  # call ITM: limite = S·e^(-q·tau) - K·e^(-r·tau)
            (_K_ITM_CALL, _S, False),  # put ITM: limite = K·e^(-r·tau) - S·e^(-q·tau)
            (_K_ITM_CALL, _S, True),  # call OTM: limite = 0, preço 0.0
            (_S, _K_ITM_CALL, False),  # put OTM: limite = 0, preço 0.0
        ],
        ids=["call-itm", "put-itm", "call-otm-zero", "put-otm-zero"],
    )
    def test_preco_no_intrinseco_descontado_e_sigma_zero(
        self, s: float, k: float, is_call: bool
    ) -> None:
        lower = bs_price(s, k, _TAU, _R, 0.0, _Q, is_call=is_call)
        result = implied_vol(lower, s, k, _TAU, _R, _Q, is_call=is_call)
        # Igualdade exata: forma fechada, e o caminho de reprecificação é o
        # mesmo ramo sigma = 0 do kernel que produziu o limite.
        assert result == ImpliedVolResult(0.0, ImpliedVolStatus.CONVERGED, 0, METHOD_CLOSED_FORM)
        assert bs_price(s, k, _TAU, _R, 0.0, _Q, is_call=is_call) == lower

    def test_put_no_intrinseco_nao_descontado_tem_solucao(self) -> None:
        """K - S > K·e^(-r·tau) - S com r > 0: cotação típica de put ITM é solúvel.

        Prova de que BELOW_INTRINSIC usa o intrínseco DESCONTADO: o
        intrínseco cru de uma put europeia ITM fica ACIMA do limite inferior.
        """
        s, k = 100.0, 150.0
        result = _assert_converged_and_repriced(k - s, s, k, 1.0, 0.15, 0.0, is_call=False)
        assert result.sigma is not None
        assert result.sigma > 0.0

    def test_call_entre_os_dois_intrinsecos_tem_solucao(self) -> None:
        """Com carry q > 0, S·e^(-q·tau) - K·e^(-r·tau) < S - K: o meio é solúvel."""
        s, k, tau, r, q = 100.0, 50.0, 1.0, 0.0, 0.10
        lower = s * math.exp(-q * tau) - k * math.exp(-r * tau)
        price = 0.5 * (lower + (s - k))
        _assert_converged_and_repriced(price, s, k, tau, r, q, is_call=True)

    def test_um_ulp_acima_do_limite_inferior_converge(self) -> None:
        """Valor-tempo de 1 ulp: sigma minúsculo, Newton + bisseção, preço reproduzido."""
        lower = bs_price(_S, _K_ITM_CALL, _TAU, _R, 0.0, _Q, is_call=True)
        price = math.nextafter(lower, math.inf)
        _assert_converged_and_repriced(price, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=True)

    def test_um_ulp_abaixo_do_limite_inferior_e_below_intrinsic(self) -> None:
        """Comparação sem folga: 1 ulp abaixo já não tem solução."""
        lower = bs_price(_S, _K_ITM_CALL, _TAU, _R, 0.0, _Q, is_call=True)
        price = math.nextafter(lower, 0.0)
        result = implied_vol(price, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=True)
        _assert_unsolved(result, ImpliedVolStatus.BELOW_INTRINSIC)

    @pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
    def test_um_ulp_abaixo_do_limite_superior_converge(self, is_call: bool) -> None:
        """sigma enorme, mas finito e dentro do bracket — o preço é reproduzido."""
        upper = _S * math.exp(-_Q * _TAU) if is_call else _K_ITM_CALL * math.exp(-_R * _TAU)
        price = math.nextafter(upper, 0.0)
        result = _assert_converged_and_repriced(
            price, _S, _K_ITM_CALL, _TAU, _R, _Q, is_call=is_call
        )
        assert result.sigma is not None
        assert math.isfinite(result.sigma)


class TestVegaNearZero:
    """vega -> 0: Newton perde a alavanca e as salvaguardas assumem."""

    @pytest.mark.parametrize(
        ("k", "is_call"),
        [(200.0, True), (300.0, True), (500.0, True), (30.0, False), (50.0, False)],
        ids=["call-k200", "call-k300", "call-k500", "put-k30", "put-k50"],
    )
    def test_otm_profundo_recupera_sigma(self, k: float, is_call: bool) -> None:
        """Preço ~1e-11 a ~1e-57 e vega ~1e-9 a ~1e-54 (medidos).

        Na cauda OTM o ruído do preço é RELATIVO ao próprio preço — o kernel
        avalia N(x) por erfc, que preserva precisão relativa até ~1e-300
        (distributions.py) —, e vega/preço é moderado (~|d|/sigma). Logo sigma
        fica determinado muito abaixo da cota do solver: a tolerância é a
        própria ``ABS_IV_SIGMA``, sem o termo de escala de ``iv_sigma_abs_tol``
        (que seria vácuo aqui: escala/vega ~1e56). Medido: |Δsigma| <= 6e-15.
        """
        s, tau, r, sigma = 100.0, 0.25, 0.05, 0.20
        price = bs_price(s, k, tau, r, sigma, is_call=is_call)
        result = implied_vol(price, s, k, tau, r, is_call=is_call)
        assert result.status is ImpliedVolStatus.CONVERGED, result
        assert result.sigma is not None
        assert_close(result.sigma, sigma, rel=0.0, abs_=ABS_IV_SIGMA, label=f"k={k}")

    @pytest.mark.parametrize(
        ("k", "is_call"), [(50.0, True), (150.0, False)], ids=["call-k50", "put-k150"]
    )
    def test_itm_profundo_ida_e_volta(self, k: float, is_call: bool) -> None:
        """ITM profundo: o ruído é da ESCALA (preço ~ intrínseco) e o vega cai
        (~5e-5 na call K=50) — a tolerância em sigma cresce como escala/vega,
        pelo helper."""
        _assert_round_trip((100.0, k, 0.5, 0.05, 0.20, 0.0), is_call=is_call)

    def test_vega_nulo_ate_a_convergencia(self) -> None:
        """Chute em sigma = 0 (vega == 0) e raiz ~1e-325: converge sem exceção.

        Complementa ``test_vega_nulo_no_chute_forca_bissecao``: com o orçamento
        default, a bisseção sai do ramo de vega nulo e Newton termina; a raiz
        está abaixo do menor subnormal, então sigma fica dentro da cota do
        solver em torno de 0.
        """
        tiniest = math.ulp(0.0)
        result = implied_vol(tiniest, 100.0, 100.0, 1.0, 0.0, is_call=True)
        assert result.status is ImpliedVolStatus.CONVERGED, result
        assert result.method == METHOD_NEWTON_BISECTION
        assert result.sigma is not None
        assert_close(result.sigma, 0.0, rel=0.0, abs_=ABS_IV_SIGMA, label="raiz ~0")


class TestTinyTau:
    @pytest.mark.parametrize("k", [100.0, 100.0001], ids=["atm", "otm-0.5desvio"])
    @pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
    def test_tau_1e_10_ida_e_volta(self, k: float, is_call: bool) -> None:
        """tau = 1e-10 (tabela de fronteiras): vega ~4e-4, preço ~1e-5."""
        _assert_round_trip((100.0, k, 1e-10, 0.05, 0.20, 0.0), is_call=is_call)

    def test_preco_em_underflow_cai_no_limite_inferior(self) -> None:
        """tau = 1e-250: o valor-tempo ATM (~1e-124) se perde no cancelamento.

        O kernel devolve preço 0.0 == limite inferior — sem informação sobre
        sigma, a resposta coerente é sigma = 0 em forma fechada, que
        reprecifica exatamente.
        """
        price = bs_price(100.0, 100.0, 1e-250, 0.05, 0.20, is_call=True)
        result = implied_vol(price, 100.0, 100.0, 1e-250, 0.05, is_call=True)
        assert result == ImpliedVolResult(0.0, ImpliedVolStatus.CONVERGED, 0, METHOD_CLOSED_FORM)
        assert bs_price(100.0, 100.0, 1e-250, 0.05, 0.0, is_call=True) == price

    def test_logo_acima_da_guarda_de_representabilidade_ainda_itera(self) -> None:
        """tau = 6e-305 (sigma_max ~1.3e154, quadrado ainda finito): resolve."""
        result = _assert_converged_and_repriced(1.0, 100.0, 100.0, 6e-305, 0.05, 0.0, is_call=True)
        assert result.iterations >= 1


# ---------------------------------------------------------------------------
# 7. GOLDEN — camada *published*: preço de livro -> sigma do livro
# ---------------------------------------------------------------------------
# O preço publicado é arredondado (abs_tol da fonte); invertê-lo propaga esse
# arredondamento por 1/vega — a tolerância em sigma é abs_tol / vega, pelo
# mesmo helper do condicionamento.

_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "data" / "golden" / "bs_european.json"
_GOLDEN: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
_PUBLISHED_PRICES: list[tuple[str, dict[str, float], bool, float, float]] = [
    (case["label"], case["inputs"], field == "call", float(value), float(published["abs_tol"]))
    for case in _GOLDEN["cases"]
    if (published := case.get("published")) is not None
    for field, value in published["values"].items()
    if field in ("call", "put")
]


@pytest.mark.parametrize(
    ("label", "inputs", "is_call", "published_price", "abs_tol"),
    _PUBLISHED_PRICES,
    ids=[f"{p[0]}-{'call' if p[2] else 'put'}" for p in _PUBLISHED_PRICES],
)
def test_preco_publicado_recupera_sigma_do_livro(
    label: str, inputs: dict[str, float], is_call: bool, published_price: float, abs_tol: float
) -> None:
    s, k, tau, r, sigma, q = (inputs[f] for f in ("s", "k", "tau", "r", "sigma", "q"))
    result = implied_vol(published_price, s, k, tau, r, q, is_call=is_call)
    assert result.status is ImpliedVolStatus.CONVERGED, result
    assert result.sigma is not None
    vega = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).vega_per_vol_unit
    assert_close(
        result.sigma,
        sigma,
        rel=0.0,
        abs_=iv_sigma_abs_tol(abs_tol, vega),
        label=f"{label} ({'call' if is_call else 'put'})",
    )

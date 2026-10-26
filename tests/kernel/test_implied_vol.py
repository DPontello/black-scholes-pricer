"""V&V da volatilidade implícita (Sprint 5) — ver docs/VV-PLAN.md.

Oráculo primário: o próprio kernel BS (ida e volta sigma -> preço -> sigma ->
preço). A tolerância em sigma é propagada pelo condicionamento da inversão
(Δsigma ≈ Δpreço / vega, helper ``iv_sigma_abs_tol``); a do preço reavaliado
vem da cota do solver. O oráculo independente (scipy) vive em
``tests/oracle/scipy_oracle.py``.

Camadas: contrato de status (cada desfecho com teste dedicado), entradas
ilegais, ida e volta em grade determinística e rótulos do solver.

Todas as tolerâncias vêm de ``tests/_tolerances.py`` — nenhuma inline.
"""

import math

import pytest

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

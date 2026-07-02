"""V&V do kernel Black-Scholes (Sprint 1) — ver docs/VV-PLAN.md.

Quatro camadas, cada uma com um oráculo distinto:
  1. Golden-master  — camada "verified" (script stdlib independente, rel 1e-12)
                      e camada "published" (livro-texto, abs_tol da fonte).
  2. Property-based — invariantes de não-arbitragem e de forma (Hypothesis).
  3. Fronteiras     — contrato normativo de tau=0 / sigma=0 / entradas ilegais.
  4. Diferenças finitas — gregas analíticas vs derivadas numéricas com
                      h = eps^(1/3)·escala (ótimo medido nesta máquina).

Todas as tolerâncias vêm de ``tests/_tolerances.py`` — nenhuma inline.
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.kernel.black_scholes import bs_outputs, bs_price, d1_d2
from options_engine.domain.kernel.distributions import norm_cdf
from options_engine.domain.model.errors import InvalidKernelInputError
from tests._tolerances import (
    ABS_MATH_IDENTITY_FLOOR,
    ABS_NEAR_EXPIRY_INTRINSIC,
    ABS_REGRESSION_FLOOR,
    ABS_SELF_FLOOR,
    ABS_SIGMA_CONTINUITY_PER_SPOT,
    FD_STEP,
    INEQ_SLACK,
    REL_FD,
    REL_MATH_IDENTITY,
    REL_REGRESSION,
    REL_SELF,
    assert_close,
    fd_abs_tol,
)

# ---------------------------------------------------------------------------
# 1. GOLDEN-MASTER
# ---------------------------------------------------------------------------

_GOLDEN_PATH = Path(__file__).resolve().parents[1] / "data" / "golden" / "bs_european.json"
_GOLDEN: dict[str, Any] = json.loads(_GOLDEN_PATH.read_text(encoding="utf-8"))
GOLDEN_CASES: list[dict[str, Any]] = _GOLDEN["cases"]
_IDS = [str(c["label"]) for c in GOLDEN_CASES]


def _all_outputs(inputs: dict[str, float]) -> dict[str, float]:
    call = bs_outputs(
        inputs["s"],
        inputs["k"],
        inputs["tau"],
        inputs["r"],
        inputs["sigma"],
        inputs["q"],
        is_call=True,
    )
    put = bs_outputs(
        inputs["s"],
        inputs["k"],
        inputs["tau"],
        inputs["r"],
        inputs["sigma"],
        inputs["q"],
        is_call=False,
    )
    return {
        "call": call.price,
        "put": put.price,
        "delta_call": call.delta,
        "delta_put": put.delta,
        "gamma": call.gamma,
        "vega": call.vega_per_vol_unit,
        "theta_call": call.theta_per_year,
        "theta_put": put.theta_per_year,
        "rho_call": call.rho,
        "rho_put": put.rho,
    }


@pytest.mark.parametrize("case", GOLDEN_CASES, ids=_IDS)
def test_golden_verified_full_precision(case: dict[str, Any]) -> None:
    """Kernel vs implementação independente (erf, não erfc) em full precision."""
    inputs: dict[str, float] = case["inputs"]
    actual = _all_outputs(inputs)
    scale = max(inputs["s"], inputs["k"])
    for field, expected in case["verified"].items():
        assert_close(
            actual[field],
            float(expected),
            rel=REL_REGRESSION,
            abs_=ABS_REGRESSION_FLOOR * scale,
            label=f"{case['label']}:{field}",
        )


@pytest.mark.parametrize(
    "case",
    [c for c in GOLDEN_CASES if "published" in c],
    ids=[str(c["label"]) for c in GOLDEN_CASES if "published" in c],
)
def test_golden_published_textbook(case: dict[str, Any]) -> None:
    """Kernel vs valores publicados, com abs_tol = metade da última casa da fonte."""
    actual = _all_outputs(case["inputs"])
    published: dict[str, Any] = case["published"]
    for field, expected in published["values"].items():
        assert_close(
            actual[field],
            float(expected),
            rel=0.0,
            abs_=float(published["abs_tol"]),
            label=f"{case['label']}:{field} ({published['source']})",
        )


def test_d1_d2_atm_canonico() -> None:
    """Sanidade de d1/d2: caso ATM canônico tem d1 = 0.35, d2 = 0.15."""
    d1, d2 = d1_d2(100.0, 100.0, 1.0, 0.05, 0.20)
    assert_close(d1, 0.35, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="d1")
    assert_close(d2, 0.15, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="d2")


def test_d1_d2_consistent_with_bs_outputs_with_carry() -> None:
    """d1_d2 público e bs_outputs devem derivar do MESMO d1 — com q != 0.

    Achado da revisão adversarial: com a fórmula duplicada, um erro de sinal
    em q apenas na API pública sobreviveria à suíte inteira (mutante
    executado e sobrevivente antes desta correção). A fórmula agora tem fonte
    única no kernel; este teste garante que a duplicação não retorne.
    """
    s, k, tau, r, sigma, q = 100.0, 90.0, 0.75, 0.03, 0.25, 0.04
    d1, d2 = d1_d2(s, k, tau, r, sigma, q)
    out = bs_outputs(s, k, tau, r, sigma, q, is_call=True)
    df_q, df_r = math.exp(-q * tau), math.exp(-r * tau)
    assert_close(out.delta, df_q * norm_cdf(d1), rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="delta")
    reconstructed = s * df_q * norm_cdf(d1) - k * df_r * norm_cdf(d2)
    assert_close(out.price, reconstructed, rel=REL_SELF, abs_=ABS_SELF_FLOOR * s, label="preço")


# ---------------------------------------------------------------------------
# 2. PROPERTY-BASED (Hypothesis)
# ---------------------------------------------------------------------------

BSParams = tuple[float, float, float, float, float, float]


@st.composite
def _bs_params(draw: st.DrawFn) -> BSParams:
    s = draw(st.floats(1.0, 5000.0))
    log_moneyness = draw(st.floats(-2.5, 2.5))
    k = s * math.exp(log_moneyness)
    tau = draw(st.floats(1.0 / 252.0, 30.0))
    r = draw(st.floats(-0.05, 0.5))  # taxa negativa incluída de propósito
    sigma = draw(st.floats(1e-3, 3.0))
    q = draw(st.floats(0.0, 0.12))
    return s, k, tau, r, sigma, q


@st.composite
def _bs_params_r_nonneg_q_zero(draw: st.DrawFn) -> BSParams:
    """Domínio restrito para propriedades que EXIGEM q = 0 e r >= 0 (ver testes)."""
    s = draw(st.floats(1.0, 5000.0))
    log_moneyness = draw(st.floats(-2.5, 2.5))
    k = s * math.exp(log_moneyness)
    tau = draw(st.floats(1.0 / 252.0, 30.0))
    r = draw(st.floats(0.0, 0.5))
    sigma = draw(st.floats(1e-3, 3.0))
    return s, k, tau, r, sigma, 0.0


@given(_bs_params())
def test_put_call_parity(params: BSParams) -> None:
    """C - P = S·e^(-q·tau) - K·e^(-r·tau) — se falhar em 1e-12, o bug é estrutural."""
    s, k, tau, r, sigma, q = params
    c = bs_price(s, k, tau, r, sigma, q, is_call=True)
    p = bs_price(s, k, tau, r, sigma, q, is_call=False)
    rhs = s * math.exp(-q * tau) - k * math.exp(-r * tau)
    assert_close(c - p, rhs, rel=REL_SELF, abs_=ABS_SELF_FLOOR * max(s, k), label="paridade")


@given(_bs_params())
def test_price_bounds_no_arbitrage(params: BSParams) -> None:
    s, k, tau, r, sigma, q = params
    c = bs_price(s, k, tau, r, sigma, q, is_call=True)
    p = bs_price(s, k, tau, r, sigma, q, is_call=False)
    fwd_s = s * math.exp(-q * tau)
    disc_k = k * math.exp(-r * tau)
    slack = INEQ_SLACK * max(s, k)
    assert max(fwd_s - disc_k, 0.0) - slack <= c <= fwd_s + slack
    assert max(disc_k - fwd_s, 0.0) - slack <= p <= disc_k + slack


@given(_bs_params())
def test_monotonic_in_spot(params: BSParams) -> None:
    s, k, tau, r, sigma, q = params
    slack = INEQ_SLACK * max(s, k)
    c_lo = bs_price(s, k, tau, r, sigma, q, is_call=True)
    c_hi = bs_price(s * 1.01, k, tau, r, sigma, q, is_call=True)
    p_lo = bs_price(s, k, tau, r, sigma, q, is_call=False)
    p_hi = bs_price(s * 1.01, k, tau, r, sigma, q, is_call=False)
    assert c_hi >= c_lo - slack  # call cresce com o spot
    assert p_hi <= p_lo + slack  # put decresce com o spot


@given(_bs_params())
def test_monotonic_in_vol(params: BSParams) -> None:
    """Vega >= 0 para call E put: mais vol nunca reduz o valor da opção."""
    s, k, tau, r, sigma, q = params
    slack = INEQ_SLACK * max(s, k)
    for is_call in (True, False):
        lo = bs_price(s, k, tau, r, sigma, q, is_call=is_call)
        hi = bs_price(s, k, tau, r, sigma * 1.1, q, is_call=is_call)
        assert hi >= lo - slack


@given(_bs_params_r_nonneg_q_zero())
def test_call_monotonic_in_tau_and_theta_sign(params: BSParams) -> None:
    """Monotonia em tau vale APENAS para call europeia com q = 0 e r >= 0.

    Conhecimento de negócio codificado (VV-PLAN): para a put NÃO vale (deep
    ITM perde valor com tau maior, pelo desconto do strike); com r < 0 a
    call deep ITM sofre o mesmo mecanismo. Escrever a propriedade "óbvia"
    fora deste domínio seria um falso negativo do próprio plano. No mesmo
    domínio restrito, theta da call é <= 0.
    """
    s, k, tau, r, sigma, q = params
    slack = INEQ_SLACK * max(s, k)
    shorter = bs_price(s, k, tau, r, sigma, q, is_call=True)
    longer = bs_price(s, k, tau * 1.5, r, sigma, q, is_call=True)
    assert longer >= shorter - slack
    out = bs_outputs(s, k, tau, r, sigma, q, is_call=True)
    assert out.theta_per_year <= slack


@given(_bs_params())
def test_delta_bounds_and_delta_parity(params: BSParams) -> None:
    s, k, tau, r, sigma, q = params
    call = bs_outputs(s, k, tau, r, sigma, q, is_call=True)
    put = bs_outputs(s, k, tau, r, sigma, q, is_call=False)
    df_q = math.exp(-q * tau)
    assert -INEQ_SLACK <= call.delta <= df_q + INEQ_SLACK
    assert -df_q - INEQ_SLACK <= put.delta <= INEQ_SLACK
    assert_close(
        call.delta - put.delta, df_q, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="paridade de delta"
    )


@given(_bs_params())
def test_gamma_vega_nonneg_and_identical_call_put(params: BSParams) -> None:
    s, k, tau, r, sigma, q = params
    call = bs_outputs(s, k, tau, r, sigma, q, is_call=True)
    put = bs_outputs(s, k, tau, r, sigma, q, is_call=False)
    assert call.gamma >= 0.0
    assert call.vega_per_vol_unit >= 0.0
    # Igualdade EXATA permitida: mesma expressão, mesmos intermediários, mesmo
    # caminho aritmético (exceção documentada da política de tolerância).
    # Se um refactor separar os caminhos call/put, este teste força a revisão.
    assert call.gamma == put.gamma
    assert call.vega_per_vol_unit == put.vega_per_vol_unit


@given(_bs_params(), st.floats(0.1, 10.0))
def test_homogeneity_degree_one(params: BSParams, lam: float) -> None:
    """BS(λs, λk, ·) = λ·BS(s, k, ·) — pega erro de escala silencioso."""
    s, k, tau, r, sigma, q = params
    for is_call in (True, False):
        left = bs_price(lam * s, lam * k, tau, r, sigma, q, is_call=is_call)
        right = lam * bs_price(s, k, tau, r, sigma, q, is_call=is_call)
        assert_close(
            left,
            right,
            rel=REL_MATH_IDENTITY,
            abs_=ABS_MATH_IDENTITY_FLOOR * lam * max(s, k),
            label=f"homogeneidade is_call={is_call}",
        )


@given(_bs_params())
def test_convexity_in_strike(params: BSParams) -> None:
    """Butterfly C(k-Δ) - 2C(k) + C(k+Δ) >= 0 — convexidade / não-arbitragem."""
    s, k, tau, r, sigma, q = params
    dk = 0.05 * k
    c_lo = bs_price(s, k - dk, tau, r, sigma, q, is_call=True)
    c_mid = bs_price(s, k, tau, r, sigma, q, is_call=True)
    c_hi = bs_price(s, k + dk, tau, r, sigma, q, is_call=True)
    assert c_lo - 2.0 * c_mid + c_hi >= -INEQ_SLACK * max(s, k)


@given(_bs_params())
def test_all_outputs_finite(params: BSParams) -> None:
    s, k, tau, r, sigma, q = params
    for is_call in (True, False):
        out = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call)
        for name, value in zip(out._fields, out, strict=True):
            assert math.isfinite(value), f"{name} não-finito: {value!r}"


# ---------------------------------------------------------------------------
# 3. FRONTEIRAS (contrato normativo — docs/ARCHITECTURE.md)
# ---------------------------------------------------------------------------


class TestExpiredTauZero:
    """tau == 0: intrínseco exato, delta degrau, demais gregas 0 por convenção.

    Igualdade exata permitida: ramo em forma fechada com aritmética trivial.
    """

    def test_call_itm(self) -> None:
        out = bs_outputs(110.0, 100.0, 0.0, 0.05, 0.20, is_call=True)
        assert out.price == 10.0
        assert out.delta == 1.0
        assert (out.gamma, out.theta_per_year, out.vega_per_vol_unit, out.rho) == (0, 0, 0, 0)

    def test_call_otm_and_atm(self) -> None:
        assert bs_outputs(90.0, 100.0, 0.0, 0.05, 0.20, is_call=True).price == 0.0
        assert bs_outputs(90.0, 100.0, 0.0, 0.05, 0.20, is_call=True).delta == 0.0
        atm = bs_outputs(100.0, 100.0, 0.0, 0.05, 0.20, is_call=True)
        assert atm.price == 0.0
        assert atm.delta == 0.5  # convenção documentada no kernel

    def test_put_mirror(self) -> None:
        itm = bs_outputs(90.0, 100.0, 0.0, 0.05, 0.20, is_call=False)
        assert itm.price == 10.0
        assert itm.delta == -1.0
        atm = bs_outputs(100.0, 100.0, 0.0, 0.05, 0.20, is_call=False)
        assert atm.delta == -0.5

    def test_tau_zero_with_sigma_zero_is_expired(self) -> None:
        """tau = 0 e sigma = 0 simultâneos: prevalece o ramo de vencimento."""
        out = bs_outputs(110.0, 100.0, 0.0, 0.05, 0.0, is_call=True)
        assert out.price == 10.0
        assert out.delta == 1.0

    @pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
    def test_near_expiry_finite_and_converges_to_intrinsic(self, is_call: bool) -> None:
        """tau = 1e-10: nada explode em NaN/inf e o preço colapsa no intrínseco."""
        for s in (110.0, 100.0, 90.0):
            intrinsic = max(s - 100.0, 0.0) if is_call else max(100.0 - s, 0.0)
            out = bs_outputs(s, 100.0, 1e-10, 0.05, 0.20, is_call=is_call)
            for name, value in zip(out._fields, out, strict=True):
                assert math.isfinite(value), f"{name} não-finito em tau=1e-10"
            assert_close(
                out.price, intrinsic, rel=0.0, abs_=ABS_NEAR_EXPIRY_INTRINSIC, label=f"s={s}"
            )


class TestSigmaZero:
    """sigma == 0: ativo determinístico — intrínseco descontado sobre o forward."""

    def test_call_itm_closed_form(self) -> None:
        s, k, tau, r, q = 110.0, 100.0, 0.5, 0.05, 0.02
        out = bs_outputs(s, k, tau, r, 0.0, q, is_call=True)
        df_r, df_q = math.exp(-r * tau), math.exp(-q * tau)
        assert_close(
            out.price, s * df_q - k * df_r, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="preço"
        )
        assert_close(out.delta, df_q, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="delta")
        assert out.gamma == 0.0
        assert out.vega_per_vol_unit == 0.0
        assert_close(
            out.theta_per_year,
            q * s * df_q - r * k * df_r,
            rel=REL_SELF,
            abs_=ABS_SELF_FLOOR,
            label="theta",
        )
        assert_close(out.rho, k * tau * df_r, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="rho")

    def test_call_otm_is_worthless(self) -> None:
        out = bs_outputs(90.0, 100.0, 0.5, 0.05, 0.0, is_call=True)
        assert out == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    def test_put_itm_closed_form(self) -> None:
        s, k, tau, r, q = 90.0, 100.0, 0.5, 0.05, 0.02
        out = bs_outputs(s, k, tau, r, 0.0, q, is_call=False)
        df_r, df_q = math.exp(-r * tau), math.exp(-q * tau)
        assert_close(
            out.price, k * df_r - s * df_q, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="preço"
        )
        assert_close(out.delta, -df_q, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="delta")

    def test_forward_equals_strike_delta_convention(self) -> None:
        """forward == k exato (r == q, s == k): delta = ±0.5·df_q por convenção.

        Ponto cego apontado pela revisão adversarial — o ramo ternário não
        era exercitado por nenhum teste (e coverage.py não conta ternários
        como branch).
        """
        s, k, tau, rq = 100.0, 100.0, 0.5, 0.03
        df_q = math.exp(-rq * tau)
        call = bs_outputs(s, k, tau, rq, 0.0, rq, is_call=True)
        put = bs_outputs(s, k, tau, rq, 0.0, rq, is_call=False)
        assert call.price == 0.0
        assert put.price == 0.0
        assert_close(call.delta, 0.5 * df_q, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="delta call")
        assert_close(put.delta, -0.5 * df_q, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="delta put")

    def test_sig_sqrt_tau_underflow_falls_back_to_deterministic_limit(self) -> None:
        """sigma > 0 e tau > 0 com sigma·sqrt(tau) em underflow para 0.0.

        Achado da revisão adversarial: antes da correção, tau = 1e-250
        estourava ``ZeroDivisionError`` cru pela fronteira do domínio. Sem
        difusão representável, o limite correto é o determinístico.
        """
        out = bs_outputs(100.0, 90.0, 1e-250, 0.05, 1e-250, is_call=True)
        for value in out:
            assert math.isfinite(value)
        assert_close(out.price, 10.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR * 100.0, label="preço")
        assert out.delta == 1.0  # df_q = 1.0 nesse regime (q = 0)

    @pytest.mark.parametrize("s", [90.0, 110.0])
    @pytest.mark.parametrize("is_call", [True, False])
    def test_continuity_with_tiny_sigma(self, s: float, is_call: bool) -> None:
        """O ramo sigma=0 é o limite contínuo da fórmula (sigma=1e-8)."""
        exact = bs_outputs(s, 100.0, 0.5, 0.05, 0.0, 0.02, is_call=is_call)
        near = bs_outputs(s, 100.0, 0.5, 0.05, 1e-8, 0.02, is_call=is_call)
        for name, e_val, n_val in zip(exact._fields, exact, near, strict=True):
            assert_close(
                n_val,
                e_val,
                rel=REL_SELF,
                abs_=ABS_SIGMA_CONTINUITY_PER_SPOT * s,
                label=f"continuidade:{name}",
            )


class TestIllegalInputs:
    """Entradas ilegais -> InvalidKernelInputError (filha de DomainError), nunca ValueError cru."""

    @pytest.mark.parametrize(
        ("s", "k", "tau", "r", "sigma", "q"),
        [
            (0.0, 100.0, 1.0, 0.05, 0.2, 0.0),
            (-1.0, 100.0, 1.0, 0.05, 0.2, 0.0),
            (math.nan, 100.0, 1.0, 0.05, 0.2, 0.0),
            (100.0, 0.0, 1.0, 0.05, 0.2, 0.0),
            (100.0, -5.0, 1.0, 0.05, 0.2, 0.0),
            (100.0, 100.0, -1e-12, 0.05, 0.2, 0.0),
            (100.0, 100.0, 1.0, 0.05, -0.1, 0.0),
            (100.0, 100.0, 1.0, 0.05, math.nan, 0.0),
            (100.0, 100.0, 1.0, math.nan, 0.2, 0.0),
            (100.0, 100.0, 1.0, math.inf, 0.2, 0.0),
            (100.0, 100.0, 1.0, 0.05, 0.2, math.nan),
            (math.inf, 100.0, 1.0, 0.05, 0.2, 0.0),
            (100.0, 100.0, math.inf, 0.05, 0.2, 0.0),
            (100.0, 100.0, 1.0, 0.05, math.inf, 0.0),
            # Achado da revisão adversarial: fator de desconto fora da faixa
            # de exp() estourava OverflowError cru (|r|·tau >= 700).
            (100.0, 90.0, 30.0, -1e7, 0.2, 0.0),
            (100.0, 90.0, 30.0, 0.05, 0.2, 30.0),
        ],
    )
    def test_raises_typed_domain_error(
        self, s: float, k: float, tau: float, r: float, sigma: float, q: float
    ) -> None:
        with pytest.raises(InvalidKernelInputError):
            bs_outputs(s, k, tau, r, sigma, q, is_call=True)

    def test_d1_d2_requires_positive_sig_sqrt_tau(self) -> None:
        with pytest.raises(InvalidKernelInputError):
            d1_d2(100.0, 100.0, 0.0, 0.05, 0.2)
        with pytest.raises(InvalidKernelInputError):
            d1_d2(100.0, 100.0, 1.0, 0.05, 0.0)
        with pytest.raises(InvalidKernelInputError):  # underflow do produto
            d1_d2(100.0, 90.0, 1e-250, 0.05, 1e-250)


def test_negative_rate_is_legal_and_parity_holds() -> None:
    """CDI não é negativo, mas o kernel não pode quebrar com r < 0 (VV-PLAN)."""
    s, k, tau, r, sigma = 100.0, 100.0, 1.0, -0.02, 0.20
    c = bs_price(s, k, tau, r, sigma, is_call=True)
    p = bs_price(s, k, tau, r, sigma, is_call=False)
    rhs = s - k * math.exp(-r * tau)
    assert_close(c - p, rhs, rel=REL_SELF, abs_=ABS_SELF_FLOOR * s, label="paridade r<0")


# ---------------------------------------------------------------------------
# 4. GREGAS ANALÍTICAS vs DIFERENÇAS FINITAS CENTRAIS
# ---------------------------------------------------------------------------
# Grid determinístico, afastado das fronteiras (FD perto de tau -> 0 diverge
# por construção, não por bug). h = FD_STEP * escala do parâmetro perturbado.

_FD_GRID: list[BSParams] = [
    (s, 100.0, tau, r, sigma, q)
    for s in (80.0, 100.0, 125.0)
    for tau in (0.1, 0.5, 2.0)
    for sigma in (0.1, 0.2, 0.5)
    for r in (0.0, 0.05, 0.12)
    for q in (0.0, 0.04)
]


def _fd_ids(params: BSParams) -> str:
    s, _, tau, r, sigma, q = params
    return f"s{s:g}-t{tau:g}-v{sigma:g}-r{r:g}-q{q:g}"


@pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
@pytest.mark.parametrize("params", _FD_GRID, ids=_fd_ids)
def test_delta_vs_central_fd(params: BSParams, is_call: bool) -> None:
    s, k, tau, r, sigma, q = params
    h = FD_STEP * s
    f_hi = bs_price(s + h, k, tau, r, sigma, q, is_call=is_call)
    f_lo = bs_price(s - h, k, tau, r, sigma, q, is_call=is_call)
    fd = (f_hi - f_lo) / (2.0 * h)
    analytic = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).delta
    tol = fd_abs_tol(max(abs(f_hi), abs(f_lo)), h)
    assert_close(analytic, fd, rel=REL_FD, abs_=tol, label="delta vs FD")


@pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
@pytest.mark.parametrize("params", _FD_GRID, ids=_fd_ids)
def test_vega_vs_central_fd(params: BSParams, is_call: bool) -> None:
    s, k, tau, r, sigma, q = params
    h = FD_STEP * sigma
    f_hi = bs_price(s, k, tau, r, sigma + h, q, is_call=is_call)
    f_lo = bs_price(s, k, tau, r, sigma - h, q, is_call=is_call)
    fd = (f_hi - f_lo) / (2.0 * h)
    analytic = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).vega_per_vol_unit
    tol = fd_abs_tol(max(abs(f_hi), abs(f_lo)), h)
    assert_close(analytic, fd, rel=REL_FD, abs_=tol, label="vega vs FD")


@pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
@pytest.mark.parametrize("params", _FD_GRID, ids=_fd_ids)
def test_theta_vs_central_fd(params: BSParams, is_call: bool) -> None:
    """theta = dV/dt = -dV/d(tau): a FD em tau estima +dV/d(tau)."""
    s, k, tau, r, sigma, q = params
    h = FD_STEP * tau
    f_hi = bs_price(s, k, tau + h, r, sigma, q, is_call=is_call)
    f_lo = bs_price(s, k, tau - h, r, sigma, q, is_call=is_call)
    fd = (f_hi - f_lo) / (2.0 * h)
    analytic = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).theta_per_year
    tol = fd_abs_tol(max(abs(f_hi), abs(f_lo)), h)
    assert_close(analytic, -fd, rel=REL_FD, abs_=tol, label="theta vs FD")


@pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
@pytest.mark.parametrize("params", _FD_GRID, ids=_fd_ids)
def test_rho_vs_central_fd(params: BSParams, is_call: bool) -> None:
    s, k, tau, r, sigma, q = params
    h = FD_STEP * 1.0  # escala natural da taxa: 1.00
    f_hi = bs_price(s, k, tau, r + h, sigma, q, is_call=is_call)
    f_lo = bs_price(s, k, tau, r - h, sigma, q, is_call=is_call)
    fd = (f_hi - f_lo) / (2.0 * h)
    analytic = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).rho
    tol = fd_abs_tol(max(abs(f_hi), abs(f_lo)), h)
    assert_close(analytic, fd, rel=REL_FD, abs_=tol, label="rho vs FD")


@pytest.mark.parametrize("is_call", [True, False], ids=["call", "put"])
@pytest.mark.parametrize("params", _FD_GRID, ids=_fd_ids)
def test_gamma_vs_central_fd_of_analytic_delta(params: BSParams, is_call: bool) -> None:
    """Rota recomendada no VV-PLAN: FD central do DELTA analítico.

    Mantém a precisão de 1ª diferença (eps^(2/3)) e valida a consistência
    delta <-> gamma — mais forte que a 2ª diferença do preço.
    """
    s, k, tau, r, sigma, q = params
    h = FD_STEP * s
    f_hi = bs_outputs(s + h, k, tau, r, sigma, q, is_call=is_call).delta
    f_lo = bs_outputs(s - h, k, tau, r, sigma, q, is_call=is_call).delta
    fd = (f_hi - f_lo) / (2.0 * h)
    analytic = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).gamma
    tol = fd_abs_tol(max(abs(f_hi), abs(f_lo)), h)
    assert_close(analytic, fd, rel=REL_FD, abs_=tol, label="gamma vs FD(delta)")

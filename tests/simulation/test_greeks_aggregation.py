"""Agregação de gregas de portfólio — linearidade, rho e vega por direção.

O teste de vega LÊ a direção da estrutura (condor_direction), nunca a assume
(decisão nº 3), e restringe o domínio à condição DERIVADA em que o corpo
domina o vega das asas (pico de vega entre as médias geométricas dos pares
de strikes) — fora dela o sinal legitimamente inverte; ver o docstring do
teste.
"""

import math

from hypothesis import assume, given
from hypothesis import strategies as st

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.conventions import TimeToExpiry
from options_engine.domain.model.enums import Side
from options_engine.domain.model.factories import condor_direction, iron_condor, straddle
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import mark_to_model_value, portfolio_greeks
from tests._tolerances import ABS_SELF_FLOOR, INEQ_SLACK, REL_SELF, assert_close
from tests.domain._builders import (
    make_condor_legs,
    make_leg,
    make_snapshot,
    make_straddle_legs,
    make_terms,
    st_strategy,
)

_TTX = TimeToExpiry.from_days(126)  # 0.5 ano em BUSINESS_252


# ---------------------------------------------------------------------------
# Linearidade: greeks(portfólio) == Σ sign·qty·greeks(leg) — incluindo rho
# ---------------------------------------------------------------------------


@given(estrutura=st_strategy())
def test_gregas_do_portfolio_sao_a_soma_ponderada(estrutura: Strategy) -> None:
    snap = make_snapshot()
    agregadas = portfolio_greeks(estrutura, time_to_expiry=_TTX, snapshot=snap)
    escala = 30.0 * sum(leg.quantity for leg in estrutura.legs)
    for campo in ("delta", "gamma", "theta_per_year", "vega_per_vol_unit", "rho"):
        esperado = math.fsum(
            leg.side.sign
            * leg.quantity
            * getattr(
                bs_outputs(
                    30.0,
                    leg.terms.strike,
                    0.5,
                    0.10,
                    0.25,
                    is_call=leg.terms.option_type.is_call,
                ),
                campo,
            )
            for leg in estrutura.legs
        )
        assert_close(
            getattr(agregadas, campo),
            esperado,
            rel=REL_SELF,
            abs_=ABS_SELF_FLOOR * escala,
            label=f"Σ {campo}",
        )


@given(estrutura=st_strategy())
def test_gregas_short_sao_menos_as_gregas_long(estrutura: Strategy) -> None:
    snap = make_snapshot()
    direto = portfolio_greeks(estrutura, time_to_expiry=_TTX, snapshot=snap)
    espelho = portfolio_greeks(estrutura.mirrored(), time_to_expiry=_TTX, snapshot=snap)
    escala = 30.0 * sum(leg.quantity for leg in estrutura.legs)
    for campo in ("delta", "gamma", "theta_per_year", "vega_per_vol_unit", "rho"):
        assert_close(
            getattr(espelho, campo),
            -getattr(direto, campo),
            rel=REL_SELF,
            abs_=ABS_SELF_FLOOR * escala,
            label=f"espelho {campo}",
        )


# ---------------------------------------------------------------------------
# Delta do straddle ATM-forward ≈ 0
# ---------------------------------------------------------------------------


def test_delta_do_straddle_atm_forward_e_pequeno() -> None:
    """Em K = F o delta do straddle é e^(-q·tau)·(2N(sigma·√tau/2) - 1) por
    unidade — limitado por 0.8·sigma·√tau (envelope 2N(x)-1 <= 2·n(0)·x).
    O bound é derivado, não número mágico."""
    sigma, tau, r, spot, qty = 0.25, 0.5, 0.10, 30.0, 10
    strike_forward = spot * math.exp(r * tau)
    estrutura = straddle(
        make_straddle_legs(direction=Side.BUY, strike=strike_forward, quantity=qty),
    )
    gregas = portfolio_greeks(estrutura, time_to_expiry=_TTX, snapshot=make_snapshot(spot=spot))
    envelope = 0.8 * sigma * math.sqrt(tau) * qty
    assert abs(gregas.delta) <= envelope + INEQ_SLACK * qty


# ---------------------------------------------------------------------------
# Vega condicionado à direção (decisão nº 3) — o teste LÊ a direção
# ---------------------------------------------------------------------------

_SPOT_CENTRAL = st.integers(min_value=56, max_value=64).map(lambda n: n / 2.0)  # [28, 32]
_VOL = st.integers(min_value=2, max_value=8).map(lambda n: n * 0.05)  # 0.10..0.40
_TAU_DIAS = st.integers(min_value=21, max_value=252)  # 1 mês a 1 ano útil
_TAXA = st.integers(min_value=0, max_value=12).map(lambda n: n / 100.0)  # 0..12%


@given(
    direction=st.sampled_from([Side.SELL, Side.BUY]),
    spot=_SPOT_CENTRAL,
    vol=_VOL,
    dias=_TAU_DIAS,
    taxa=_TAXA,
)
def test_vega_do_condor_condicionado_a_direcao(
    direction: Side, spot: float, vol: float, dias: int, taxa: float
) -> None:
    """Sob vol up (+5 pontos), condor VENDIDO não cresce e condor COMPRADO
    não decresce. O assert é escolhido pela direção LIDA da estrutura.

    Condição de regime DERIVADA (não chute): vega(K) é uma gaussiana exata
    em ln K centrada em ln K*, com K* = S·e^((r+sigma²/2)·tau). O corpo
    domina o vega das asas sse K* fica entre as médias geométricas dos
    pares (K1,K2) e (K3,K4) — assim cada perna do corpo fica mais perto do
    pico que a asa correspondente. Fora desse regime (achado por
    Hypothesis: spot=28, tau=1.5, r=15%) o pico migra para além da asa alta
    e o sinal do vega líquido legitimamente inverte — física da fórmula,
    não bug; o conhecimento fica codificado neste assume."""
    condor = iron_condor(make_condor_legs(direction=direction))
    tau = dias / 252.0
    k_pico = spot * math.exp((taxa + 0.5 * vol * vol) * tau)
    assume(math.sqrt(26.0 * 28.0) < k_pico < math.sqrt(32.0 * 34.0))
    ttx = TimeToExpiry.from_days(dias)
    folga = INEQ_SLACK * spot * 10  # escala: spot x quantidade
    base = mark_to_model_value(
        condor, spot, time_to_expiry=ttx, snapshot=make_snapshot(vol=vol, rate=taxa)
    )
    chocado = mark_to_model_value(
        condor, spot, time_to_expiry=ttx, snapshot=make_snapshot(vol=vol + 0.05, rate=taxa)
    )
    if condor_direction(condor) is Side.SELL:
        assert chocado <= base + folga
    else:
        assert chocado >= base - folga


def test_vega_agregado_do_condor_tem_o_sinal_da_direcao() -> None:
    """No centro do miolo: vendido = short vega (<= 0), comprado = espelho."""
    snap = make_snapshot()
    folga = INEQ_SLACK * 300.0
    vendido = portfolio_greeks(
        iron_condor(make_condor_legs(direction=Side.SELL)), time_to_expiry=_TTX, snapshot=snap
    )
    comprado = portfolio_greeks(
        iron_condor(make_condor_legs(direction=Side.BUY)), time_to_expiry=_TTX, snapshot=snap
    )
    assert vendido.vega_per_vol_unit <= folga
    assert comprado.vega_per_vol_unit >= -folga


def test_straddle_comprado_e_long_vega() -> None:
    gregas = portfolio_greeks(
        straddle(make_straddle_legs(direction=Side.BUY)),
        time_to_expiry=_TTX,
        snapshot=make_snapshot(),
    )
    assert gregas.vega_per_vol_unit >= -INEQ_SLACK * 300.0


def test_rho_do_condor_e_agregado_explicitamente() -> None:
    """Rho existe e agrega desde o dia 1 — casa com StressScenario.rate_shift."""
    condor = iron_condor(make_condor_legs())
    gregas = portfolio_greeks(condor, time_to_expiry=_TTX, snapshot=make_snapshot())
    esperado = math.fsum(
        leg.side.sign
        * leg.quantity
        * bs_outputs(
            30.0, leg.terms.strike, 0.5, 0.10, 0.25, is_call=leg.terms.option_type.is_call
        ).rho
        for leg in condor.legs
    )
    assert_close(gregas.rho, esperado, rel=REL_SELF, abs_=ABS_SELF_FLOOR * 300.0, label="rho")


def test_opcao_seca_reproduz_o_kernel() -> None:
    """Portfólio de 1 leg qty 1: as gregas agregadas SÃO as do kernel."""
    seca = Strategy.create("call seca", [make_leg(terms=make_terms(strike=30.0), quantity=1)])
    gregas = portfolio_greeks(seca, time_to_expiry=_TTX, snapshot=make_snapshot())
    kernel = bs_outputs(30.0, 30.0, 0.5, 0.10, 0.25, is_call=True)
    assert_close(gregas.delta, kernel.delta, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="delta")
    assert_close(
        gregas.theta_per_year,
        kernel.theta_per_year,
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * 30.0,
        label="theta",
    )

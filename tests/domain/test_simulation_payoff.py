"""Motor de payoff/P&L no vencimento — goldens geométricos e propriedades.

Goldens: geometria conhecida de cor de cada estrutura nomeada (vértices,
platôs, pico, V), com prêmios canônicos dos builders. Propriedades: payoff
da estrutura = soma dos payoffs das legs; short == -long ponto a ponto (o
anti-inversão-de-P&L, propriedade mais importante da Sprint 2); pnl exige
prêmio (decisão nº 4); AMERICAN é rejeitado (decisão nº 2).
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.model.enums import ExerciseStyle, Side
from options_engine.domain.model.errors import (
    MissingPremiumError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.factories import butterfly, iron_condor, straddle
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import (
    net_premium_cashflow,
    payoff_at_expiry,
    payoff_profile,
    pnl,
)
from tests._tolerances import (
    ABS_BREAKEVEN,
    ABS_PAYOFF,
    ABS_SELF_FLOOR,
    REL_BREAKEVEN,
    REL_PAYOFF,
    REL_SELF,
    assert_close,
)
from tests.domain._builders import (
    make_butterfly_legs,
    make_condor_legs,
    make_leg,
    make_straddle_legs,
    make_terms,
    st_strategy,
)

# ---------------------------------------------------------------------------
# Goldens geométricos por estrutura nomeada (qty 10)
# ---------------------------------------------------------------------------


def test_golden_condor_de_credito_vertices_e_plataus() -> None:
    """Crédito líquido 1.00/un x qty 10: platô central +10, asas -10,
    zeros exatamente nos breakevens 27 e 33."""
    condor = iron_condor(make_condor_legs(direction=Side.SELL, quantity=10))
    esperados = {
        20.0: -10.0,
        26.0: -10.0,  # vértice da asa baixa
        27.0: 0.0,  # breakeven K2 - crédito
        28.0: 10.0,  # vértice do corpo put
        30.0: 10.0,  # platô central
        32.0: 10.0,  # vértice do corpo call
        33.0: 0.0,  # breakeven K3 + crédito
        34.0: -10.0,  # vértice da asa alta
        40.0: -10.0,
    }
    for spot, esperado in esperados.items():
        assert_close(
            pnl(condor, spot), esperado, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label=f"pnl s={spot}"
        )


def test_golden_straddle_comprado_v_em_k() -> None:
    """Débito 3.45/un x qty 10: vale do V em K com -34.5; pernas simétricas."""
    estrutura = straddle(make_straddle_legs(direction=Side.BUY, quantity=10))
    assert_close(
        payoff_at_expiry(estrutura, 30.0), 0.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="V em K"
    )
    assert_close(
        payoff_at_expiry(estrutura, 25.0), 50.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="perna put"
    )
    assert_close(
        payoff_at_expiry(estrutura, 35.0),
        50.0,
        rel=REL_PAYOFF,
        abs_=ABS_PAYOFF,
        label="perna call",
    )
    assert_close(
        pnl(estrutura, 30.0), -34.5, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="fundo do V líquido"
    )


def test_golden_butterfly_comprada_pico_em_k2() -> None:
    """Pico bruto (K2-K1) x qty = 20 em K2; zero nas asas e além delas."""
    estrutura = butterfly(make_butterfly_legs(direction=Side.BUY, quantity=10))
    esperados = {26.0: 0.0, 28.0: 0.0, 30.0: 20.0, 32.0: 0.0, 34.0: 0.0}
    for spot, esperado in esperados.items():
        assert_close(
            payoff_at_expiry(estrutura, spot),
            esperado,
            rel=REL_PAYOFF,
            abs_=ABS_PAYOFF,
            label=f"fly s={spot}",
        )


# ---------------------------------------------------------------------------
# Semântica payoff (bruto) vs pnl (líquido) — decisão nº 4
# ---------------------------------------------------------------------------


def test_payoff_bruto_nao_exige_premio() -> None:
    condor = iron_condor(make_condor_legs(premiums=None))
    assert_close(
        payoff_at_expiry(condor, 30.0), 0.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="bruto"
    )


def test_pnl_sem_premio_e_erro_tipado() -> None:
    condor = iron_condor(make_condor_legs(premiums=None))
    with pytest.raises(MissingPremiumError):
        pnl(condor, 30.0)


def test_pnl_com_premio_parcial_tambem_e_erro() -> None:
    """Ou todas as legs têm prêmio, ou pnl não existe — parcial não conta."""
    legs = make_condor_legs()
    legs[2] = make_leg(
        symbol=legs[2].symbol, terms=legs[2].terms, side=legs[2].side, quantity=10, premium=None
    )
    with pytest.raises(MissingPremiumError):
        pnl(iron_condor(legs), 30.0)


def test_cashflow_do_condor_de_credito_e_positivo() -> None:
    """Vender o corpo recebe mais do que as asas custam: crédito +10."""
    condor = iron_condor(make_condor_legs(direction=Side.SELL, quantity=10))
    assert_close(
        net_premium_cashflow(condor), 10.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="crédito"
    )


def test_cashflow_do_straddle_comprado_e_negativo() -> None:
    estrutura = straddle(make_straddle_legs(direction=Side.BUY, quantity=10))
    assert_close(
        net_premium_cashflow(estrutura), -34.5, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="débito"
    )


# ---------------------------------------------------------------------------
# payoff_profile — perfil completo com breakevens em forma fechada
# ---------------------------------------------------------------------------


def test_perfil_do_condor_com_premio() -> None:
    condor = iron_condor(make_condor_legs(direction=Side.SELL, quantity=10))
    eixo = (20.0, 26.0, 28.0, 30.0, 32.0, 34.0, 40.0)
    perfil = payoff_profile(condor, eixo)

    assert perfil.pnl is not None
    assert perfil.breakevens is not None
    # Breakevens em forma fechada: K2 - crédito unitário e K3 + crédito
    # unitário — independem da quantidade (zeros da curva escalada).
    assert len(perfil.breakevens) == 2
    assert_close(perfil.breakevens[0], 27.0, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="K2-c")
    assert_close(perfil.breakevens[1], 33.0, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="K3+c")
    assert perfil.max_gain is not None
    assert perfil.max_loss is not None
    assert_close(perfil.max_gain, 10.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="ganho máx")
    assert_close(perfil.max_loss, -10.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="perda máx")
    # pnl == payoff + cashflow, ponto a ponto.
    for bruto, liquido in zip(perfil.payoff_at_expiry, perfil.pnl, strict=True):
        assert_close(liquido, bruto + 10.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="pnl=payoff+c")


def test_perfil_sem_premio_so_tem_o_bruto() -> None:
    condor = iron_condor(make_condor_legs(premiums=None))
    perfil = payoff_profile(condor, (20.0, 30.0, 40.0))
    assert perfil.pnl is None
    assert perfil.breakevens is None
    assert perfil.max_gain is not None
    assert perfil.max_loss is not None
    # Extremos do BRUTO do condor de crédito: teto 0 (tudo pó), piso -largura
    # da asa x qty = -2 x 10.
    assert_close(perfil.max_gain, 0.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="bruto máx")
    assert_close(perfil.max_loss, -20.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="bruto mín")


def test_perfil_de_call_comprada_tem_ganho_ilimitado() -> None:
    seca = Strategy.create("call seca", [make_leg(premium=2.5)])
    perfil = payoff_profile(seca, (20.0, 30.0, 40.0))
    assert perfil.max_gain is None  # None = ilimitado, explícito no tipo
    assert perfil.max_loss is not None
    assert_close(perfil.max_loss, -25.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="perda = débito")


# ---------------------------------------------------------------------------
# Propriedades (Hypothesis)
# ---------------------------------------------------------------------------

_SPOTS = st.integers(min_value=0, max_value=200).map(lambda n: n / 2.0)


@given(estrutura=st_strategy(), spot=_SPOTS)
def test_payoff_da_estrutura_e_a_soma_das_legs(estrutura: Strategy, spot: float) -> None:
    """Linearidade do Composite: o todo é exatamente a soma ponderada."""
    por_leg = [
        payoff_at_expiry(Strategy.create(f"leg {leg.symbol}", [leg]), spot)
        for leg in estrutura.legs
    ]
    escala = max((leg.terms.strike for leg in estrutura.legs), default=1.0)
    assert_close(
        payoff_at_expiry(estrutura, spot),
        sum(por_leg),
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * escala,
        label="Σ legs",
    )


@given(estrutura=st_strategy(with_premiums=True), spot=_SPOTS)
def test_short_e_menos_long_ponto_a_ponto(estrutura: Strategy, spot: float) -> None:
    """A propriedade mais importante da Sprint 2: espelhar todos os lados
    nega o P&L em TODO spot — inclusive o fluxo de prêmios."""
    espelhada = estrutura.mirrored()
    escala = max(leg.terms.strike for leg in estrutura.legs)
    assert_close(
        pnl(espelhada, spot),
        -pnl(estrutura, spot),
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * escala,
        label="short == -long (pnl)",
    )
    assert_close(
        payoff_at_expiry(espelhada, spot),
        -payoff_at_expiry(estrutura, spot),
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * escala,
        label="short == -long (payoff)",
    )


# ---------------------------------------------------------------------------
# Rejeição de AMERICAN (decisão nº 2)
# ---------------------------------------------------------------------------


def _estrutura_americana() -> Strategy:
    leg = make_leg(terms=make_terms(exercise_style=ExerciseStyle.AMERICAN), premium=1.0)
    return Strategy.create("americana", [leg])


def test_payoff_rejeita_american() -> None:
    with pytest.raises(UnsupportedExerciseStyleError):
        payoff_at_expiry(_estrutura_americana(), 30.0)


def test_pnl_rejeita_american() -> None:
    with pytest.raises(UnsupportedExerciseStyleError):
        pnl(_estrutura_americana(), 30.0)


def test_perfil_rejeita_american() -> None:
    with pytest.raises(UnsupportedExerciseStyleError):
        payoff_profile(_estrutura_americana(), (20.0, 30.0, 40.0))

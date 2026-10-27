"""Mark-to-model — reprecificação com tau remanescente, fronteiras do motor.

Oráculos: o próprio kernel BS por leg (linearidade, auto-consistência
REL_SELF) e o kernel de payoff no limite tau = 0 (posição vencida ==
intrínseco descontado, decisão nº 5).
"""

import math

import pytest
from hypothesis import given

from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    TimeToExpiry,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    MissingPremiumError,
    MixedAnnualizationBaseError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.factories import iron_condor
from options_engine.domain.model.scenarios import StressScenario
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import (
    apply_scenario,
    mark_to_model_value,
    payoff_at_expiry,
    pnl,
    pnl_curve,
)
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.domain._builders import (
    make_condor_legs,
    make_leg,
    make_snapshot,
    make_terms,
    st_strategy,
)

_TTX = TimeToExpiry.from_days(126)  # 0.5 ano em BUSINESS_252
_VENCIDA = TimeToExpiry.from_days(0)
_EIXO = (24.0, 27.0, 30.0, 33.0, 36.0)


def _condor(premiums: bool = True) -> Strategy:
    return iron_condor(
        make_condor_legs(premiums=None if not premiums else (0.30, 0.80, 0.85, 0.35))
    )


def test_valor_e_a_soma_bs_das_legs() -> None:
    """Auto-consistência: o motor é exatamente Σ sign·qty·BS(leg)."""
    condor = _condor()
    snap = make_snapshot()
    r = 0.10  # o snapshot canônico carrega 10% já em capitalização contínua
    esperado = math.fsum(
        leg.side.sign
        * leg.quantity
        * bs_price(
            30.0,
            leg.terms.strike,
            0.5,
            r,
            0.25,
            is_call=leg.terms.option_type.is_call,
        )
        for leg in condor.legs
    )
    assert_close(
        mark_to_model_value(condor, 30.0, time_to_expiry=_TTX, snapshot=snap),
        esperado,
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * 30.0,
        label="Σ BS legs",
    )


def test_posicao_vencida_vale_o_intrinseco_descontado() -> None:
    """Decisão nº 5: tau = 0 cai no ramo fechado do kernel — o valor é o
    payoff no vencimento (fator de desconto 1), nunca NaN, nunca erro."""
    condor = _condor()
    snap = make_snapshot()
    for spot in _EIXO:
        assert_close(
            mark_to_model_value(condor, spot, time_to_expiry=_VENCIDA, snapshot=snap),
            payoff_at_expiry(condor, spot),
            rel=REL_SELF,
            abs_=ABS_SELF_FLOOR * 30.0,
            label=f"vencida s={spot}",
        )


def test_pnl_curve_exige_premio() -> None:
    with pytest.raises(MissingPremiumError):
        pnl_curve(_condor(premiums=False), _EIXO, time_to_expiry=_TTX, snapshot=make_snapshot())


def test_pnl_curve_no_vencimento_e_o_pnl_do_vencimento() -> None:
    """Coerência entre as três semânticas: a curva mark-to-model com tau = 0
    coincide com pnl (vencimento) ponto a ponto."""
    condor = _condor()
    snap = make_snapshot()
    curva = pnl_curve(condor, _EIXO, time_to_expiry=_VENCIDA, snapshot=snap)
    for spot, valor in zip(_EIXO, curva, strict=True):
        assert_close(
            valor,
            pnl(condor, spot),
            rel=REL_SELF,
            abs_=ABS_SELF_FLOOR * 30.0,
            label=f"curva==pnl s={spot}",
        )


@given(estrutura=st_strategy(with_premiums=True))
def test_curva_short_e_menos_long(estrutura: Strategy) -> None:
    """short == -long também a mercado (mark-to-model), não só no vencimento."""
    snap = make_snapshot()
    escala = max(leg.terms.strike for leg in estrutura.legs)
    curva = pnl_curve(estrutura, _EIXO, time_to_expiry=_TTX, snapshot=snap)
    espelhada = pnl_curve(estrutura.mirrored(), _EIXO, time_to_expiry=_TTX, snapshot=snap)
    for direto, espelho in zip(curva, espelhada, strict=True):
        assert_close(
            espelho, -direto, rel=REL_SELF, abs_=ABS_SELF_FLOOR * escala, label="espelho a mercado"
        )


def test_base_misturada_e_rejeitada() -> None:
    """Vol em base 365 com tau em base 252: o erro silencioso vira exceção."""
    snap_365 = make_snapshot(vol_base=DayCountConvention.CALENDAR_365)
    with pytest.raises(MixedAnnualizationBaseError):
        mark_to_model_value(_condor(), 30.0, time_to_expiry=_TTX, snapshot=snap_365)
    with pytest.raises(MixedAnnualizationBaseError):
        pnl_curve(_condor(), _EIXO, time_to_expiry=_TTX, snapshot=snap_365)


def test_american_e_rejeitado_a_mercado() -> None:
    """Inclusive a CALL americana: a aproximação da ADR-0002 vale só no
    ``PricingModel``, que marca o resultado; o valor a mercado não tem marca."""
    terms = make_terms(option_type=OptionType.CALL, exercise_style=ExerciseStyle.AMERICAN)
    americana = Strategy.create("americana", [make_leg(terms=terms, premium=1.0)])
    with pytest.raises(UnsupportedExerciseStyleError):
        mark_to_model_value(americana, 30.0, time_to_expiry=_TTX, snapshot=make_snapshot())


# ---------------------------------------------------------------------------
# apply_scenario — choques nomeados sobre o snapshot
# ---------------------------------------------------------------------------


def test_cenario_choca_spot_book_vol_e_taxa() -> None:
    base = make_snapshot(rate=0.1365, compounding=Compounding.BUSINESS_DAILY_252)
    crise = StressScenario(label="crise", spot_shift=0.80, vol_shift=0.10, rate_shift=0.02)
    chocado = apply_scenario(base, crise)

    assert_close(chocado.spot, 24.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="spot")
    # Book escala junto do spot — coerência bid <= mid <= ask preservada.
    assert_close(chocado.bid, 29.95 * 0.80, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="bid")
    assert_close(chocado.ask, 30.05 * 0.80, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="ask")
    assert_close(chocado.volatility.value, 0.35, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="vol")
    # Taxa: CDI convertido para contínua ANTES do choque aditivo.
    assert chocado.risk_free_rate.compounding is Compounding.CONTINUOUS
    assert_close(
        chocado.risk_free_rate.rate,
        math.log1p(0.1365) + 0.02,
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR,
        label="taxa contínua chocada",
    )


def test_choque_que_negativa_a_vol_e_irrepresentavel() -> None:
    """O VO Volatility rejeita na construção — cenário impossível não gera
    snapshot impossível."""
    base = make_snapshot(vol=0.15)
    with pytest.raises(InvalidDomainValueError):
        apply_scenario(base, StressScenario(label="vol crush", vol_shift=-0.20))

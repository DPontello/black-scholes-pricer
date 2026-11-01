"""Probabilidade risco-neutra de lucro no vencimento (lognormal), contra conta independente."""

from math import erf, exp, log, sqrt
from statistics import NormalDist

import pytest

from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    TimeToExpiry,
    Volatility,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.errors import MixedAnnualizationBaseError
from options_engine.domain.model.factories import iron_condor
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import pnl
from options_engine.domain.simulation.probability import probability_of_profit
from tests._tolerances import ABS_PROBABILITY_GRID, PROBABILITY_GRID_POINTS
from tests.domain._builders import make_condor_legs, make_leg, make_stock_leg, make_terms

_TTX = TimeToExpiry.from_days(63)
_TAXA = RiskFreeRate(0.10, Compounding.CONTINUOUS)
_VOL = Volatility(0.30, DayCountConvention.BUSINESS_252)
_SPOT = 30.0


def _phi(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def _acima(nivel: float) -> float:
    """P(S_T > nivel) pela fórmula fechada, escrita aqui de novo de propósito."""
    tau, sigma = _TTX.year_fraction, _VOL.value
    d2 = (log(_SPOT / nivel) + (0.10 - sigma**2 / 2) * tau) / (sigma * sqrt(tau))
    return _phi(d2)


def _pela_grade(estrutura: Strategy) -> float:
    tau, sigma = _TTX.year_fraction, _VOL.value
    normal = NormalDist()
    deriva = (0.10 - sigma**2 / 2) * tau
    n = PROBABILITY_GRID_POINTS
    positivos = sum(
        pnl(estrutura, _SPOT * exp(deriva + sigma * sqrt(tau) * normal.inv_cdf((i + 0.5) / n)))
        > 0.0
        for i in range(n)
    )
    return positivos / n


def _probabilidade(estrutura: Strategy, ttx: TimeToExpiry = _TTX) -> float:
    return probability_of_profit(estrutura, _SPOT, time_to_expiry=ttx, rate=_TAXA, vol=_VOL)


def test_call_comprada_e_a_chance_de_passar_do_breakeven() -> None:
    call = make_leg(terms=make_terms(strike=31.0), quantity=100, premium=1.2)
    estrutura = Strategy.create("compra de call", [call])
    assert _probabilidade(estrutura) == pytest.approx(_acima(32.2), abs=1e-12)


def test_venda_coberta_e_a_chance_de_ficar_acima_do_breakeven() -> None:
    call = make_leg(terms=make_terms(strike=32.0), side=Side.SELL, quantity=100, premium=1.0)
    coberta = Strategy.create("venda coberta", [call], [make_stock_leg(price=30.0)])
    assert _probabilidade(coberta) == pytest.approx(_acima(29.0), abs=1e-12)


@pytest.mark.parametrize("nome", ["put vendida", "iron condor"])
def test_bate_com_a_grade_estratificada(nome: str) -> None:
    if nome == "put vendida":
        put = make_leg(
            terms=make_terms(strike=29.0, option_type=OptionType.PUT),
            side=Side.SELL,
            quantity=100,
            premium=0.9,
        )
        estrutura = Strategy.create(nome, [put])
    else:
        estrutura = iron_condor(make_condor_legs(direction=Side.SELL, quantity=10))
    probabilidade = _probabilidade(estrutura)
    assert 0.0 <= probabilidade <= 1.0
    assert probabilidade == pytest.approx(_pela_grade(estrutura), abs=ABS_PROBABILITY_GRID)


def test_no_vencimento_a_resposta_e_zero_ou_um() -> None:
    call = make_leg(terms=make_terms(strike=28.0), quantity=100, premium=1.0)
    no_dinheiro = Strategy.create("call", [call])
    fora = Strategy.create("call", [make_leg(terms=make_terms(strike=40.0), premium=1.0)])
    vencida = TimeToExpiry.from_days(0)
    assert _probabilidade(no_dinheiro, vencida) == 1.0
    assert _probabilidade(fora, vencida) == 0.0


def test_vol_e_tau_na_mesma_base() -> None:
    estrutura = Strategy.create("call", [make_leg(premium=1.0)])
    em_365 = Volatility(0.30, DayCountConvention.CALENDAR_365)
    with pytest.raises(MixedAnnualizationBaseError):
        probability_of_profit(estrutura, _SPOT, time_to_expiry=_TTX, rate=_TAXA, vol=em_365)


def test_put_comprada_e_a_chance_de_ficar_abaixo_do_breakeven() -> None:
    put = make_leg(
        terms=make_terms(strike=29.0, option_type=OptionType.PUT), quantity=100, premium=0.8
    )
    estrutura = Strategy.create("compra de put", [put])
    assert _probabilidade(estrutura) == pytest.approx(1.0 - _acima(28.2), abs=1e-12)


def test_call_americana_tambem_tem_probabilidade() -> None:
    call = make_leg(
        terms=make_terms(strike=31.0, exercise_style=ExerciseStyle.AMERICAN),
        quantity=100,
        premium=1.2,
    )
    estrutura = Strategy.create("compra de call", [call])
    assert _probabilidade(estrutura) == pytest.approx(_acima(32.2), abs=1e-12)

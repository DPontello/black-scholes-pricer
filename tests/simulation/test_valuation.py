"""Avaliação "hoje" do montador: vol por perna, call americana rotulada, gregas e grade."""

import pytest
from hypothesis import given

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    TimeToExpiry,
    Volatility,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    MixedAnnualizationBaseError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import (
    mark_to_model_value,
    net_premium_cashflow,
    pnl_curve,
    portfolio_greeks,
)
from options_engine.domain.simulation.valuation import (
    DEFAULT_SPOT_SHOCKS,
    DEFAULT_VOL_SHOCKS,
    american_call_approximated,
    scenario_matrix,
    structure_greeks,
    today_curve,
    today_value,
)
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.domain._builders import (
    make_leg,
    make_snapshot,
    make_stock_leg,
    make_terms,
    st_strategy,
)

_TTX = TimeToExpiry.from_days(126)
_TAXA = RiskFreeRate(0.10, Compounding.CONTINUOUS)
_B252 = DayCountConvention.BUSINESS_252


def _vols(estrutura: Strategy, sigma: float = 0.25) -> list[Volatility]:
    return [Volatility(sigma, _B252) for _ in estrutura.legs]


def _perto(a: float, b: float, escala: float = 1.0, label: str = "") -> None:
    assert_close(a, b, rel=REL_SELF, abs_=ABS_SELF_FLOOR * max(escala, 1.0), label=label)


@given(estrutura=st_strategy(with_premiums=True, with_stock=True))
def test_com_a_mesma_vol_bate_com_o_motor_de_vol_unica(estrutura: Strategy) -> None:
    snapshot = make_snapshot()
    escala = 2000.0
    vols = _vols(estrutura)
    _perto(
        today_value(estrutura, 31.0, time_to_expiry=_TTX, rate=_TAXA, vols=vols),
        mark_to_model_value(estrutura, 31.0, time_to_expiry=_TTX, snapshot=snapshot),
        escala,
        "valor",
    )
    for a, b in zip(
        today_curve(estrutura, [25.0, 30.0, 35.0], time_to_expiry=_TTX, rate=_TAXA, vols=vols),
        pnl_curve(estrutura, [25.0, 30.0, 35.0], time_to_expiry=_TTX, snapshot=snapshot),
        strict=True,
    ):
        _perto(a, b, escala, "curva")
    nossas = structure_greeks(estrutura, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=vols)
    do_motor = portfolio_greeks(estrutura, time_to_expiry=_TTX, snapshot=snapshot)
    for campo in ("delta", "gamma", "theta_per_year", "vega_per_vol_unit", "rho"):
        _perto(getattr(nossas, campo), getattr(do_motor, campo), escala, campo)


def _straddle() -> Strategy:
    call = make_leg(symbol="C30", terms=make_terms(strike=30.0), quantity=100, premium=1.5)
    put = make_leg(
        symbol="P30",
        terms=make_terms(strike=30.0, option_type=OptionType.PUT),
        quantity=100,
        premium=1.2,
    )
    return Strategy.create("straddle", [call, put])


def test_cada_perna_usa_a_propria_vol() -> None:
    vols = [Volatility(0.30, _B252), Volatility(0.20, _B252)]
    tau = _TTX.year_fraction
    esperado = 100 * bs_outputs(31.0, 30.0, tau, 0.10, 0.30, is_call=True).price + 100 * (
        bs_outputs(31.0, 30.0, tau, 0.10, 0.20, is_call=False).price
    )
    obtido = today_value(_straddle(), 31.0, time_to_expiry=_TTX, rate=_TAXA, vols=vols)
    _perto(obtido, esperado, 1000.0)


def test_call_americana_entra_como_europeia_e_rotulada() -> None:
    americana = make_leg(
        terms=make_terms(exercise_style=ExerciseStyle.AMERICAN), quantity=100, premium=1.0
    )
    europeia = make_leg(quantity=100, premium=1.0)
    com = Strategy.create("americana", [americana])
    sem = Strategy.create("europeia", [europeia])
    assert american_call_approximated(com) and not american_call_approximated(sem)
    _perto(
        today_value(com, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=_vols(com)),
        today_value(sem, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=_vols(sem)),
        1000.0,
    )


def test_put_americana_nao_tem_avaliacao_hoje() -> None:
    put = make_leg(
        terms=make_terms(option_type=OptionType.PUT, exercise_style=ExerciseStyle.AMERICAN)
    )
    estrutura = Strategy.create("put americana", [put])
    with pytest.raises(UnsupportedExerciseStyleError, match="put americana"):
        today_value(estrutura, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=_vols(estrutura))


def test_uma_vol_por_perna_na_mesma_base_do_tau() -> None:
    estrutura = _straddle()
    with pytest.raises(InvalidDomainValueError, match="vol"):
        today_value(estrutura, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=_vols(estrutura)[:1])
    em_365 = [Volatility(0.25, DayCountConvention.CALENDAR_365)] * 2
    with pytest.raises(MixedAnnualizationBaseError):
        today_value(estrutura, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=em_365)


def test_delta_da_venda_coberta_conta_as_acoes() -> None:
    call = make_leg(terms=make_terms(strike=32.0), side=Side.SELL, quantity=100, premium=1.0)
    coberta = Strategy.create("venda coberta", [call], [make_stock_leg()])
    gregas = structure_greeks(coberta, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=_vols(coberta))
    esperado = (
        100 - 100 * bs_outputs(30.0, 32.0, _TTX.year_fraction, 0.10, 0.25, is_call=True).delta
    )
    _perto(gregas.delta, esperado, 100.0)


def test_grade_tem_o_pnl_de_hoje_no_centro_e_none_onde_a_vol_zera() -> None:
    estrutura = _straddle()
    vols = [Volatility(0.08, _B252), Volatility(0.25, _B252)]
    grade = scenario_matrix(
        estrutura,
        30.0,
        time_to_expiry=_TTX,
        rate=_TAXA,
        vols=vols,
        spot_shocks=DEFAULT_SPOT_SHOCKS,
        vol_shocks=DEFAULT_VOL_SHOCKS,
    )
    assert (len(grade.values), len(grade.values[0])) == (7, 5)
    assert grade.spots == tuple(30.0 * (1 + c) for c in DEFAULT_SPOT_SHOCKS)
    centro = grade.values[DEFAULT_SPOT_SHOCKS.index(0.0)][DEFAULT_VOL_SHOCKS.index(0.0)]
    hoje = today_curve(estrutura, [30.0], time_to_expiry=_TTX, rate=_TAXA, vols=vols)[0]
    assert centro is not None
    _perto(centro, hoje, 1000.0)
    assert grade.values[0][0] is None  # 0,08 - 0,10 de vol na call
    assert grade.values[0][-1] is not None


def test_grade_tambem_exige_premio_e_o_pnl_soma_o_caixa() -> None:
    estrutura = _straddle()
    vols = _vols(estrutura)
    valor = today_value(estrutura, 30.0, time_to_expiry=_TTX, rate=_TAXA, vols=vols)
    (pnl,) = today_curve(estrutura, [30.0], time_to_expiry=_TTX, rate=_TAXA, vols=vols)
    _perto(pnl, valor + net_premium_cashflow(estrutura), 1000.0)


def test_choque_de_spot_de_menos_100_por_cento_e_recusado() -> None:
    estrutura = _straddle()
    with pytest.raises(InvalidDomainValueError, match="choque de spot"):
        scenario_matrix(
            estrutura,
            30.0,
            time_to_expiry=_TTX,
            rate=_TAXA,
            vols=_vols(estrutura),
            spot_shocks=(-1.0, 0.0),
        )

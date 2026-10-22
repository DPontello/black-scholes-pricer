"""``PriceOptionService`` — orquestração com fakes dos ports."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.inbound import PriceOptionCommand, PriceOptionUseCase
from options_engine.application.use_cases.price_option import PriceOptionService
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import ExpiredOptionError, UnsupportedExerciseStyleError
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from tests.application._fakes import FakeMarketData, FakeTradingCalendar
from tests.domain._builders import VENCIMENTO_PADRAO, make_snapshot, make_terms

UTC_MINUS_3 = timezone(timedelta(hours=-3))
INSTANTE_DE_VALORACAO = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)


def make_service(
    market_data: FakeMarketData | None = None,
    calendar: FakeTradingCalendar | None = None,
    day_count: DayCountConvention = DayCountConvention.BUSINESS_252,
) -> tuple[PriceOptionService, FakeMarketData, FakeTradingCalendar]:
    market_data = market_data if market_data is not None else FakeMarketData(make_snapshot())
    calendar = calendar if calendar is not None else FakeTradingCalendar(business_days=118)
    service = PriceOptionService(
        model=BlackScholesPricingModel(),
        market_data=market_data,
        clock=FixedClock(INSTANTE_DE_VALORACAO),
        calendar=calendar,
        valuation_timezone=UTC_MINUS_3,
        day_count=day_count,
    )
    return service, market_data, calendar


def test_service_satisfaz_o_protocol_inbound() -> None:
    service, _, _ = make_service()
    assert isinstance(service, PriceOptionUseCase)


def test_happy_path_orquestra_snapshot_tau_e_modelo() -> None:
    service, market_data, calendar = make_service()
    result = service.execute(PriceOptionCommand(terms=make_terms()))
    # Auditoria completa no resultado: modelo, snapshot e tau usados.
    assert result.model_id == "black-scholes-v1"
    assert result.snapshot == market_data.snapshot
    assert result.time_to_expiry.year_fraction == 118 / 252
    assert result.time_to_expiry.convention is DayCountConvention.BUSINESS_252
    assert result.price > 0.0
    # O símbolo consultado deriva dos termos (fonte única de verdade).
    assert market_data.requested_symbols == ["PETR4"]
    # A contagem parte da data de valoração no fuso B3 até o vencimento.
    assert calendar.requested_ranges == [(INSTANTE_DE_VALORACAO.date(), VENCIMENTO_PADRAO)]


def test_command_deriva_o_simbolo_dos_termos() -> None:
    command = PriceOptionCommand(terms=make_terms(underlying="VALE3"))
    assert command.underlying_symbol == "VALE3"


def test_exercicio_americano_falha_antes_de_tocar_o_mercado() -> None:
    service, market_data, _ = make_service()
    termos_americanos = make_terms(exercise_style=ExerciseStyle.AMERICAN)
    with pytest.raises(UnsupportedExerciseStyleError):
        service.execute(PriceOptionCommand(terms=termos_americanos))
    # Falha barata: estilo não suportado não merece uma ida ao feed.
    assert market_data.requested_symbols == []


def test_opcao_vencida_dispara_expired_option_error() -> None:
    service, _, _ = make_service()
    vencida = make_terms(expiry=INSTANTE_DE_VALORACAO.date() - timedelta(days=1))
    with pytest.raises(ExpiredOptionError):
        service.execute(PriceOptionCommand(terms=vencida))


def test_vencimento_no_proprio_dia_precifica_o_intrinseco() -> None:
    """tau = 0 cai no ramo fechado do kernel: call ITM vale spot - strike."""
    service, _, _ = make_service(calendar=FakeTradingCalendar(business_days=0))
    no_dia = make_terms(
        strike=28.0, expiry=INSTANTE_DE_VALORACAO.date(), option_type=OptionType.CALL
    )
    result = service.execute(PriceOptionCommand(terms=no_dia))
    # Igualdade exata permitida: ramo de forma fechada (intrínseco, spot 30).
    assert result.price == 2.0


def test_calendar_365_exige_vol_na_mesma_base() -> None:
    """A política de day count do service casa com a base da vol do snapshot
    — o VO de request detecta a mistura (CONVENTIONS §2)."""
    snapshot_365 = make_snapshot(vol_base=DayCountConvention.CALENDAR_365)
    service, _, calendar = make_service(
        market_data=FakeMarketData(snapshot_365),
        day_count=DayCountConvention.CALENDAR_365,
    )
    result = service.execute(PriceOptionCommand(terms=make_terms()))
    assert result.time_to_expiry.convention is DayCountConvention.CALENDAR_365
    # Dias corridos, sem consultar o calendário de dias úteis.
    assert calendar.requested_ranges == []

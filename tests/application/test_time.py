"""Helper único de tempo dos use cases — fuso, convenções e guarda de vencida."""

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.use_cases._time import resolve_time_to_expiry, valuation_date
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.errors import ExpiredOptionError
from tests.application._fakes import FakeTradingCalendar

UTC_MINUS_3 = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# valuation_date
# ---------------------------------------------------------------------------


def test_data_de_valoracao_converte_para_o_fuso_injetado() -> None:
    """01:30 UTC já é 'amanhã' em Londres, mas ainda 22:30 de HOJE na B3 —
    o .date() cru do UTC anteciparia o vencimento em um pregão."""
    clock = FixedClock(datetime(2026, 7, 4, 1, 30, tzinfo=UTC))
    assert valuation_date(clock, UTC_MINUS_3) == date(2026, 7, 3)
    assert valuation_date(clock, UTC) == date(2026, 7, 4)


# ---------------------------------------------------------------------------
# resolve_time_to_expiry
# ---------------------------------------------------------------------------


def test_business_252_conta_dias_uteis_via_calendario() -> None:
    calendar = FakeTradingCalendar(business_days=126)
    ttx = resolve_time_to_expiry(
        date(2026, 12, 18), date(2026, 7, 3), calendar, DayCountConvention.BUSINESS_252
    )
    assert ttx.year_fraction == 126 / 252
    assert ttx.convention is DayCountConvention.BUSINESS_252
    assert calendar.requested_ranges == [(date(2026, 7, 3), date(2026, 12, 18))]


def test_calendar_365_conta_dias_corridos_sem_consultar_o_calendario() -> None:
    """Usar o calendário de dias úteis numa convenção de dias corridos
    produziria tau errado sem erro de runtime — a armadilha inversa do §2."""
    calendar = FakeTradingCalendar(business_days=999)  # sentinela: não pode ser usada
    ttx = resolve_time_to_expiry(
        date(2026, 7, 13), date(2026, 7, 3), calendar, DayCountConvention.CALENDAR_365
    )
    assert ttx.year_fraction == 10 / 365
    assert ttx.convention is DayCountConvention.CALENDAR_365
    assert calendar.requested_ranges == []


def test_vencimento_no_proprio_dia_e_legal_com_tau_zero() -> None:
    """expiry == hoje: resta 0 dia útil, tau = 0, intrínseco descontado
    (decisão nº 5) — sem caso especial, sem exceção."""
    calendar = FakeTradingCalendar(business_days=0)
    ttx = resolve_time_to_expiry(
        date(2026, 7, 3), date(2026, 7, 3), calendar, DayCountConvention.BUSINESS_252
    )
    assert ttx.year_fraction == 0.0


def test_opcao_vencida_dispara_expired_option_error_antes_do_calendario() -> None:
    calendar = FakeTradingCalendar(business_days=0)
    with pytest.raises(ExpiredOptionError):
        resolve_time_to_expiry(
            date(2026, 7, 2), date(2026, 7, 3), calendar, DayCountConvention.BUSINESS_252
        )
    # A guarda fica no use case: o calendário nunca vê contagem negativa.
    assert calendar.requested_ranges == []

"""``StaticHolidayCalendar`` — semântica [start, end), feriados e cobertura."""

from datetime import date

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET, StaticHolidayCalendar
from options_engine.application.ports.outbound import TradingCalendar
from options_engine.domain.model.errors import InvalidDomainValueError

COBERTURA_2026 = {"coverage_start": date(2026, 1, 1), "coverage_end": date(2026, 12, 31)}


def _calendario(*feriados: date) -> StaticHolidayCalendar:
    return StaticHolidayCalendar(feriados, **COBERTURA_2026)


def test_satisfaz_o_protocol_em_runtime() -> None:
    assert isinstance(_calendario(), TradingCalendar)


# ---------------------------------------------------------------------------
# Semântica meio-aberta [start, end) — ARCH §4.1
# ---------------------------------------------------------------------------


def test_start_igual_end_conta_zero() -> None:
    """No próprio dia do vencimento resta 0 dia útil → tau = 0 (decisão nº 5)."""
    cal = _calendario()
    assert cal.business_days_between(date(2026, 7, 3), date(2026, 7, 3)) == 0


def test_um_dia_util_antes_do_vencimento_conta_um() -> None:
    """O pregão de HOJE ainda conta: [qui, sex) = 1."""
    cal = _calendario()
    assert cal.business_days_between(date(2026, 7, 2), date(2026, 7, 3)) == 1


def test_end_e_exclusivo() -> None:
    """[seg, seg+7) numa semana limpa = 5 — o end (a próxima segunda) fica fora."""
    cal = _calendario()
    assert cal.business_days_between(date(2026, 7, 6), date(2026, 7, 13)) == 5


def test_fim_de_semana_nao_conta() -> None:
    cal = _calendario()
    # [sábado, segunda) = 0 dias úteis.
    assert cal.business_days_between(date(2026, 7, 4), date(2026, 7, 6)) == 0


def test_feriado_em_dia_de_semana_nao_conta() -> None:
    # 2026-09-07 (Independência) cai numa segunda: [sex 04, ter 08) = só a sexta.
    cal = _calendario(date(2026, 9, 7))
    assert cal.business_days_between(date(2026, 9, 4), date(2026, 9, 8)) == 1


def test_start_maior_que_end_e_rejeitado() -> None:
    cal = _calendario()
    with pytest.raises(InvalidDomainValueError):
        cal.business_days_between(date(2026, 7, 10), date(2026, 7, 3))


# ---------------------------------------------------------------------------
# Guarda de cobertura — responder fora do range contaria feriado
# desconhecido como dia útil
# ---------------------------------------------------------------------------


def test_consulta_antes_da_cobertura_e_rejeitada() -> None:
    cal = _calendario()
    with pytest.raises(InvalidDomainValueError):
        cal.business_days_between(date(2025, 12, 20), date(2026, 1, 10))


def test_consulta_depois_da_cobertura_e_rejeitada() -> None:
    cal = _calendario()
    with pytest.raises(InvalidDomainValueError):
        cal.business_days_between(date(2026, 12, 1), date(2027, 1, 10))


def test_feriado_fora_da_cobertura_declarada_e_rejeitado_na_construcao() -> None:
    with pytest.raises(InvalidDomainValueError):
        StaticHolidayCalendar([date(2027, 1, 1)], **COBERTURA_2026)


def test_cobertura_invertida_e_rejeitada() -> None:
    with pytest.raises(InvalidDomainValueError):
        StaticHolidayCalendar([], coverage_start=date(2026, 12, 31), coverage_end=date(2026, 1, 1))


# ---------------------------------------------------------------------------
# Lista empacotada (decisão nº 7: arquivo estático versionado)
# ---------------------------------------------------------------------------


def test_lista_empacotada_carrega_e_conta_2026_inteiro() -> None:
    """2026 tem 261 dias de semana e 14 feriados B3 em dia de semana → 247
    pregões. Golden aritmético: se o CSV perder uma linha, este número muda."""
    cal = StaticHolidayCalendar.from_packaged_data()
    assert cal.business_days_between(date(2026, 1, 1), date(2027, 1, 1)) == 247


def test_lista_empacotada_conhece_vespera_de_natal() -> None:
    """24/12 e 25/12 sem pregão: [qua 23, sáb 26) conta só a quarta."""
    cal = StaticHolidayCalendar.from_packaged_data()
    assert cal.business_days_between(date(2026, 12, 23), date(2026, 12, 26)) == 1


def test_fuso_da_b3_e_utc_menos_3_fixo() -> None:
    """DST abolido em 2019: offset constante, sem tzdata."""
    from datetime import datetime, timedelta

    verao = datetime(2026, 1, 15, 12, 0, tzinfo=B3_UTC_OFFSET)
    inverno = datetime(2026, 7, 15, 12, 0, tzinfo=B3_UTC_OFFSET)
    assert verao.utcoffset() == inverno.utcoffset() == timedelta(hours=-3)

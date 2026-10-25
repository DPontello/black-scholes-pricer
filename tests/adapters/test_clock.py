"""Relógios concretos — contrato tz-aware do port ``Clock``."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from options_engine.adapters.outbound.clock import FixedClock, SystemClock
from options_engine.application.ports.outbound import Clock
from options_engine.domain.model.errors import InvalidDomainValueError


@pytest.mark.parametrize(
    "clock", [SystemClock(), FixedClock(datetime(2026, 7, 3, tzinfo=UTC))], ids=["system", "fixed"]
)
def test_satisfaz_o_protocol_em_runtime(clock: Clock) -> None:
    assert isinstance(clock, Clock)


def test_system_clock_devolve_utc_tz_aware() -> None:
    agora = SystemClock().now()
    assert agora.tzinfo is UTC


def test_system_clock_e_monotonico_nao_decrescente() -> None:
    clock = SystemClock()
    a, b = clock.now(), clock.now()
    assert b >= a


def test_fixed_clock_congela_o_instante() -> None:
    instante = datetime(2026, 7, 3, 14, 0, tzinfo=timezone(timedelta(hours=-3)))
    clock = FixedClock(instante)
    assert clock.now() == clock.now() == instante


def test_fixed_clock_rejeita_instante_naive() -> None:
    with pytest.raises(InvalidDomainValueError):
        FixedClock(datetime(2026, 7, 3, 14, 0))

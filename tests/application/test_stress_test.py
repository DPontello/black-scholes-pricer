"""``StressTestService`` — um snapshot atômico, muitos cenários nomeados."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.inbound import StressTestUseCase
from options_engine.application.use_cases.stress_test import StressTestService
from options_engine.domain.model.errors import ExpiredOptionError, InvalidDomainValueError
from options_engine.domain.model.scenarios import StressScenario
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.engine import apply_scenario, mark_to_model_value
from tests.application._fakes import FakeMarketData, FakeTradingCalendar
from tests.domain._builders import make_condor_legs, make_leg, make_snapshot, make_terms

UTC_MINUS_3 = timezone(timedelta(hours=-3))
INSTANTE_DE_VALORACAO = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)

CENARIOS = (
    StressScenario(label="base"),  # identidade: spot x1, shifts 0
    StressScenario(label="crise", spot_shift=0.80, vol_shift=0.10),
    StressScenario(label="rally", spot_shift=1.15, vol_shift=-0.05),
)


def make_service(
    market_data: FakeMarketData | None = None,
    calendar: FakeTradingCalendar | None = None,
) -> tuple[StressTestService, FakeMarketData]:
    market_data = market_data if market_data is not None else FakeMarketData(make_snapshot())
    service = StressTestService(
        market_data=market_data,
        clock=FixedClock(INSTANTE_DE_VALORACAO),
        calendar=calendar if calendar is not None else FakeTradingCalendar(business_days=118),
        valuation_timezone=UTC_MINUS_3,
    )
    return service, market_data


def _condor() -> Strategy:
    return Strategy.create("condor", make_condor_legs())


def test_service_satisfaz_o_protocol_inbound() -> None:
    service, _ = make_service()
    assert isinstance(service, StressTestUseCase)


def test_report_carrega_base_e_um_outcome_por_cenario_na_ordem() -> None:
    service, market_data = make_service()
    condor = _condor()
    report = service.execute(condor, CENARIOS)
    assert report.strategy_name == condor.name
    assert report.base_snapshot == market_data.snapshot
    assert report.time_to_expiry.year_fraction == 118 / 252
    assert tuple(outcome.scenario for outcome in report.outcomes) == CENARIOS
    # Um único snapshot atômico para o report inteiro.
    assert market_data.requested_symbols == [condor.underlying]


def test_cenario_identidade_reproduz_o_valor_base() -> None:
    """Choque neutro (x1, +0, +0) não muda nada: mesmo caminho aritmético,
    igualdade exata permitida."""
    service, _ = make_service()
    report = service.execute(_condor(), CENARIOS)
    base = report.outcomes[0]
    assert base.value == report.base_value
    assert report.change_from_base(base) == 0.0


def test_valores_batem_com_o_motor_de_simulacao() -> None:
    """O service orquestra; quem calcula é o domínio — valor por valor."""
    service, market_data = make_service()
    report = service.execute(_condor(), CENARIOS)
    for outcome in report.outcomes:
        shocked = apply_scenario(market_data.snapshot, outcome.scenario)
        esperado = mark_to_model_value(
            _condor(), shocked.spot, time_to_expiry=report.time_to_expiry, snapshot=shocked
        )
        assert outcome.value == esperado


def test_lista_vazia_de_cenarios_e_rejeitada() -> None:
    service, _ = make_service()
    with pytest.raises(InvalidDomainValueError):
        service.execute(_condor(), ())


def test_estrutura_vencida_dispara_expired_option_error() -> None:
    service, market_data = make_service()
    ontem = INSTANTE_DE_VALORACAO.date() - timedelta(days=1)
    vencida = Strategy.create(
        "call seca vencida", [make_leg(terms=make_terms(expiry=ontem), premium=0.5)]
    )
    with pytest.raises(ExpiredOptionError):
        service.execute(vencida, CENARIOS)
    # A guarda dispara DEPOIS do snapshot (o símbolo vem da estrutura), mas
    # nenhum valor é calculado — o report nem chega a nascer.
    assert market_data.requested_symbols == [vencida.underlying]


def test_estrutura_no_dia_do_vencimento_vale_o_intrinseco_descontado() -> None:
    """tau = 0 dentro do report: células viram intrínseco descontado
    (decisão nº 5) — valores finitos, report construível, nunca NaN."""
    service, _ = make_service(calendar=FakeTradingCalendar(business_days=0))
    report = service.execute(_condor(), CENARIOS)
    assert report.time_to_expiry.year_fraction == 0.0
    assert all(isinstance(outcome.value, float) for outcome in report.outcomes)

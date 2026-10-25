"""``StressTestService`` — implementação do contrato ``StressTestUseCase``.

Um snapshot ATÔMICO, muitos cenários: a foto de mercado é obtida UMA vez e
cada cenário nomeado a choca via ``apply_scenario`` (VO puro em, VO puro
fora). Os valores vêm do motor de simulação (kernel), não de um
``PricingModel`` — por isso o ``StressTestReport`` não carrega ``model_id``
(consistente com ``StressGridResult``).
"""

from collections.abc import Sequence
from datetime import tzinfo

from options_engine.application.ports.outbound import Clock, MarketDataPort, TradingCalendar
from options_engine.application.use_cases._time import resolve_time_to_expiry, valuation_date
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.scenarios import (
    ScenarioOutcome,
    StressScenario,
    StressTestReport,
)
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.engine import apply_scenario, mark_to_model_value

__all__ = ["StressTestService"]


class StressTestService:
    """Valor mark-to-model BRUTO da estrutura sob cenários nomeados.

    Mesma política de valoração do ``PriceOptionService``: ``day_count`` e
    ``valuation_timezone`` no construtor (decisão do composition root), tau
    resolvido pelo helper único de tempo — vencida → ``ExpiredOptionError``,
    no próprio dia → tau = 0 e intrínseco descontado (decisão nº 5).
    """

    def __init__(
        self,
        market_data: MarketDataPort,
        clock: Clock,
        calendar: TradingCalendar,
        *,
        valuation_timezone: tzinfo,
        day_count: DayCountConvention = DayCountConvention.BUSINESS_252,
    ) -> None:
        self._market_data = market_data
        self._clock = clock
        self._calendar = calendar
        self._valuation_timezone = valuation_timezone
        self._day_count = day_count

    def execute(self, strategy: Strategy, scenarios: Sequence[StressScenario]) -> StressTestReport:
        snapshot = self._market_data.get_snapshot(strategy.underlying)
        as_of = valuation_date(self._clock, self._valuation_timezone)
        time_to_expiry = resolve_time_to_expiry(
            strategy.expiry, as_of, self._calendar, self._day_count
        )
        base_value = mark_to_model_value(
            strategy, snapshot.spot, time_to_expiry=time_to_expiry, snapshot=snapshot
        )
        outcomes = []
        for scenario in scenarios:
            shocked = apply_scenario(snapshot, scenario)
            outcomes.append(
                ScenarioOutcome(
                    scenario=scenario,
                    value=mark_to_model_value(
                        strategy, shocked.spot, time_to_expiry=time_to_expiry, snapshot=shocked
                    ),
                )
            )
        # Lista vazia de cenários morre aqui: o VO exige >= 1 outcome —
        # um relatório de estresse vazio é pergunta sem resposta, não dado.
        return StressTestReport(
            strategy_name=strategy.name,
            base_snapshot=snapshot,
            time_to_expiry=time_to_expiry,
            base_value=base_value,
            outcomes=tuple(outcomes),
        )

"""Ports inbound (driving) — os contratos que os adapters de borda consomem.

Os adapters inbound (CLI hoje, FastAPI na Sprint 4) dependem APENAS destes
Protocols: o endpoint HTTP será ~10 linhas de tradução DTO -> command —
prova concreta de que o framework é adapter, não fundação (ARCH §4.2).

Emenda de 2026-07-04 ao ARCH §4.2 (painel de design da Sprint 3):

- ``PriceOptionCommand`` NÃO carrega ``underlying_symbol`` como campo — os
  termos já o contêm, e um campo redundante seria uma segunda fonte de
  verdade que o ``PricingRequest`` teria de reconciliar. A property derivada
  preserva a conveniência do acesso.
- ``AnalyzeStrategyPayoffUseCase`` recebe ``SpotAxis`` (eixo 1D), não
  ``ScenarioGrid`` (2D): payoff no vencimento não tem eixo de vol — exigir
  um grid completo forçaria todo chamador a inventar um eixo fantasma.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.results import PayoffProfile, PricingResult
from options_engine.domain.model.scenarios import SpotAxis, StressScenario, StressTestReport
from options_engine.domain.model.strategy import Strategy

__all__ = [
    "AnalyzeStrategyPayoffUseCase",
    "PriceOptionCommand",
    "PriceOptionUseCase",
    "StressTestUseCase",
]


@dataclass(frozen=True, slots=True)
class PriceOptionCommand:
    """Pedido de precificação de UMA opção — apenas os termos econômicos.

    O snapshot e o tau NÃO entram aqui: são resolvidos pelo use case via
    ports (``MarketDataPort``, ``Clock``, ``TradingCalendar``) — o chamador
    de borda pede "precifique estes termos", não "precifique com este
    mercado".
    """

    terms: OptionTerms

    @property
    def underlying_symbol(self) -> str:
        """Símbolo do subjacente, derivado dos termos (fonte única de verdade)."""
        return self.terms.underlying


@runtime_checkable
class PriceOptionUseCase(Protocol):
    """Precifica uma opção europeia com dados de mercado atuais."""

    def execute(self, command: PriceOptionCommand) -> PricingResult: ...


@runtime_checkable
class AnalyzeStrategyPayoffUseCase(Protocol):
    """Perfil de payoff/P&L no vencimento sobre um eixo de spots.

    Retorna ``payoff_at_expiry`` (bruto) sempre; ``pnl`` (líquido) apenas
    quando todas as legs têm prêmio informado (decisão ratificada nº 4).
    """

    def execute(self, strategy: Strategy, axis: SpotAxis) -> PayoffProfile: ...


@runtime_checkable
class StressTestUseCase(Protocol):
    """Valor mark-to-model da estrutura sob cenários nomeados."""

    def execute(
        self, strategy: Strategy, scenarios: Sequence[StressScenario]
    ) -> StressTestReport: ...

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

from collections.abc import Collection, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from math import isfinite
from typing import Protocol, runtime_checkable

from options_engine.application.ports.outbound import CadastroFreshness
from options_engine.domain.income.costs import REFERENCE_POSITION_SHARES
from options_engine.domain.income.metrics import IncomeStructure
from options_engine.domain.income.ranking import IncomeRanking, RankingCriterion
from options_engine.domain.model.chain import RejectedSeries
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.profile import Profile, ProfileEntry
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.model.results import PayoffProfile, PricingResult
from options_engine.domain.model.scenarios import SpotAxis, StressScenario, StressTestReport
from options_engine.domain.model.strategy import Strategy

__all__ = [
    "AnalyzeStrategyPayoffUseCase",
    "ChainView",
    "ExpiryBlock",
    "ExpiryOption",
    "MarketStatus",
    "MarketViewUseCase",
    "PriceOptionCommand",
    "PriceOptionUseCase",
    "ProfileUseCase",
    "RankIncomeCommand",
    "RankIncomeOpportunitiesUseCase",
    "SeriesRow",
    "StressTestUseCase",
    "WatchRow",
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
    """Precifica uma opção com dados de mercado atuais.

    Europeia exata; call americana como aproximação europeia marcada no
    resultado (ADR-0002, com taxa >= 0); put americana rejeitada.
    """

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


@dataclass(frozen=True, slots=True)
class RankIncomeCommand:
    """Pedido do painel de renda (plano da fase 2 §3.3) — defaults decididos pela mesa.

    - ``underlyings``: a lista do usuário, na ordem dele; repetido é erro.
    - ``structures``: as três por default (put coberta, venda coberta e
      trava de crédito, com put e com call).
    - ``delta_min``/``delta_max``: faixa do MÓDULO do delta da perna vendida,
      0,15 a 0,35.
    - ``expiries``: os N próximos vencimentos com du >= 0 (default 2).
    - ``min_trades`` e ``max_spread_pct``: filtros de liquidez SEM default;
      ``max_spread_pct`` em decimal ((ask - bid) / mid; 0.10 == 10%).
    - ``sort_by``: default rendimento anualizado LÍQUIDO.
    - ``reference_shares``: 100 ações por estrutura.
    - ``spread_width_steps``: a perna comprada da trava é o k-ésimo strike
      seguinte mais fora do dinheiro, mesmo tipo e vencimento (técnico).
    """

    underlyings: tuple[str, ...]
    structures: frozenset[IncomeStructure] = field(
        default_factory=lambda: frozenset(IncomeStructure)
    )
    delta_min: float = 0.15
    delta_max: float = 0.35
    expiries: int = 2
    min_trades: int | None = None
    max_spread_pct: float | None = None
    sort_by: RankingCriterion = RankingCriterion.NET_ANNUAL_YIELD
    reference_shares: int = REFERENCE_POSITION_SHARES
    spread_width_steps: int = 1

    def __post_init__(self) -> None:
        if not self.underlyings or any(not s.strip() for s in self.underlyings):
            raise InvalidDomainValueError("o painel exige ao menos um ativo, sem nomes vazios")
        if len(set(self.underlyings)) != len(self.underlyings):
            raise InvalidDomainValueError(f"ativo repetido em {self.underlyings!r}")
        if not self.structures:
            raise InvalidDomainValueError("o painel exige ao menos uma estrutura")
        if not (0.0 <= self.delta_min <= self.delta_max <= 1.0):
            raise InvalidDomainValueError(
                f"faixa de delta exige 0 <= mínimo <= máximo <= 1; recebido "
                f"{self.delta_min!r} a {self.delta_max!r}"
            )
        inteiros = {
            "expiries": (self.expiries, 1),
            "reference_shares": (self.reference_shares, 1),
            "spread_width_steps": (self.spread_width_steps, 1),
        }
        for nome, (valor, minimo) in inteiros.items():
            if valor < minimo:
                raise InvalidDomainValueError(f"{nome} deve ser >= {minimo}; recebido {valor!r}")
        if self.min_trades is not None and self.min_trades < 0:
            raise InvalidDomainValueError(f"min_trades deve ser >= 0; recebido {self.min_trades!r}")
        if self.max_spread_pct is not None and not (
            isfinite(self.max_spread_pct) and self.max_spread_pct > 0.0
        ):
            raise InvalidDomainValueError(
                f"max_spread_pct deve ser finito e > 0; recebido {self.max_spread_pct!r}"
            )


@runtime_checkable
class RankIncomeOpportunitiesUseCase(Protocol):
    """Ranking das oportunidades de renda do pregão: venda coberta, put coberta e travas."""

    def execute(self, command: RankIncomeCommand) -> IncomeRanking: ...


@runtime_checkable
class ProfileUseCase(Protocol):
    """Perfis do app: quem está usando, a watchlist dele e a trava entre PCs.

    ``open`` trava o perfil para este PC (outro PC com trava recente →
    ``ProfileLockedError``, a menos que ``force``); ``close`` solta a trava.
    ``active`` e ``set_watchlist`` exigem perfil aberto (``NoActiveProfileError``).
    """

    def list(self) -> tuple[ProfileEntry, ...]: ...

    def create(self, name: str, folder: str) -> Profile: ...

    def open(self, name: str, force: bool = False) -> Profile: ...

    def active(self) -> Profile: ...

    def set_watchlist(self, tickers: Sequence[str]) -> Profile: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class WatchRow:
    """Exatamente um dos dois: ``quote`` ou ``reason``."""

    symbol: str
    quote: UnderlyingQuote | None
    reason: str | None

    def __post_init__(self) -> None:
        if (self.quote is None) == (self.reason is None):
            raise InvalidDomainValueError(
                f"linha de {self.symbol!r} precisa de cotação OU motivo, nunca dos dois ou nenhum"
            )


@dataclass(frozen=True, slots=True)
class SeriesRow:
    symbol: str
    option_type: OptionType
    strike: float
    exercise_style: ExerciseStyle
    bid: float | None
    ask: float | None
    last: float | None
    trades: int
    volume: float
    implied_vol: float | None
    delta: float | None


@dataclass(frozen=True, slots=True)
class ExpiryBlock:
    expiry: date
    business_days: int
    rows: tuple[SeriesRow, ...]


@dataclass(frozen=True, slots=True)
class ExpiryOption:
    expiry: date
    business_days: int
    weekly: bool


@dataclass(frozen=True, slots=True)
class ChainView:
    """``timestamp``: a cotação do ativo, que é a data de valoração.

    ``expiries``: os blocos dos vencimentos escolhidos; ``available``: os que há para escolher.
    """

    symbol: str
    spot: float
    source: DataSource
    timestamp: datetime
    expiries: tuple[ExpiryBlock, ...]
    rejected: tuple[RejectedSeries, ...]
    available: tuple[ExpiryOption, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketStatus:
    """Sem ``cadastro``, ``cadastro_reason`` diz por quê."""

    source: DataSource
    cadastro: CadastroFreshness | None
    cadastro_reason: str | None
    cotahist_range: tuple[date, date] | None


@runtime_checkable
class MarketViewUseCase(Protocol):
    """``chain`` levanta ``UnknownSymbolError`` ou ``UnderlyingUnavailableError``; ``quotes``
    nunca levanta por ativo: o motivo vai na linha.

    ``expiries`` ``None`` é a escolha padrão: o vencimento mais próximo e o próximo mensal."""

    def follow(
        self,
        watchlist: Sequence[str],
        chain_symbol: str | None,
        expiries: Collection[date] | None = None,
    ) -> None: ...

    def quotes(self, watchlist: Sequence[str]) -> tuple[WatchRow, ...]: ...

    def chain(self, symbol: str, expiries: Collection[date] | None = None) -> ChainView: ...

    def status(self) -> MarketStatus: ...

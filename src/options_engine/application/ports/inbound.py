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
from enum import Enum
from math import isfinite
from pathlib import Path
from typing import Protocol, runtime_checkable

from options_engine.application.ports.outbound import CadastroFreshness
from options_engine.domain.analytics.volatility import DailyVol, VolContext
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.income.costs import REFERENCE_POSITION_SHARES
from options_engine.domain.income.metrics import IncomeStructure
from options_engine.domain.income.ranking import IncomeRanking, RankingCriterion
from options_engine.domain.model.chain import RejectedSeries
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.profile import Profile, ProfileEntry
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.model.results import Greeks, PayoffProfile, PricingResult
from options_engine.domain.model.scenarios import SpotAxis, StressScenario, StressTestReport
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.model.templates import Template
from options_engine.domain.pricing.smile import SmilePoint
from options_engine.domain.simulation.valuation import ScenarioMatrix

__all__ = [
    "AnalyzeStrategyPayoffUseCase",
    "BuilderAnalysis",
    "BuilderLegInput",
    "BuilderLegView",
    "BuilderRequest",
    "BuilderStockInput",
    "BuilderStockView",
    "ChainView",
    "ExpiryBlock",
    "ExpiryOption",
    "ExpiryPoint",
    "ExpiryResult",
    "LegPriceOrigin",
    "MarketAnalysis",
    "MarketAnalysisUseCase",
    "MarketStatus",
    "MarketViewUseCase",
    "PriceOptionCommand",
    "PriceOptionUseCase",
    "ProfileUseCase",
    "RankIncomeCommand",
    "RankIncomeOpportunitiesUseCase",
    "SeriesRow",
    "SmileView",
    "StrategyBuilderUseCase",
    "StressTestUseCase",
    "TermPoint",
    "TodayResult",
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
    ``active``, ``set_watchlist`` e ``set_book_settings`` exigem perfil aberto
    (``NoActiveProfileError``).
    """

    def list(self) -> tuple[ProfileEntry, ...]: ...

    def create(self, name: str, folder: str) -> Profile: ...

    def open(self, name: str, force: bool = False) -> Profile: ...

    def active(self) -> Profile: ...

    def active_folder(self) -> Path: ...

    def set_watchlist(self, tickers: Sequence[str]) -> Profile: ...

    def set_book_settings(self, settings: BookSettings) -> Profile: ...

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
    lot: int | None = None


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
    cotahist_business_days: int | None = None


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
        *,
        portfolio_underlyings: Sequence[str] = (),
        portfolio_series: Sequence[str] = (),
    ) -> None: ...

    def quotes(self, watchlist: Sequence[str]) -> tuple[WatchRow, ...]: ...

    def chain(self, symbol: str, expiries: Collection[date] | None = None) -> ChainView: ...

    def status(self) -> MarketStatus: ...


class LegPriceOrigin(Enum):
    """De onde veio o preço da perna no montador (ADR-0004); ``DIGITADO`` é o que o usuário pôs."""

    EXECUTAVEL = "executavel"
    INDICATIVO = "indicativo"
    TEORICO = "teorico"
    DIGITADO = "digitado"
    PRECO_MEDIO = "preco_medio"  # a ação "da carteira", pelo preço médio do perfil


@dataclass(frozen=True, slots=True)
class BuilderLegInput:
    symbol: str
    side: Side
    quantity: int
    price: float | None = None


@dataclass(frozen=True, slots=True)
class BuilderStockInput:
    side: Side
    quantity: int
    origin: StockOrigin
    price: float | None = None


@dataclass(frozen=True, slots=True)
class BuilderRequest:
    """``template``: a chave de um modelo pronto, para conferir a forma e dar o nome."""

    underlying: str
    legs: tuple[BuilderLegInput, ...]
    stock: BuilderStockInput | None = None
    template: str | None = None


@dataclass(frozen=True, slots=True)
class BuilderLegView:
    symbol: str
    option_type: OptionType
    strike: float
    exercise_style: ExerciseStyle
    side: Side
    quantity: int
    lot: int | None
    price: float | None
    origin: LegPriceOrigin | None


@dataclass(frozen=True, slots=True)
class BuilderStockView:
    symbol: str
    side: Side
    quantity: int
    origin: StockOrigin
    price: float | None
    price_origin: LegPriceOrigin | None


@dataclass(frozen=True, slots=True)
class ExpiryPoint:
    """``payoff`` bruto sempre; ``pnl`` e ``net`` só com todas as pernas com preço."""

    spot: float
    payoff: float
    pnl: float | None
    net: float | None


@dataclass(frozen=True, slots=True)
class ExpiryResult:
    """Em moeda. ``max_gain``/``max_loss`` e os ``net_*``: ``None`` = ilimitado."""

    net_premium: float
    breakevens: tuple[float, ...]
    max_gain: float | None
    max_loss: float | None
    net_max_gain: float | None
    net_max_loss: float | None
    setup_costs: float
    income_tax_at_max_gain: float | None
    probability_of_profit: float


@dataclass(frozen=True, slots=True)
class TodayResult:
    curve: tuple[tuple[float, float], ...]
    greeks: Greeks
    grid: ScenarioMatrix
    american_call_approximated: bool


@dataclass(frozen=True, slots=True)
class BuilderAnalysis:
    """``at_expiry`` e ``today`` são ``None`` quando falta preço ou vol; o motivo vai em
    ``warnings`` e em ``today_unavailable``."""

    name: str
    underlying: str
    expiry: date
    business_days: int
    spot: float
    source: DataSource
    timestamp: datetime
    legs: tuple[BuilderLegView, ...]
    stock: BuilderStockView | None
    curve: tuple[ExpiryPoint, ...]
    at_expiry: ExpiryResult | None
    today: TodayResult | None
    today_unavailable: str | None
    warnings: tuple[str, ...]


@runtime_checkable
class StrategyBuilderUseCase(Protocol):
    """``suggest``: as pernas de um modelo pronto com as séries da cadeia (100 x proporção)."""

    def templates(self) -> tuple[Template, ...]: ...

    def suggest(self, underlying: str, template_key: str, expiry: date) -> BuilderRequest: ...

    def analyze(self, request: BuilderRequest) -> BuilderAnalysis: ...


@dataclass(frozen=True, slots=True)
class SmileView:
    """IV de cada série contra o strike (a série fora do dinheiro em cada strike)."""

    expiry: date
    business_days: int
    points: tuple[SmilePoint, ...]


@dataclass(frozen=True, slots=True)
class TermPoint:
    """IV no dinheiro (do smile, no spot) de um vencimento."""

    expiry: date
    business_days: int
    vol: float


@dataclass(frozen=True, slots=True)
class MarketAnalysis:
    """A aba Análise de um ativo: o histórico de fim de dia e o hoje pela cadeia do momento.

    ``history_reason``: por que não há histórico (sem COTAHIST, ativo desconhecido);
    ``today_reason``: por que não há IV 30 de hoje (nenhum vencimento com smile no spot).
    """

    symbol: str
    spot: float
    cdi_annual: float
    history: tuple[DailyVol, ...]
    history_reason: str | None
    today: VolContext | None
    today_reason: str | None
    smiles: tuple[SmileView, ...]
    term_structure: tuple[TermPoint, ...]
    source: DataSource
    timestamp: datetime


@runtime_checkable
class MarketAnalysisUseCase(Protocol):
    def analysis(self, symbol: str) -> MarketAnalysis: ...

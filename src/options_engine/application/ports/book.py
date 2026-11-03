"""Port inbound do book de recomendações (spec da semana 3, §3)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from options_engine.application.ports.inbound import BuilderRequest
from options_engine.domain.analytics.volatility import VolContext
from options_engine.domain.book.direcionais import DirectionalView
from options_engine.domain.book.model import BookExclusion, BookItem
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.model.quotes import DataSource
from options_engine.domain.model.templates import Family

__all__ = ["BookEntry", "BookFamilyView", "BookOutcome", "BookUseCase", "BookView", "UnderlyingVol"]


@dataclass(frozen=True, slots=True)
class BookOutcome:
    """Ganho e perda líquidos de custos e IR no vencimento, em moeda; ``max_loss`` positivo,
    ``None`` = sem limite. A chance de lucro é bruta (sem custos nem IR)."""

    max_gain: float | None
    max_loss: float | None
    probability_of_profit: float


@dataclass(frozen=True, slots=True)
class BookEntry:
    """O item e o pedido pronto para o montador, sem preços: ele reprecifica pela cadeia do
    momento. ``outcome``: ``None`` se a análise do pedido não deu resultado ou se é referência."""

    item: BookItem
    request: BuilderRequest
    outcome: BookOutcome | None = None


@dataclass(frozen=True, slots=True)
class BookFamilyView:
    items: tuple[BookEntry, ...]
    references: tuple[BookEntry, ...]
    exclusions: tuple[BookExclusion, ...]


@dataclass(frozen=True, slots=True)
class UnderlyingVol:
    """Contexto de vol do ativo no fim de dia, ou o motivo de não haver."""

    symbol: str
    context: VolContext | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class BookView:
    """``session``: o pregão do fim de dia varrido (``None`` sem nenhuma cadeia)."""

    session: date | None
    source: DataSource
    contexts: tuple[UnderlyingVol, ...]
    families: Mapping[Family, BookFamilyView]
    unavailable: tuple[BookExclusion, ...]


@runtime_checkable
class BookUseCase(Protocol):
    def book(self, settings: BookSettings, underlyings: Sequence[str]) -> BookView: ...

    def directional(self, settings: BookSettings, view: DirectionalView) -> BookFamilyView:
        """Recusa (``InvalidDomainValueError``) alvo do lado errado ou vencimento sem séries."""
        ...

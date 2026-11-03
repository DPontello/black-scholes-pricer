"""Item do book (spec da semana 3, §3.1): a estrutura, o critério, os números e o porquê.

O porquê é um molde com ``{chave}`` das métricas do item: a formatação dos números para a tela é
do adapter (decisão 8 da Sprint 3), e assim o texto e os números nunca se contradizem.
"""

from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum, unique
from math import isfinite
from string import Formatter
from typing import Final

from options_engine.domain.book.presets import BookSettings
from options_engine.domain.model.chain import LegPremium, PriceQuality, worst_quality
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.templates import Family

__all__ = [
    "ITEMS_PER_STRUCTURE",
    "LOWER_IS_BETTER",
    "BookExclusion",
    "BookItem",
    "BookLabel",
    "BookLeg",
    "BookStock",
    "FamilyResult",
    "Metric",
    "MetricUnit",
    "best_per_structure",
    "passes_liquidity",
]

ITEMS_PER_STRUCTURE: Final = 5
# Critério em que menor é melhor: o custo da proteção e o movimento que a compra de vol precisa.
LOWER_IS_BETTER: Final = frozenset(
    {"straddle_comprado", "strangle_comprado", "put_protetora", "collar"}
)


@unique
class MetricUnit(Enum):
    PERCENT = "percentual"  # decimal: 0.12 == 12%
    CURRENCY = "reais"
    RATIO = "razao"
    STD_DEVS = "desvios"
    BUSINESS_DAYS = "dias_uteis"
    NUMBER = "numero"


@dataclass(frozen=True, slots=True)
class Metric:
    key: str
    label: str
    value: float
    unit: MetricUnit

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise InvalidDomainValueError(f"métrica {self.key!r} não finita: {self.value!r}")


@unique
class BookLabel(Enum):
    SEM_SINAL_CLARO = "sem_sinal_claro"
    NAO_DIRECIONAL = "nao_direcional"
    PERDA_ILIMITADA = "perda_ilimitada"
    POSICAO_HIPOTETICA = "posicao_hipotetica"
    CALL_AMERICANA_COMO_EUROPEIA = "call_americana_como_europeia"
    REGIME_PELA_HV = "regime_pela_hv"
    IV_EXTRAPOLADA = "iv_extrapolada"


@dataclass(frozen=True, slots=True)
class BookLeg:
    symbol: str
    option_type: OptionType
    strike: float
    side: Side
    quantity: int
    premium: LegPremium


@dataclass(frozen=True, slots=True)
class BookStock:
    side: Side
    quantity: int
    origin: StockOrigin


@dataclass(frozen=True, slots=True)
class BookItem:
    """Uma recomendação; ``reason`` cita as métricas por ``{chave}`` (ver ``render_reason``)."""

    family: Family
    template_key: str
    underlying: str
    expiry: date
    business_days: int
    legs: tuple[BookLeg, ...]
    stock: BookStock | None
    criterion: Metric
    metrics: tuple[Metric, ...]
    reason: str
    labels: tuple[BookLabel, ...] = ()

    def __post_init__(self) -> None:
        if not self.legs:
            raise InvalidDomainValueError("item do book exige ao menos uma perna")
        chaves = [m.key for m in self.all_metrics]
        if len(set(chaves)) != len(chaves):
            raise InvalidDomainValueError(f"métricas repetidas no item: {chaves!r}")
        citadas = {campo for _, campo, _, _ in Formatter().parse(self.reason) if campo}
        if not citadas <= set(chaves):
            raise InvalidDomainValueError(
                f"o porquê cita {sorted(citadas - set(chaves))!r}, que não são métricas do item"
            )

    @property
    def all_metrics(self) -> tuple[Metric, ...]:
        return (self.criterion, *self.metrics)

    @property
    def quality(self) -> PriceQuality:
        return worst_quality(leg.premium.quality for leg in self.legs)

    def render_reason(self, fmt: Callable[[Metric], str]) -> str:
        return self.reason.format_map({m.key: fmt(m) for m in self.all_metrics})

    def tie_break(self) -> tuple[str, date, tuple[float, ...]]:
        return (self.underlying, self.expiry, tuple(leg.strike for leg in self.legs))


@dataclass(frozen=True, slots=True)
class BookExclusion:
    """O que ficou fora por dado ruim (ativo, série ou estrutura) e por quê."""

    symbol: str
    reason: str


@dataclass(frozen=True, slots=True)
class FamilyResult:
    """Itens (só EXECUTAVEL), referências (INDICATIVO e TEORICO) e exclusões de uma família."""

    items: tuple[BookItem, ...] = ()
    references: tuple[BookItem, ...] = ()
    exclusions: tuple[BookExclusion, ...] = ()

    def __post_init__(self) -> None:
        if any(i.quality is not PriceQuality.EXECUTAVEL for i in self.items):
            raise InvalidDomainValueError("o book só aceita itens EXECUTAVEL (ADR-0004)")
        if any(i.quality is PriceQuality.EXECUTAVEL for i in self.references):
            raise InvalidDomainValueError("referências são só INDICATIVO e TEORICO")

    @classmethod
    def of(
        cls, candidates: Iterable[BookItem], exclusions: Iterable[BookExclusion] = ()
    ) -> "FamilyResult":
        """Separa por qualidade e fica com os melhores de cada estrutura pelo critério."""
        todos = tuple(candidates)
        return cls(
            best_per_structure(c for c in todos if c.quality is PriceQuality.EXECUTAVEL),
            best_per_structure(c for c in todos if c.quality is not PriceQuality.EXECUTAVEL),
            tuple(dict.fromkeys(exclusions)),
        )

    @classmethod
    def combine(cls, *parts: "FamilyResult") -> "FamilyResult":
        """Junta resultados (de vários ativos) e refaz a escolha dos melhores por estrutura."""
        return cls.of(
            (i for p in parts for i in (*p.items, *p.references)),
            (e for p in parts for e in p.exclusions),
        )


def best_per_structure(
    items: Iterable[BookItem], *, limit: int = ITEMS_PER_STRUCTURE
) -> tuple[BookItem, ...]:
    """Os ``limit`` melhores de cada estrutura pelo critério (maior primeiro, menor nas
    ``LOWER_IS_BETTER``), com desempate por ativo, vencimento e strikes; estruturas na ordem em
    que aparecem."""
    por_estrutura: dict[str, list[BookItem]] = defaultdict(list)
    for item in items:
        por_estrutura[item.template_key].append(item)

    def chave(item: BookItem) -> tuple[float, tuple[str, date, tuple[float, ...]]]:
        sinal = 1.0 if item.template_key in LOWER_IS_BETTER else -1.0
        return sinal * item.criterion.value, item.tie_break()

    return tuple(
        item for grupo in por_estrutura.values() for item in sorted(grupo, key=chave)[:limit]
    )


def passes_liquidity(trades: int, spread_pct: float | None, settings: BookSettings) -> bool:
    """Negócios no pregão e spread do preset; sem os dois lados do book não há spread a medir."""
    return (
        trades >= settings.min_trades
        and spread_pct is not None
        and spread_pct <= settings.max_spread_pct
    )

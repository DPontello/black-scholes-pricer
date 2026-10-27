"""Resultado do ranking de oportunidades de renda — VOs e ordenação pura (plano da fase 2 §3.3).

O painel só apresenta: tudo o que ele mostra já sai daqui decidido —
qualidade da estrutura (a pior entre as pernas, ADR-0004), separação entre o
ranking (só EXECUTAVEL) e as referências (INDICATIVO e TEORICO, sempre
rotuladas, nunca no ranking), ordem pelo critério com desempate
determinístico e exclusões com motivo.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import Enum, unique

from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.income.metrics import IncomeMetrics, IncomeStructure
from options_engine.domain.model.chain import LegPremium, PriceQuality, worst_quality
from options_engine.domain.model.conventions import RiskFreeRate
from options_engine.domain.model.enums import (
    ExerciseStyle,
    OptionType,
    PricingApproximation,
    Side,
)
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "CandidateLeg",
    "Exclusion",
    "ExclusionScope",
    "IncomeCandidate",
    "IncomeRanking",
    "RankingCriterion",
    "UnderlyingSummary",
    "rank_candidates",
]


@unique
class RankingCriterion(Enum):
    """Critério de ordenação do ranking; o default da mesa é o anualizado LÍQUIDO."""

    NET_ANNUAL_YIELD = "anual-liquido"
    GROSS_ANNUAL_YIELD = "anual-bruto"
    NET_PERIOD_YIELD = "periodo-liquido"
    GROSS_PERIOD_YIELD = "periodo-bruto"
    NET_EXCESS_OVER_CDI = "excesso-cdi-liquido"

    def value_of(self, metrics: IncomeMetrics) -> float | None:
        """O número que ordena; ``None`` (vencimento hoje, sem anualização) vai por último."""
        valores = {
            RankingCriterion.NET_ANNUAL_YIELD: metrics.net_yield_annual_252,
            RankingCriterion.GROSS_ANNUAL_YIELD: metrics.yield_annual_252,
            RankingCriterion.NET_PERIOD_YIELD: metrics.net_yield_period,
            RankingCriterion.GROSS_PERIOD_YIELD: metrics.yield_period,
            RankingCriterion.NET_EXCESS_OVER_CDI: metrics.net_excess_over_cdi_annual_252,
        }
        return valores[self]


@unique
class ExclusionScope(Enum):
    """Nível em que a exclusão aconteceu."""

    UNDERLYING = "ativo"
    SERIES = "serie"
    STRUCTURE = "estrutura"


@dataclass(frozen=True, slots=True)
class Exclusion:
    """O que ficou fora do painel e por quê — exclusão silenciosa esconderia problema de dado."""

    scope: ExclusionScope
    symbol: str
    reason: str

    def __post_init__(self) -> None:
        if not self.symbol.strip() or not self.reason.strip():
            raise InvalidDomainValueError(
                f"exclusão exige símbolo e motivo; recebido {self.symbol!r}, {self.reason!r}"
            )


@dataclass(frozen=True, slots=True)
class CandidateLeg:
    """Uma perna de candidato, com o prêmio rotulado e o que o painel mostra dela.

    ``delta`` e ``exercise_probability`` (N(d2) na call, N(-d2) na put —
    probabilidade RISCO-NEUTRA de exercício) com a vol da própria série,
    senão a do smile; ``implied_vol`` é a da própria série (mid), se houver.
    ``spread_pct`` = (ask - bid) / mid, só com book completo. ``volume`` é
    financeiro, na moeda do subjacente.
    """

    symbol: str
    option_type: OptionType
    side: Side
    strike: float
    expiry: date
    exercise_style: ExerciseStyle
    premium: LegPremium
    delta: float
    exercise_probability: float
    implied_vol: float | None
    trades: int
    volume: float
    spread_pct: float | None

    @property
    def approximation(self) -> PricingApproximation | None:
        """Marca da ADR-0002: call americana precificada como europeia."""
        if self.option_type is OptionType.CALL and self.exercise_style is ExerciseStyle.AMERICAN:
            return PricingApproximation.AMERICAN_CALL_AS_EUROPEAN
        return None


@dataclass(frozen=True, slots=True)
class IncomeCandidate:
    """Uma oportunidade montada: estrutura, pernas (vendida primeiro) e métricas."""

    underlying: str
    structure: IncomeStructure
    expiry: date
    legs: tuple[CandidateLeg, ...]
    metrics: IncomeMetrics
    underlying_book_available: bool

    def __post_init__(self) -> None:
        if not self.legs:
            raise InvalidDomainValueError("candidato exige ao menos uma perna")

    @property
    def quality(self) -> PriceQuality:
        """A estrutura vale o que vale a perna mais fraca (ADR-0004)."""
        return worst_quality(leg.premium.quality for leg in self.legs)

    @property
    def approximations(self) -> tuple[PricingApproximation, ...]:
        marcas = {leg.approximation for leg in self.legs}
        return tuple(sorted((m for m in marcas if m is not None), key=lambda m: m.value))

    def tie_break(self) -> tuple[str, str, date, tuple[float, ...]]:
        """Desempate determinístico: ativo, estrutura, vencimento, strikes."""
        return (
            self.underlying,
            self.structure.value,
            self.expiry,
            tuple(leg.strike for leg in self.legs),
        )


@dataclass(frozen=True, slots=True)
class UnderlyingSummary:
    """O ativo-objeto como o painel o mostra: pregão, spot, vol realizada, CDI e custos."""

    symbol: str
    session: date
    spot: float
    realized_vol: float
    book_available: bool
    cdi: RiskFreeRate
    cost_schedule: CostSchedule


@dataclass(frozen=True, slots=True)
class IncomeRanking:
    """Resultado do use case: ranking EXECUTAVEL, referências rotuladas e exclusões."""

    criterion: RankingCriterion
    ranked: tuple[IncomeCandidate, ...]
    references: tuple[IncomeCandidate, ...]
    exclusions: tuple[Exclusion, ...]
    underlyings: tuple[UnderlyingSummary, ...]

    def __post_init__(self) -> None:
        if any(c.quality is not PriceQuality.EXECUTAVEL for c in self.ranked):
            raise InvalidDomainValueError("o ranking só aceita estruturas EXECUTAVEL (ADR-0004)")
        if any(c.quality is PriceQuality.EXECUTAVEL for c in self.references):
            raise InvalidDomainValueError("referências são só INDICATIVO e TEORICO")


def _chave(
    criterion: RankingCriterion, candidato: IncomeCandidate
) -> tuple[bool, float, tuple[str, str, date, tuple[float, ...]]]:
    # IncomeMetrics já garante finitude: só o None (vencimento hoje) precisa de regra.
    valor = criterion.value_of(candidato.metrics)
    return (valor is None, -(valor if valor is not None else 0.0), candidato.tie_break())


def rank_candidates(
    candidates: Iterable[IncomeCandidate], criterion: RankingCriterion
) -> tuple[tuple[IncomeCandidate, ...], tuple[IncomeCandidate, ...]]:
    """(ranking EXECUTAVEL, referências), ambos do maior para o menor pelo critério.

    ``None`` por último; empates pelo desempate determinístico do candidato.
    """
    ordenados = sorted(candidates, key=lambda c: _chave(criterion, c))
    executaveis = tuple(c for c in ordenados if c.quality is PriceQuality.EXECUTAVEL)
    referencias = tuple(c for c in ordenados if c.quality is not PriceQuality.EXECUTAVEL)
    return executaveis, referencias

"""StrategyLeg (VO) e Strategy (Aggregate Root, padrão Composite).

Maior risco do projeto (ROADMAP, Sprint 2): erro de sinal/direção das legs
inverte P&L silenciosamente. A defesa é estrutural — ``quantity > 0`` sempre
e direção exclusivamente no enum ``Side``; ``SELL/-10`` é irrepresentável.

O motor trata qualquer estrutura uniformemente como soma ponderada
(``side.sign * quantity``) — nenhum ``isinstance`` em lugar nenhum; a
estrutura é dados, não subclasse. Iron Condor = 4 legs, Straddle = 2,
opção seca = 1.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from math import isfinite

from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import (
    EmptyStrategyError,
    InvalidDomainValueError,
    MixedExpiryError,
    MixedUnderlyingError,
)

__all__ = ["Strategy", "StrategyLeg"]


@dataclass(frozen=True, slots=True)
class StrategyLeg:
    """Perna de uma estrutura: termos + ticker + direção + quantidade + prêmio.

    ``symbol`` é o ticker do contrato (rastreabilidade); ``terms`` é a cópia
    dos termos econômicos para o cálculo puro — autorizada porque atributos
    de contrato listado são imutáveis pós-listagem (ARCH §2.2).

    ``premium`` é o prêmio UNITÁRIO (por contrato, na moeda do subjacente),
    opcional e informado pelo chamador (decisão nº 4): sem ele, apenas o
    payoff bruto é calculável.
    """

    symbol: str
    terms: OptionTerms
    side: Side
    quantity: int
    premium: float | None = None

    def __post_init__(self) -> None:
        if not self.symbol:
            raise InvalidDomainValueError("symbol da leg não pode ser vazio")
        if self.quantity < 1:
            raise InvalidDomainValueError(
                f"quantity deve ser >= 1 — direção vive em Side, nunca em "
                f"quantidade negativa (CONVENTIONS §4); recebido {self.quantity!r}"
            )
        if self.premium is not None and not (isfinite(self.premium) and self.premium >= 0.0):
            raise InvalidDomainValueError(
                f"premium deve ser finito e >= 0 quando informado; recebido {self.premium!r}"
            )

    @property
    def signed_quantity(self) -> int:
        """Exposição assinada: ``side.sign * quantity`` (CONVENTIONS §4)."""
        return self.side.sign * self.quantity

    def mirrored(self) -> "StrategyLeg":
        """Mesma leg com o lado invertido — base da propriedade short == -long."""
        return replace(self, side=self.side.opposite)


@dataclass(frozen=True, slots=True)
class Strategy:
    """Aggregate Root: estrutura multi-leg validada por completo na construção.

    Sem ``add_leg`` mutável no MVP — a raiz nasce consistente ou não nasce.
    Invariantes ratificadas (decisão nº 6, restrições de fase reversíveis):
    mesmo subjacente e mesmo vencimento em todas as legs.
    """

    name: str
    legs: tuple[StrategyLeg, ...]

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidDomainValueError("name da estrutura não pode ser vazio")
        if len(self.legs) == 0:
            raise EmptyStrategyError(f"estrutura {self.name!r} exige ao menos uma leg")
        subjacentes = {leg.terms.underlying for leg in self.legs}
        if len(subjacentes) > 1:
            raise MixedUnderlyingError(
                f"estrutura {self.name!r} mistura subjacentes {sorted(subjacentes)!r} "
                f"(decisão nº 6: cross-asset é extensão futura)"
            )
        vencimentos = {leg.terms.expiry for leg in self.legs}
        if len(vencimentos) > 1:
            raise MixedExpiryError(
                f"estrutura {self.name!r} mistura vencimentos {sorted(vencimentos)!r} "
                f"(decisão nº 6: calendar spreads são extensão futura)"
            )

    @classmethod
    def create(cls, name: str, legs: Sequence[StrategyLeg]) -> "Strategy":
        """Porta de entrada canônica — normaliza a sequência e valida tudo."""
        return cls(name=name, legs=tuple(legs))

    @property
    def underlying(self) -> str:
        """Subjacente único da estrutura (garantido pela invariante)."""
        return self.legs[0].terms.underlying

    @property
    def expiry(self) -> date:
        """Vencimento único da estrutura (garantido pela invariante)."""
        return self.legs[0].terms.expiry

    @property
    def has_premiums(self) -> bool:
        """True se TODAS as legs têm prêmio — pré-condição de ``pnl`` (decisão nº 4)."""
        return all(leg.premium is not None for leg in self.legs)

    def mirrored(self, name: str | None = None) -> "Strategy":
        """Estrutura espelhada (todos os lados invertidos) — short == -long."""
        return Strategy(
            name=name if name is not None else f"{self.name} (espelhada)",
            legs=tuple(leg.mirrored() for leg in self.legs),
        )

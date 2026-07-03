"""Convenções de unidade como Value Objects — day count, capitalização, bases.

Convenção divergente é a fonte nº 1 de "falso bug" em pricing (CONVENTIONS
§preâmbulo): estes VOs carregam a convenção JUNTO do valor, de modo que
misturar bases (vol 252 com tau 365, CDI direto no kernel) deixe de ser um
preço silenciosamente errado e vire um erro de tipo ou uma exceção tipada.
"""

from dataclasses import dataclass
from enum import Enum, unique
from math import isfinite, log1p

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "Compounding",
    "DayCountConvention",
    "RiskFreeRate",
    "TimeToExpiry",
    "Volatility",
]


@unique
class DayCountConvention(Enum):
    """Base de contagem de dias — NUNCA um ``252`` hardcoded (decisão nº 1).

    ``BUSINESS_252`` é o default ratificado pela mesa (aderência B3/CDI);
    ``CALENDAR_365`` existe para validação contra a literatura (Hull publica
    em anos calendário). O default se materializa como parâmetro default nas
    fronteiras que convertem dias — jamais como constante enterrada.
    """

    BUSINESS_252 = 252
    CALENDAR_365 = 365

    @property
    def days_per_year(self) -> int:
        return self.value


@unique
class Compounding(Enum):
    """Regime de capitalização de uma taxa — parte inseparável do valor.

    Black-Scholes assume capitalização contínua; o CDI é cotado como taxa
    efetiva anual em base 252 dias úteis. Taxa como ``float`` nu é proibida
    em qualquer port (CONVENTIONS §3) exatamente porque estes dois números
    não são intercambiáveis.
    """

    CONTINUOUS = "continuous"
    BUSINESS_DAILY_252 = "business_daily_252"


@dataclass(frozen=True, slots=True)
class RiskFreeRate:
    """Taxa livre de risco anual, decimal, com regime de capitalização explícito.

    ``rate`` é decimal (0.1365 == 13.65% a.a.). A conversão para contínua —
    exigida pelo kernel — é método explícito e testável, nunca uma linha
    enterrada num adapter (CONVENTIONS §3).
    """

    rate: float
    compounding: Compounding

    def __post_init__(self) -> None:
        if not isfinite(self.rate):
            raise InvalidDomainValueError(f"taxa deve ser finita; recebido {self.rate!r}")
        # Taxas negativas moderadas são legais (o core não pode quebrar com
        # r < 0 — VV-PLAN §3), mas abaixo de -100% a.a. não há semântica
        # econômica e ln(1 + r) deixa de existir.
        if not (self.rate > -1.0):
            raise InvalidDomainValueError(
                f"taxa deve ser > -1.0 (-100% a.a.); recebido {self.rate!r}"
            )

    def as_continuous(self) -> float:
        """Taxa em capitalização contínua: ``r_cont = ln(1 + r_efetiva)``.

        ``log1p`` em vez de ``log(1 + r)``: para taxas pequenas, ``1 + r``
        descarta dígitos de r antes do log; ``log1p`` preserva a precisão.
        """
        if self.compounding is Compounding.CONTINUOUS:
            return self.rate
        return log1p(self.rate)


@dataclass(frozen=True, slots=True)
class Volatility:
    """Volatilidade anualizada, decimal (0.20 == 20%), com base explícita.

    Mesma disciplina da taxa: vol como ``float`` nu repetiria o erro que o
    ``RiskFreeRate`` existe para impedir. A base de anualização DEVE casar
    com a do tau usado no pricing — o motor verifica (CONVENTIONS §2).

    Restrição consciente do MVP: vol flat por subjacente (sem smile) —
    sinalizada, não escondida.
    """

    value: float
    annualization_base: DayCountConvention

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            raise InvalidDomainValueError(f"vol deve ser finita; recebido {self.value!r}")
        # `not (x >= 0)` em vez de `x < 0`: NaN compara False com tudo,
        # logo também seria rejeitado (defesa em profundidade do kernel).
        if not (self.value >= 0.0):
            raise InvalidDomainValueError(f"vol deve ser >= 0; recebido {self.value!r}")


@dataclass(frozen=True, slots=True)
class TimeToExpiry:
    """Tempo até o vencimento em fração de ano + a convenção que o produziu.

    Carregar a convenção é auditoria: impede que um tau em base 252 seja
    usado com vol em base 365 sem ninguém perceber (CONVENTIONS §2). A
    contagem de dias em si (feriados B3) é do ``TradingCalendar`` (Sprint 3);
    aqui vive apenas a conversão contagem -> fração, pura e testável.
    """

    year_fraction: float
    convention: DayCountConvention

    def __post_init__(self) -> None:
        if not isfinite(self.year_fraction):
            raise InvalidDomainValueError(
                f"fração de ano deve ser finita; recebido {self.year_fraction!r}"
            )
        if not (self.year_fraction >= 0.0):
            raise InvalidDomainValueError(
                f"fração de ano deve ser >= 0; recebido {self.year_fraction!r}"
            )

    @classmethod
    def from_days(
        cls,
        days: int,
        convention: DayCountConvention = DayCountConvention.BUSINESS_252,
    ) -> "TimeToExpiry":
        """Converte uma contagem de dias (já na convenção dada) em fração de ano.

        ``days`` são dias ÚTEIS para BUSINESS_252 e corridos para
        CALENDAR_365 — contar é responsabilidade do chamador/calendário.
        """
        if days < 0:
            raise InvalidDomainValueError(f"contagem de dias deve ser >= 0; recebido {days!r}")
        return cls(year_fraction=days / convention.days_per_year, convention=convention)

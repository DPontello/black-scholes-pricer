"""Limites, retrato das operações e os alertas que as regras devolvem."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from math import isfinite
from typing import Final

from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.model import LegState

__all__ = [
    "MAX_EXPIRY_DAYS",
    "MAX_STRIKE_DISTANCE",
    "AfterExpiry",
    "Alert",
    "AlertKind",
    "AlertSettings",
    "Evaluation",
    "OperationSnapshot",
]

MAX_EXPIRY_DAYS: Final = 60
MAX_STRIKE_DISTANCE: Final = 0.20


@dataclass(frozen=True, slots=True)
class AlertSettings:
    """``expiry_days``: dias úteis até o vencimento; ``strike_distance``: fração do strike."""

    expiry_days: int = 5
    strike_distance: float = 0.02

    def __post_init__(self) -> None:
        dias = self.expiry_days
        if isinstance(dias, bool) or not isinstance(dias, int) or not 0 <= dias <= MAX_EXPIRY_DAYS:
            raise InvalidDomainValueError(
                f"dias até o vencimento devem ser inteiros de 0 a {MAX_EXPIRY_DAYS}; "
                f"recebido {dias!r}"
            )
        distancia = self.strike_distance
        if not (isfinite(distancia) and 0.0 <= distancia <= MAX_STRIKE_DISTANCE):
            raise InvalidDomainValueError(
                f"distância do strike deve ficar entre 0 e {MAX_STRIKE_DISTANCE:.0%}; "
                f"recebido {distancia!r}"
            )


class AlertKind(StrEnum):
    """Na ordem de gravidade: a lista sai nessa ordem."""

    EXERCISE_TO_REGISTER = "exercicio_a_registrar"
    STOP = "stop"
    STOP_UNPRICED = "stop_sem_preco"
    EXERCISE_RISK = "risco_de_exercicio"
    EXPIRY_NEAR = "vencimento_proximo"
    AWAITING_CLOSE = "aguardando_fechamento"
    TARGET = "alvo"


def _exige_limite(nome: str, valor: float | None) -> None:
    if valor is not None and not (isfinite(valor) and valor > 0.0):
        raise InvalidDomainValueError(
            f"{nome} deve ser um valor em R$ maior que zero; recebido {valor!r}"
        )


@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    """Uma operação aberta já marcada pela Carteira. ``total``: realizado com custos + não
    realizado pelo preço de zerar; ``None`` quando alguma perna aberta está sem preço de zerar.
    ``stop_loss`` e ``target`` em R$, positivos.

    Sem ``total``: ``estimated_total`` é o mesmo total com o teórico nas pernas cotadas sem o lado
    de zerar (``None`` se falta cotação ou teórico); ``unpriced``, que alguma perna cotada não tem
    nem o lado nem o teórico, e nenhuma está sem cotação."""

    operation_id: str
    name: str
    underlying: str
    legs: tuple[LegState, ...]
    total: float | None
    stop_loss: float | None = None
    target: float | None = None
    estimated_total: float | None = None
    unpriced: bool = False

    def __post_init__(self) -> None:
        _exige_limite("stop", self.stop_loss)
        _exige_limite("alvo", self.target)


@dataclass(frozen=True, slots=True)
class AfterExpiry:
    """Perna depois do pregão do vencimento que não virou pó (o aviso da Carteira)."""

    operation_id: str
    leg: int
    symbol: str
    expiry: date
    outcome: ExpiryOutcome


@dataclass(frozen=True, slots=True)
class Alert:
    """``key`` identifica o alerta entre avaliações (para dispensar): tipo, operação e perna
    (``-`` quando o alerta é da operação inteira). ``estimated``: stop pelo total estimado."""

    key: str
    kind: AlertKind
    operation_id: str
    operation_name: str
    underlying: str
    leg: int | None = None
    symbol: str | None = None
    expiry: date | None = None
    business_days: int | None = None
    in_the_money: bool | None = None
    total: float | None = None
    limit: float | None = None
    can_roll: bool = False
    estimated: bool = False


@dataclass(frozen=True, slots=True)
class Evaluation:
    """``undetermined``: as chaves que não deu para avaliar (sem spot, sem preço de zerar, fora do
    calendário); nem disparam nem contam como "deixou de valer". ``estimated``: as do stop avaliado
    pelo total estimado; disparam, mas também não contam como "deixou de valer"."""

    alerts: tuple[Alert, ...]
    undetermined: frozenset[str]
    estimated: frozenset[str] = frozenset()

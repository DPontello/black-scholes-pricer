"""Alertas do perfil aberto: avaliar a carteira já marcada, dispensar, restaurar e rolar."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from options_engine.application.ports.inbound import BuilderRequest
from options_engine.application.ports.portfolio import ExpiryNotice, PortfolioView
from options_engine.domain.alerts.model import Alert
from options_engine.domain.model.quotes import DataSource

__all__ = ["AlertUseCase", "AlertsView", "RollSuggestion", "RollUseCase"]


@dataclass(frozen=True, slots=True)
class AlertsView:
    """``alerts``: sem os dispensados; ``dismissed``: quantos estão escondidos agora.
    ``source``: a da Carteira (o fim de dia, com o Tryd fechado)."""

    alerts: tuple[Alert, ...]
    dismissed: int
    source: DataSource


@runtime_checkable
class AlertUseCase(Protocol):
    def evaluate(self, view: PortfolioView, notices: Sequence[ExpiryNotice]) -> AlertsView:
        """A carteira e os avisos vêm de quem já os leu (a rota ou o WebSocket): uma consulta de
        mercado só para os dois."""
        ...

    def dismiss(self, key: str) -> None: ...

    def restore_all(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RollSuggestion:
    """A estrutura nova no vencimento seguinte e o caixa de zerar as pernas de opção abertas.

    ``request``: ``None`` sem modelo conhecido ou sem vencimento seguinte na cadeia.
    ``close_cash``: positivo recebe, negativo paga, pelo preço de zerar; ``None`` se alguma perna
    está sem ele.
    """

    operation_id: str
    operation_name: str
    underlying: str
    current_expiry: date
    next_expiry: date | None
    request: BuilderRequest | None
    close_cash: float | None
    source: DataSource


@runtime_checkable
class RollUseCase(Protocol):
    def roll(self, operation_id: str) -> RollSuggestion:
        """Só para operação aberta com opção vendida; nada é enviado nem gravado."""
        ...

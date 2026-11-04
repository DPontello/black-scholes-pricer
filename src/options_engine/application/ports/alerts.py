"""Alertas do perfil aberto: avaliar a carteira já marcada, dispensar e restaurar."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from options_engine.application.ports.portfolio import ExpiryNotice, PortfolioView
from options_engine.domain.alerts.model import Alert
from options_engine.domain.model.quotes import DataSource

__all__ = ["AlertUseCase", "AlertsView"]


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

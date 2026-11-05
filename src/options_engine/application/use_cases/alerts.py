"""``AlertService``: os alertas da carteira já marcada e os dispensados do perfil aberto.

Um dispensado some até o alerta deixar de valer numa avaliação determinada; então a chave sai do
arquivo, e o alerta reaparece se voltar a valer. Sem spot ou sem preço de zerar a chave fica: o
Tryd piscando não faz um alerta dispensado voltar.
"""

import threading
from collections.abc import Callable, Sequence
from datetime import date, tzinfo
from math import fsum

from options_engine.application.ports.alerts import AlertsView
from options_engine.application.ports.outbound import (
    Clock,
    DismissedAlertsRepository,
    MarketPort,
    TradingCalendar,
)
from options_engine.application.ports.portfolio import (
    ExpiryNotice,
    OperationView,
    PortfolioView,
)
from options_engine.domain.alerts.model import AfterExpiry, AlertSettings, OperationSnapshot
from options_engine.domain.alerts.rules import evaluate
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.model import OptionLegRef

__all__ = ["AlertService"]


class AlertService:
    """``dismissed_for`` e ``settings_for`` são chamados a cada uso: o perfil aberto pode ter
    mudado. ``market_timezone``: o fuso da B3, para o "hoje" dos dias úteis."""

    def __init__(
        self,
        dismissed_for: Callable[[], DismissedAlertsRepository],
        settings_for: Callable[[], AlertSettings],
        clock: Clock,
        market_timezone: tzinfo,
        *,
        market: MarketPort,
        calendar: TradingCalendar,
    ) -> None:
        self._dismissed_for = dismissed_for
        self._settings_for = settings_for
        self._clock = clock
        self._tz = market_timezone
        self._market = market
        self._calendar = calendar
        self._lock = threading.Lock()

    def evaluate(self, view: PortfolioView, notices: Sequence[ExpiryNotice]) -> AlertsView:
        settings = self._settings_for()
        hoje = self._clock.now().astimezone(self._tz).date()
        avaliacao = evaluate(
            [_retrato(o) for o in view.operations],
            [AfterExpiry(n.operation_id, n.leg, n.symbol, n.expiry, n.outcome) for n in notices],
            self._spots(view),
            lambda vencimento: self._dias_uteis(hoje, vencimento),
            settings,
        )
        ativas = {a.key for a in avaliacao.alerts}
        with self._lock:
            repositorio = self._dismissed_for()
            dispensados = repositorio.load()
            mantidos = dispensados & (ativas | avaliacao.undetermined)
            if mantidos != dispensados:
                repositorio.save(mantidos)
        visiveis = tuple(a for a in avaliacao.alerts if a.key not in mantidos)
        return AlertsView(visiveis, len(avaliacao.alerts) - len(visiveis), view.source)

    def dismiss(self, key: str) -> None:
        with self._lock:
            repositorio = self._dismissed_for()
            repositorio.save(repositorio.load() | {key})

    def restore_all(self) -> None:
        with self._lock:
            self._dismissed_for().save(frozenset())

    def _spots(self, view: PortfolioView) -> dict[str, float]:
        """Só dos ativos com opção vendida aberta: o único alerta que usa o spot."""
        ativos = sorted(
            {
                o.operation.underlying
                for o in view.operations
                for e in o.legs
                if isinstance(e.ref, OptionLegRef) and e.side is Side.SELL
            }
        )
        spots: dict[str, float] = {}
        for ativo, cotacao in (self._market.get_quotes(ativos) if ativos else {}).items():
            if isinstance(cotacao, str):
                continue
            spot = cotacao.last if cotacao.last is not None else cotacao.previous_close
            if spot is not None:
                spots[ativo] = spot
        return spots

    def _dias_uteis(self, hoje: date, vencimento: date) -> int | None:
        try:
            return self._calendar.business_days_between(hoje, vencimento)
        except InvalidDomainValueError:
            return None  # vencimento já passou ou fora da cobertura do calendário


def _retrato(view: OperationView) -> OperationSnapshot:
    operacao = view.operation
    total = None if view.unrealized is None else fsum((view.realized, view.unrealized))
    return OperationSnapshot(
        operacao.id,
        operacao.name,
        operacao.underlying,
        view.legs,
        total,
        operacao.stop_loss,
        operacao.target,
    )

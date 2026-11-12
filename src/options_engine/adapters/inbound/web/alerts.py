"""Router dos alertas: a lista (roda o vencimento e a Carteira antes), dispensar, restaurar e a
sugestão de rolagem para o Montador. A mesma lista vai no WebSocket (``alertas_out``)."""

from datetime import date

from fastapi import APIRouter, Response
from pydantic import BaseModel

from options_engine.adapters.inbound.web.builder import AnaliseIn, pedido_out
from options_engine.adapters.inbound.web.portfolio import Closes, ler_carteira
from options_engine.application.ports.alerts import (
    AlertsView,
    AlertUseCase,
    RollSuggestion,
    RollUseCase,
)
from options_engine.application.ports.portfolio import PortfolioUseCase
from options_engine.domain.alerts.model import Alert

__all__ = ["AlertasOut", "alertas_out", "router_alertas"]


class AlertaOut(BaseModel):
    """``perna`` é ``None`` no stop e no alvo (alertas da operação inteira)."""

    chave: str
    tipo: str
    operacao: str
    nome: str
    ativo: str
    perna: int | None
    ticker: str | None
    vencimento: date | None
    dias_uteis: int | None
    dentro_do_dinheiro: bool | None
    total: float | None
    limite: float | None
    pode_rolar: bool


class AlertasOut(BaseModel):
    """``dispensados``: quantos estão escondidos agora."""

    fonte: str
    alertas: list[AlertaOut]
    dispensados: int


class RolagemOut(BaseModel):
    """``pedido``: a estrutura nova para o Montador, ``None`` sem modelo ou sem vencimento
    seguinte. ``caixa_de_zerar``: positivo recebe, negativo paga; ``None`` sem preço de zerar."""

    operacao: str
    nome: str
    ativo: str
    vencimento_atual: date
    vencimento_novo: date | None
    pedido: AnaliseIn | None
    caixa_de_zerar: float | None
    fonte: str


def _alerta_out(alerta: Alert) -> AlertaOut:
    return AlertaOut(
        chave=alerta.key,
        tipo=alerta.kind.value,
        operacao=alerta.operation_id,
        nome=alerta.operation_name,
        ativo=alerta.underlying,
        perna=alerta.leg,
        ticker=alerta.symbol,
        vencimento=alerta.expiry,
        dias_uteis=alerta.business_days,
        dentro_do_dinheiro=alerta.in_the_money,
        total=alerta.total,
        limite=alerta.limit,
        pode_rolar=alerta.can_roll,
    )


def alertas_out(view: AlertsView) -> AlertasOut:
    return AlertasOut(
        fonte=view.source.value,
        alertas=[_alerta_out(a) for a in view.alerts],
        dispensados=view.dismissed,
    )


def _rolagem_out(sugestao: RollSuggestion) -> RolagemOut:
    return RolagemOut(
        operacao=sugestao.operation_id,
        nome=sugestao.operation_name,
        ativo=sugestao.underlying,
        vencimento_atual=sugestao.current_expiry,
        vencimento_novo=sugestao.next_expiry,
        pedido=None if sugestao.request is None else pedido_out(sugestao.request),
        caixa_de_zerar=sugestao.close_cash,
        fonte=sugestao.source.value,
    )


def router_alertas(
    alerts: AlertUseCase, roll: RollUseCase, portfolio: PortfolioUseCase, *, closes: Closes
) -> APIRouter:
    router = APIRouter(prefix="/api/alertas", tags=["alertas"])

    @router.get("")
    def listar() -> AlertasOut:
        lida = ler_carteira(portfolio, closes)
        return alertas_out(alerts.evaluate(lida.view, lida.notices))

    @router.post("/restaurar", status_code=204)
    def restaurar() -> Response:
        alerts.restore_all()
        return Response(status_code=204)

    @router.post("/{chave}/dispensar", status_code=204)
    def dispensar(chave: str) -> Response:
        alerts.dismiss(chave)
        return Response(status_code=204)

    @router.get("/rolagem/{operacao_id}")
    def rolagem(operacao_id: str) -> RolagemOut:
        return _rolagem_out(roll.roll(operacao_id))

    return router

"""Router de mercado — status, cotações, cadeia e o WebSocket ao vivo.

Números saem crus, sem formatação: a formatação pt-BR é do frontend (decisão nº 8, conversão
de exibição só na apresentação). Todo número de mercado sai com a ``fonte``
(``ao_vivo``, ``atrasado`` ou ``fim_de_dia``) e a hora da observação.

REST:

- ``GET /api/mercado/status``: de onde vêm os dados e como estão os arquivos da B3;
- ``GET /api/mercado/cotacoes``: a lista de ativos do perfil aberto (sem perfil, 404);
- ``GET /api/mercado/cadeia/{ativo}?vencimentos=2``: a cadeia, com IV e delta por série.

WebSocket ``/api/ao-vivo``: ao conectar manda ``status`` e ``cotacoes``; a cada intervalo
(1 s) reenvia só o que mudou. O cliente abre a cadeia de um ativo com
``{"tipo": "cadeia", "ativo": "PETR4", "vencimentos": 2}`` e a fecha com ``"ativo": null``.
Cada mudança da lista do perfil ou da cadeia aberta é avisada à fonte ao vivo (``follow``),
para ela assinar só o que está na tela. O cálculo roda no threadpool: o laço de eventos
nunca espera o motor.
"""

import asyncio
import json
import time
from typing import Annotated, Final

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketState

from options_engine.application.ports.inbound import (
    DEFAULT_CHAIN_EXPIRIES,
    ChainView,
    MarketStatus,
    MarketViewUseCase,
    ProfileUseCase,
    WatchRow,
)
from options_engine.domain.model.errors import DomainError, NoActiveProfileError
from options_engine.domain.model.profile import normalize_ticker

__all__ = ["INTERVALO_AO_VIVO_S", "MAX_VENCIMENTOS", "router_mercado"]

INTERVALO_AO_VIVO_S: Final = 1.0
MAX_VENCIMENTOS: Final = 12


# --- modelos de saída ----------------------------------------------------------------------------


class CadastroOut(BaseModel):
    data: str
    dias_uteis: int
    velho: bool


class FaixaOut(BaseModel):
    de: str
    ate: str


class StatusOut(BaseModel):
    fonte: str
    cadastro: CadastroOut | None
    cadastro_motivo: str | None
    cotahist: FaixaOut | None


class CotacaoOut(BaseModel):
    """``variacao_pct`` é DECIMAL, como todo ``_pct`` do projeto (CONVENTIONS): 0.02 = +2%."""

    ativo: str
    ultimo: float | None
    compra: float | None
    venda: float | None
    fechamento_anterior: float | None
    variacao_pct: float | None
    negocios: int | None
    volume: float | None
    hora: str | None
    fonte: str | None
    motivo: str | None


class SerieOut(BaseModel):
    ticker: str
    tipo: str
    strike: float
    estilo: str
    compra: float | None
    venda: float | None
    ultimo: float | None
    negocios: int
    volume: float
    iv: float | None
    delta: float | None


class VencimentoOut(BaseModel):
    data: str
    dias_uteis: int
    series: list[SerieOut]


class RejeitadaOut(BaseModel):
    ticker: str
    motivo: str


class CadeiaOut(BaseModel):
    ativo: str
    spot: float
    fonte: str
    hora: str
    vencimentos: list[VencimentoOut]
    rejeitadas: list[RejeitadaOut]


class _PedidoCadeia(BaseModel):
    """Mensagem do cliente no WebSocket: abre (``ativo``) ou fecha (``None``) a cadeia."""

    tipo: str
    ativo: str | None
    vencimentos: int = Field(default=DEFAULT_CHAIN_EXPIRIES, ge=1, le=MAX_VENCIMENTOS)


def _status_out(status: MarketStatus) -> StatusOut:
    cadastro = status.cadastro
    faixa = status.cotahist_range
    return StatusOut(
        fonte=status.source.value,
        cadastro=None
        if cadastro is None
        else CadastroOut(
            data=cadastro.reference_date.isoformat(),
            dias_uteis=cadastro.business_days,
            velho=cadastro.stale,
        ),
        cadastro_motivo=status.cadastro_reason,
        cotahist=None
        if faixa is None
        else FaixaOut(de=faixa[0].isoformat(), ate=faixa[1].isoformat()),
    )


def _cotacao_out(row: WatchRow) -> CotacaoOut:
    quote = row.quote
    if quote is None:
        return CotacaoOut(
            ativo=row.symbol,
            ultimo=None,
            compra=None,
            venda=None,
            fechamento_anterior=None,
            variacao_pct=None,
            negocios=None,
            volume=None,
            hora=None,
            fonte=None,
            motivo=row.reason,
        )
    variacao = (
        None
        if quote.last is None or quote.previous_close is None
        else quote.last / quote.previous_close - 1.0
    )
    return CotacaoOut(
        ativo=row.symbol,
        ultimo=quote.last,
        compra=quote.bid,
        venda=quote.ask,
        fechamento_anterior=quote.previous_close,
        variacao_pct=variacao,
        negocios=quote.trades,
        volume=quote.volume,
        hora=quote.timestamp.isoformat(),
        fonte=quote.source.value,
        motivo=None,
    )


def _cadeia_out(view: ChainView) -> CadeiaOut:
    return CadeiaOut(
        ativo=view.symbol,
        spot=view.spot,
        fonte=view.source.value,
        hora=view.timestamp.isoformat(),
        vencimentos=[
            VencimentoOut(
                data=block.expiry.isoformat(),
                dias_uteis=block.business_days,
                series=[
                    SerieOut(
                        ticker=row.symbol,
                        tipo=row.option_type.value,
                        strike=row.strike,
                        estilo=row.exercise_style.value,
                        compra=row.bid,
                        venda=row.ask,
                        ultimo=row.last,
                        negocios=row.trades,
                        volume=row.volume,
                        iv=row.implied_vol,
                        delta=row.delta,
                    )
                    for row in block.rows
                ],
            )
            for block in view.expiries
        ],
        rejeitadas=[RejeitadaOut(ticker=r.symbol, motivo=r.reason) for r in view.rejected],
    )


# --- router --------------------------------------------------------------------------------------


def router_mercado(
    market: MarketViewUseCase,
    profiles: ProfileUseCase,
    *,
    interval_s: float = INTERVALO_AO_VIVO_S,
) -> APIRouter:
    """Rotas ``/api/mercado/...`` e o WebSocket ``/api/ao-vivo``."""
    router = APIRouter(prefix="/api", tags=["mercado"])

    @router.get("/mercado/status")
    def status() -> StatusOut:
        return _status_out(market.status())

    @router.get("/mercado/cotacoes")
    def cotacoes() -> list[CotacaoOut]:
        return [_cotacao_out(row) for row in market.quotes(profiles.active().watchlist)]

    @router.get("/mercado/cadeia/{ativo}")
    def cadeia(
        ativo: str,
        vencimentos: Annotated[int, Query(ge=1, le=MAX_VENCIMENTOS)] = DEFAULT_CHAIN_EXPIRIES,
    ) -> CadeiaOut:
        return _cadeia_out(market.chain(normalize_ticker(ativo), vencimentos))

    @router.websocket("/ao-vivo")
    async def ao_vivo(websocket: WebSocket) -> None:
        await websocket.accept()
        await _SessaoAoVivo(websocket, market, profiles, interval_s).rodar()

    return router


class _SessaoAoVivo:
    """Uma conexão do WebSocket: o que o cliente acompanha e o que já lhe foi mandado."""

    def __init__(
        self,
        websocket: WebSocket,
        market: MarketViewUseCase,
        profiles: ProfileUseCase,
        interval_s: float,
    ) -> None:
        self._ws = websocket
        self._market = market
        self._profiles = profiles
        self._interval_s = interval_s
        self._cadeia: tuple[str, int] | None = None  # (ativo, vencimentos) da cadeia aberta
        self._seguindo: tuple[tuple[str, ...], str | None] | None = None
        self._enviado: dict[str, object] = {}  # último conteúdo mandado de cada tipo

    async def rodar(self) -> None:
        entrada: asyncio.Queue[str | None] = asyncio.Queue()
        leitor = asyncio.create_task(self._ler(entrada))
        try:
            await self._mandar(await run_in_threadpool(self._mudancas))
            proximo = time.monotonic() + self._interval_s
            while True:
                try:
                    texto = await asyncio.wait_for(
                        entrada.get(), timeout=max(0.0, proximo - time.monotonic())
                    )
                except TimeoutError:
                    proximo += self._interval_s
                    await self._mandar(await run_in_threadpool(self._mudancas))
                    continue
                if texto is None:  # o cliente desconectou
                    return
                await self._mandar(await run_in_threadpool(self._pedido, texto))
        except WebSocketDisconnect:
            return
        finally:
            leitor.cancel()

    async def _ler(self, entrada: "asyncio.Queue[str | None]") -> None:
        try:
            while True:
                entrada.put_nowait(await self._ws.receive_text())
        except WebSocketDisconnect:
            entrada.put_nowait(None)

    async def _mandar(self, mensagens: list[dict[str, object]]) -> None:
        for mensagem in mensagens:
            if self._ws.client_state is not WebSocketState.CONNECTED:
                raise WebSocketDisconnect()
            await self._ws.send_json(mensagem)

    # --- no threadpool ---------------------------------------------------------------------------

    def _pedido(self, texto: str) -> list[dict[str, object]]:
        """Trata uma mensagem do cliente e devolve o que mandar já (sem esperar o intervalo)."""
        try:
            pedido = _PedidoCadeia.model_validate(json.loads(texto))
            if pedido.tipo != "cadeia":
                raise ValueError(f"tipo de mensagem desconhecido: {pedido.tipo!r}")
            ativo = None if pedido.ativo is None else normalize_ticker(pedido.ativo)
        except (ValueError, ValidationError, DomainError) as erro:
            return [{"tipo": "erro", "erro": "RequisicaoInvalida", "mensagem": _texto(erro)}]
        self._cadeia = None if ativo is None else (ativo, pedido.vencimentos)
        self._enviado.pop("cadeia", None)  # cadeia nova (ou reaberta) sai inteira
        return self._mudancas()

    def _mudancas(self) -> list[dict[str, object]]:
        """Status, cotações e cadeia aberta, só os que mudaram desde o último envio."""
        try:
            lista, motivo = self._profiles.active().watchlist, None
        except NoActiveProfileError as erro:
            lista, motivo = (), str(erro)
        seguir = (tuple(lista), None if self._cadeia is None else self._cadeia[0])
        if seguir != self._seguindo:
            self._market.follow(*seguir)
            self._seguindo = seguir
        atual: dict[str, dict[str, object]] = {
            "status": {"tipo": "status", **_status_out(self._market.status()).model_dump()},
            "cotacoes": {
                "tipo": "cotacoes",
                "dados": [_cotacao_out(r).model_dump() for r in self._market.quotes(lista)],
                "motivo": motivo,
            },
        }
        if self._cadeia is not None:
            atual["cadeia"] = self._mensagem_da_cadeia(*self._cadeia)
        mudou = [m for chave, m in atual.items() if self._enviado.get(chave) != m]
        self._enviado.update(atual)
        return mudou

    def _mensagem_da_cadeia(self, ativo: str, vencimentos: int) -> dict[str, object]:
        try:
            view = self._market.chain(ativo, vencimentos)
        except DomainError as erro:  # desconhecido, aguardando dados, sem histórico...
            return {
                "tipo": "cadeia",
                "ativo": ativo,
                "erro": type(erro).__name__,
                "mensagem": str(erro),
            }
        return {"tipo": "cadeia", "dados": _cadeia_out(view).model_dump()}


def _texto(erro: Exception) -> str:
    if isinstance(erro, ValidationError):
        campos = ", ".join(".".join(str(p) for p in e["loc"]) or "mensagem" for e in erro.errors())
        return f"mensagem inválida no WebSocket (campos: {campos})"
    return f"mensagem inválida no WebSocket: {erro}"

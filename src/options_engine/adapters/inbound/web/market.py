"""Router de mercado: status, cotações, cadeia, análise e o WebSocket ``/api/ao-vivo``.

O WebSocket manda cada mensagem (``status``, ``cotacoes``, ``cadeia``, ``carteira``,
``alertas``) só quando ela muda. A carteira entra na assinatura do mercado: os ativos dela depois
da lista do perfil e as séries abertas antes da cadeia. Os alertas saem da mesma leitura da
carteira, sem outra consulta de mercado.
"""

import asyncio
import json
import time
from datetime import date, datetime
from typing import Annotated, Final

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketState

from options_engine.adapters.inbound.web.alerts import alertas_out
from options_engine.adapters.inbound.web.portfolio import Closes, carteira_out, ler_carteira
from options_engine.adapters.outbound.b3files.library import STALE_CADASTRO_BUSINESS_DAYS
from options_engine.application.ports.alerts import AlertUseCase
from options_engine.application.ports.inbound import (
    ChainView,
    MarketAnalysis,
    MarketAnalysisUseCase,
    MarketStatus,
    MarketViewUseCase,
    ProfileUseCase,
    WatchRow,
)
from options_engine.application.ports.portfolio import PortfolioSymbols, PortfolioUseCase
from options_engine.domain.model.errors import DomainError, NoActiveProfileError
from options_engine.domain.model.profile import normalize_ticker

__all__ = ["INTERVALO_AO_VIVO_S", "MAX_VENCIMENTOS", "router_mercado"]

INTERVALO_AO_VIVO_S: Final = 1.0
MAX_VENCIMENTOS: Final = 12
_NADA: Final = PortfolioSymbols((), ())


class PregaoOut(BaseModel):
    pregao: date
    fechamento: float
    iv30: float | None
    extrapolada: bool
    hv21: float | None


class HojeOut(BaseModel):
    iv30: float
    hv21: float
    iv_rank: float | None
    iv_percentil: float | None
    regime: str
    regime_pela_hv: bool
    extrapolada: bool


class PontoSmileOut(BaseModel):
    strike: float
    iv: float
    ticker: str


class SmileOut(BaseModel):
    vencimento: date
    dias_uteis: int
    pontos: list[PontoSmileOut]


class TermoOut(BaseModel):
    vencimento: date
    dias_uteis: int
    iv: float


class AnaliseMercadoOut(BaseModel):
    """Números crus: vols e CDI em fração anual; a taxa é a do perfil, constante no histórico."""

    ativo: str
    spot: float
    cdi_anual: float
    fonte: str
    hora: datetime
    historico: list[PregaoOut]
    historico_motivo: str | None
    hoje: HojeOut | None
    hoje_motivo: str | None
    smiles: list[SmileOut]
    estrutura: list[TermoOut]


def _analise_out(analise: MarketAnalysis) -> AnaliseMercadoOut:
    hoje = analise.today
    return AnaliseMercadoOut(
        ativo=analise.symbol,
        spot=analise.spot,
        cdi_anual=analise.cdi_annual,
        fonte=analise.source.value,
        hora=analise.timestamp,
        historico=[
            PregaoOut(
                pregao=d.session,
                fechamento=d.close,
                iv30=d.iv30,
                extrapolada=d.extrapolated,
                hv21=d.hv21,
            )
            for d in analise.history
        ],
        historico_motivo=analise.history_reason,
        hoje=None
        if hoje is None
        else HojeOut(
            iv30=hoje.iv30,
            hv21=hoje.hv21,
            iv_rank=hoje.iv_rank,
            iv_percentil=hoje.iv_percentile,
            regime=hoje.regime.value,
            regime_pela_hv=hoje.regime_from_hv,
            extrapolada=hoje.extrapolated,
        ),
        hoje_motivo=analise.today_reason,
        smiles=[
            SmileOut(
                vencimento=s.expiry,
                dias_uteis=s.business_days,
                pontos=[
                    PontoSmileOut(strike=p.strike, iv=p.implied_vol, ticker=p.symbol)
                    for p in s.points
                ],
            )
            for s in analise.smiles
        ],
        estrutura=[
            TermoOut(vencimento=t.expiry, dias_uteis=t.business_days, iv=t.vol)
            for t in analise.term_structure
        ],
    )


class CadastroOut(BaseModel):
    data: str
    dias_uteis: int
    velho: bool


class FaixaOut(BaseModel):
    de: str
    ate: str
    dias_uteis: int | None
    velho: bool


class StatusOut(BaseModel):
    fonte: str
    cadastro: CadastroOut | None
    cadastro_motivo: str | None
    cotahist: FaixaOut | None


class CotacaoOut(BaseModel):
    # variacao_pct é decimal (CONVENTIONS): 0.02 = +2%.
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
    lote: int | None


class VencimentoOut(BaseModel):
    data: str
    dias_uteis: int
    series: list[SerieOut]


class DisponivelOut(BaseModel):
    data: str
    dias_uteis: int
    semanal: bool


class RejeitadaOut(BaseModel):
    ticker: str
    motivo: str


class CadeiaOut(BaseModel):
    ativo: str
    spot: float
    fonte: str
    hora: str
    vencimentos: list[VencimentoOut]
    disponiveis: list[DisponivelOut]
    rejeitadas: list[RejeitadaOut]


class _PedidoCadeia(BaseModel):
    tipo: str
    ativo: str | None
    vencimentos: list[date] | None = Field(default=None, min_length=1, max_length=MAX_VENCIMENTOS)


def _status_out(status: MarketStatus) -> StatusOut:
    cadastro = status.cadastro
    faixa = status.cotahist_range
    idade = status.cotahist_business_days
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
        else FaixaOut(
            de=faixa[0].isoformat(),
            ate=faixa[1].isoformat(),
            dias_uteis=idade,
            velho=idade is not None and idade > STALE_CADASTRO_BUSINESS_DAYS,
        ),
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
                        lote=row.lot,
                    )
                    for row in block.rows
                ],
            )
            for block in view.expiries
        ],
        disponiveis=[
            DisponivelOut(
                data=option.expiry.isoformat(),
                dias_uteis=option.business_days,
                semanal=option.weekly,
            )
            for option in view.available
        ],
        rejeitadas=[RejeitadaOut(ticker=r.symbol, motivo=r.reason) for r in view.rejected],
    )


def router_mercado(
    market: MarketViewUseCase,
    profiles: ProfileUseCase,
    *,
    portfolio: PortfolioUseCase | None = None,
    closes: Closes = lambda _symbol, _day: None,
    interval_s: float = INTERVALO_AO_VIVO_S,
    analysis: MarketAnalysisUseCase | None = None,
    alerts: AlertUseCase | None = None,
) -> APIRouter:
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
        vencimentos: Annotated[
            list[date] | None, Query(min_length=1, max_length=MAX_VENCIMENTOS)
        ] = None,
    ) -> CadeiaOut:
        return _cadeia_out(market.chain(normalize_ticker(ativo), vencimentos))

    if analysis is not None:

        @router.get("/mercado/analise/{ativo}")
        def analise(ativo: str) -> AnaliseMercadoOut:
            return _analise_out(analysis.analysis(normalize_ticker(ativo)))

    @router.websocket("/ao-vivo")
    async def ao_vivo(websocket: WebSocket) -> None:
        await websocket.accept()
        await _SessaoAoVivo(
            websocket, market, profiles, interval_s, portfolio, closes, alerts
        ).rodar()

    return router


class _SessaoAoVivo:
    def __init__(
        self,
        websocket: WebSocket,
        market: MarketViewUseCase,
        profiles: ProfileUseCase,
        interval_s: float,
        portfolio: PortfolioUseCase | None,
        closes: Closes,
        alerts: AlertUseCase | None = None,
    ) -> None:
        self._ws = websocket
        self._alerts = alerts
        self._market = market
        self._profiles = profiles
        self._interval_s = interval_s
        self._portfolio = portfolio
        self._closes = closes
        self._cadeia: tuple[str, frozenset[date] | None] | None = None  # (ativo, vencimentos)
        self._seguindo: (
            tuple[tuple[str, ...], str | None, frozenset[date] | None, PortfolioSymbols] | None
        ) = None
        self._enviado: dict[str, object] = {}

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
                if texto is None:
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
            await self._ws.send_json(jsonable_encoder(mensagem))

    def _pedido(self, texto: str) -> list[dict[str, object]]:
        try:
            pedido = _PedidoCadeia.model_validate(json.loads(texto))
            if pedido.tipo != "cadeia":
                raise ValueError(f"tipo de mensagem desconhecido: {pedido.tipo!r}")
            ativo = None if pedido.ativo is None else normalize_ticker(pedido.ativo)
        except (ValueError, ValidationError, DomainError) as erro:
            return [{"tipo": "erro", "erro": "RequisicaoInvalida", "mensagem": _texto(erro)}]
        vencimentos = None if pedido.vencimentos is None else frozenset(pedido.vencimentos)
        self._cadeia = None if ativo is None else (ativo, vencimentos)
        self._enviado.pop("cadeia", None)  # cadeia nova (ou reaberta) sai inteira
        return self._mudancas()

    def _mudancas(self) -> list[dict[str, object]]:
        try:
            lista, motivo = self._profiles.active().watchlist, None
        except NoActiveProfileError as erro:
            lista, motivo = (), str(erro)
        ativo, vencimentos = (None, None) if self._cadeia is None else self._cadeia
        carteira, alertas, simbolos = self._mensagens_da_carteira()
        seguir = (tuple(lista), ativo, vencimentos, simbolos)
        if seguir != self._seguindo:
            self._market.follow(
                tuple(lista),
                ativo,
                vencimentos,
                portfolio_underlyings=simbolos.underlyings,
                portfolio_series=simbolos.series,
            )
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
        if carteira is not None:
            atual["carteira"] = carteira
        if alertas is not None:
            atual["alertas"] = alertas
        mudou = [m for chave, m in atual.items() if self._enviado.get(chave) != m]
        self._enviado.update(atual)
        return mudou

    def _mensagens_da_carteira(
        self,
    ) -> tuple[dict[str, object] | None, dict[str, object] | None, PortfolioSymbols]:
        """A carteira e os alertas; sem perfil aberto ou com a pasta fora do ar, os dois levam o
        erro."""
        if self._portfolio is None:
            return None, None, _NADA
        try:
            lida = ler_carteira(self._portfolio, self._closes)
        except DomainError as erro:
            carteira = _erro("carteira", erro)
            return carteira, None if self._alerts is None else _erro("alertas", erro), _NADA
        carteira = {"tipo": "carteira", "dados": carteira_out(lida.view, lida.notices).model_dump()}
        if self._alerts is None:
            return carteira, None, lida.view.symbols
        try:
            dados = alertas_out(self._alerts.evaluate(lida.view, lida.notices)).model_dump()
            alertas: dict[str, object] = {"tipo": "alertas", "dados": dados}
        except DomainError as erro:
            alertas = _erro("alertas", erro)
        return carteira, alertas, lida.view.symbols

    def _mensagem_da_cadeia(
        self, ativo: str, vencimentos: frozenset[date] | None
    ) -> dict[str, object]:
        try:
            view = self._market.chain(ativo, vencimentos)
        except DomainError as erro:
            return {
                "tipo": "cadeia",
                "ativo": ativo,
                "erro": type(erro).__name__,
                "mensagem": str(erro),
            }
        return {"tipo": "cadeia", "dados": _cadeia_out(view).model_dump()}


def _erro(tipo: str, erro: DomainError) -> dict[str, object]:
    return {"tipo": tipo, "erro": type(erro).__name__, "mensagem": str(erro)}


def _texto(erro: Exception) -> str:
    if isinstance(erro, ValidationError):
        campos = ", ".join(".".join(str(p) for p in e["loc"]) or "mensagem" for e in erro.errors())
        return f"mensagem inválida no WebSocket (campos: {campos})"
    return f"mensagem inválida no WebSocket: {erro}"

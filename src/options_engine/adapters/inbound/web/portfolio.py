"""Router da carteira: as operações abertas a mercado, o histórico, o registro e os eventos.

``GET /api/carteira`` roda o vencimento antes (pó automático e avisos), como ao abrir a tela;
a mesma visão vai no WebSocket (``carteira_atual``). Os termos de cada série vêm do cadastro
pelo ticker (``terms``); o fechamento do pregão, dos COTAHIST importados (``closes``).
"""

from collections.abc import Callable, Sequence
from datetime import date
from typing import Annotated, Final, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from options_engine.adapters.inbound.web.builder import MAX_PERNAS, IlegivelOut, Lado
from options_engine.application.ports.portfolio import (
    ExpiryNotice,
    Fill,
    LegMark,
    OperationView,
    PortfolioSymbols,
    PortfolioUseCase,
    PortfolioView,
    RegisterOperation,
    RegisterOptionLeg,
    RegisterStock,
    TaxMonthView,
)
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.profile import normalize_ticker
from options_engine.domain.portfolio.income_tax import ExerciseNote, TaxPiece
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Event,
    Exercise,
    Expired,
    LegState,
    Open,
    OptionLegRef,
    TransferOut,
)

__all__ = ["MAX_EXECUCOES", "Closes", "Terms", "carteira_atual", "router_carteira"]

MAX_EXECUCOES: Final = 20
Closes = Callable[[str, date], float | None]
Terms = Callable[[str, str], OptionTerms | str]
_LADO: Final[dict[Lado, Side]] = {"compra": Side.BUY, "venda": Side.SELL}
_TEXTO_DO_LADO: Final[dict[Side, Lado]] = {Side.BUY: "compra", Side.SELL: "venda"}


class ExecucaoIn(BaseModel):
    quantidade: int = Field(ge=1)
    preco: float = Field(ge=0)
    custos: float | None = Field(default=None, ge=0)


class PernaRegistroIn(BaseModel):
    ticker: str
    lado: Lado
    execucoes: Annotated[list[ExecucaoIn], Field(min_length=1, max_length=MAX_EXECUCOES)]


class AcaoRegistroIn(BaseModel):
    lado: Lado
    origem: Literal["compra", "carteira"]
    execucoes: Annotated[list[ExecucaoIn], Field(max_length=MAX_EXECUCOES)] = []


class RegistroIn(BaseModel):
    ativo: str
    nome: str
    data: date
    pernas: Annotated[list[PernaRegistroIn], Field(max_length=MAX_PERNAS)] = []
    acao: AcaoRegistroIn | None = None


class AcoesIn(BaseModel):
    ativo: str
    quantidade: int = Field(ge=1)
    preco_medio: float = Field(gt=0)
    data: date


class EncerrarIn(BaseModel):
    perna: int = Field(ge=0)
    quantidade: int = Field(ge=1)
    preco: float = Field(ge=0)
    data: date
    custos: float | None = Field(default=None, ge=0)


class ExercicioIn(BaseModel):
    perna: int = Field(ge=0)
    quantidade: int = Field(ge=1)
    data: date
    custos: float | None = Field(default=None, ge=0)


class OperacaoSalvaOut(BaseModel):
    id: str


class MarcaOut(BaseModel):
    """``preco`` é o de zerar; sem ele, ``teorico`` (fora do total executável) e o ``motivo``."""

    preco: float | None
    nao_realizado: float | None
    teorico: float | None
    motivo: str | None


class PernaCarteiraOut(BaseModel):
    indice: int
    ticker: str
    tipo: str
    strike: float | None
    vencimento: str | None
    estilo: str | None
    origem: str | None
    lado: Lado | None
    quantidade: int
    preco_medio: float
    realizado: float
    marca: MarcaOut | None


class EventoOut(BaseModel):
    tipo: str
    perna: int
    data: str
    lado: Lado | None = None
    quantidade: int | None = None
    preco: float | None = None
    custos: float | None = None
    custo_medio: float | None = None
    para: str | None = None


class OperacaoOut(BaseModel):
    id: str
    ativo: str
    nome: str
    criada_em: str
    pernas: list[PernaCarteiraOut]
    eventos: list[EventoOut]
    realizado: float
    nao_realizado: float | None


class TotalOut(BaseModel):
    ticker: str
    lado: Lado
    quantidade: int
    preco_medio: float
    marca: MarcaOut


class AvisoOut(BaseModel):
    operacao: str
    perna: int
    ticker: str
    vencimento: str
    situacao: str


class PecaIrOut(BaseModel):
    data: date
    ticker: str
    categoria: str
    tipo: str
    resultado: float
    operacoes: list[str]


class ExercicioIrOut(BaseModel):
    data: date
    ticker: str
    operacao: str


class MesIrOut(BaseModel):
    """``pagar_ate``: o último dia útil do mês seguinte, só com IR a pagar no mês (e dentro do
    calendário); ``ir_de_antes``: o IR abaixo de R$ 10 que veio dos meses anteriores."""

    mes: str
    comum: float
    day_trade: float
    base_comum: float
    base_day_trade: float
    prejuizo_comum: float
    prejuizo_day_trade: float
    ir_do_mes: float
    ir_de_antes: float
    ir_a_pagar: float
    ir_para_depois: float
    pagar_ate: date | None
    pecas: list[PecaIrOut]
    exercicios: list[ExercicioIrOut]


class CarteiraOut(BaseModel):
    fonte: str
    operacoes: list[OperacaoOut]
    totais: list[TotalOut]
    avisos: list[AvisoOut]
    ilegiveis: list[IlegivelOut]


def _marca_out(marca: LegMark) -> MarcaOut:
    return MarcaOut(
        preco=marca.price,
        nao_realizado=marca.unrealized,
        teorico=marca.theoretical,
        motivo=marca.reason,
    )


def _perna_out(estado: LegState, marca: LegMark | None) -> PernaCarteiraOut:
    ref = estado.ref
    opcao = ref.terms if isinstance(ref, OptionLegRef) else None
    return PernaCarteiraOut(
        indice=estado.index,
        ticker=ref.symbol,
        tipo="acao" if opcao is None else opcao.option_type.value,
        strike=None if opcao is None else opcao.strike,
        vencimento=None if opcao is None else opcao.expiry.isoformat(),
        estilo=None if opcao is None else opcao.exercise_style.value,
        origem=None if isinstance(ref, OptionLegRef) else ref.origin.value,
        lado=None if estado.side is None else _TEXTO_DO_LADO[estado.side],
        quantidade=estado.quantity,
        preco_medio=estado.average_price,
        realizado=estado.realized,
        marca=None if marca is None else _marca_out(marca),
    )


def _evento_out(evento: Event) -> EventoOut:
    perna, data = evento.leg, evento.on.isoformat()
    match evento:
        case Open():
            return EventoOut(
                tipo="abertura",
                perna=perna,
                data=data,
                lado=_TEXTO_DO_LADO[evento.side],
                quantidade=evento.quantity,
                preco=evento.price,
                custos=evento.costs,
            )
        case Close():
            return EventoOut(
                tipo="encerramento",
                perna=perna,
                data=data,
                quantidade=evento.quantity,
                preco=evento.price,
                custos=evento.costs,
                custo_medio=evento.cost_basis,
            )
        case Exercise() | Assignment():
            tipo = "exercicio" if isinstance(evento, Exercise) else "atribuicao"
            return EventoOut(
                tipo=tipo, perna=perna, data=data, quantidade=evento.quantity, custos=evento.costs
            )
        case Expired():
            return EventoOut(tipo="po", perna=perna, data=data)
        case TransferOut():
            return EventoOut(
                tipo="transferencia",
                perna=perna,
                data=data,
                quantidade=evento.quantity,
                para=evento.to_operation,
            )


def _operacao_out(view: OperationView) -> OperacaoOut:
    operacao = view.operation
    marcas = view.marks or (None,) * len(view.legs)
    return OperacaoOut(
        id=operacao.id,
        ativo=operacao.underlying,
        nome=operacao.name,
        criada_em=operacao.created_on.isoformat(),
        pernas=[_perna_out(e, m) for e, m in zip(view.legs, marcas, strict=True)],
        eventos=[_evento_out(e) for e in operacao.events],
        realizado=view.realized,
        nao_realizado=view.unrealized,
    )


def _carteira_out(view: PortfolioView, avisos: Sequence[ExpiryNotice]) -> CarteiraOut:
    return CarteiraOut(
        fonte=view.source.value,
        operacoes=[_operacao_out(o) for o in view.operations],
        totais=[
            TotalOut(
                ticker=t.total.symbol,
                lado=_TEXTO_DO_LADO[t.total.side],
                quantidade=t.total.quantity,
                preco_medio=t.total.average_price,
                marca=_marca_out(t.mark),
            )
            for t in view.totals
        ],
        avisos=[
            AvisoOut(
                operacao=a.operation_id,
                perna=a.leg,
                ticker=a.symbol,
                vencimento=a.expiry.isoformat(),
                situacao=a.outcome.value,
            )
            for a in avisos
        ],
        ilegiveis=[IlegivelOut(arquivo=i.path, motivo=i.reason) for i in view.unreadable],
    )


def _peca_ir_out(peca: TaxPiece) -> PecaIrOut:
    return PecaIrOut(
        data=peca.on,
        ticker=peca.symbol,
        categoria=peca.category.value,
        tipo=peca.kind.value,
        resultado=peca.result,
        operacoes=list(peca.operations),
    )


def _exercicio_ir_out(nota: ExerciseNote) -> ExercicioIrOut:
    return ExercicioIrOut(data=nota.on, ticker=nota.symbol, operacao=nota.operation)


def _mes_ir_out(view: TaxMonthView) -> MesIrOut:
    mes = view.month
    return MesIrOut(
        mes=mes.month.isoformat()[:7],
        comum=mes.common_result,
        day_trade=mes.day_trade_result,
        base_comum=mes.common_base,
        base_day_trade=mes.day_trade_base,
        prejuizo_comum=mes.common_loss,
        prejuizo_day_trade=mes.day_trade_loss,
        ir_do_mes=mes.tax,
        ir_de_antes=mes.carried_in,
        ir_a_pagar=mes.due,
        ir_para_depois=mes.carried_out,
        pagar_ate=view.pay_by,
        pecas=[_peca_ir_out(p) for p in mes.pieces],
        exercicios=[_exercicio_ir_out(n) for n in mes.exercises],
    )


def carteira_atual(
    portfolio: PortfolioUseCase, closes: Closes
) -> tuple[CarteiraOut, PortfolioSymbols]:
    """O vencimento roda antes: a perna que virou pó já sai fora das abertas."""
    avisos = portfolio.process_expiries(closes)
    view = portfolio.open_operations()
    return _carteira_out(view, avisos), view.symbols


def _fills(execucoes: Sequence[ExecucaoIn]) -> tuple[Fill, ...]:
    return tuple(Fill(e.quantidade, e.preco, e.custos) for e in execucoes)


def _registro(corpo: RegistroIn, terms: Terms) -> RegisterOperation:
    ativo = normalize_ticker(corpo.ativo)
    pernas = []
    for perna in corpo.pernas:
        ticker = perna.ticker.strip().upper()
        termos = terms(ticker, ativo)
        if isinstance(termos, str):
            raise InvalidDomainValueError(termos)
        pernas.append(RegisterOptionLeg(ticker, termos, _LADO[perna.lado], _fills(perna.execucoes)))
    acao = corpo.acao
    return RegisterOperation(
        ativo,
        corpo.nome,
        corpo.data,
        tuple(pernas),
        None
        if acao is None
        else RegisterStock(_LADO[acao.lado], StockOrigin(acao.origem), _fills(acao.execucoes)),
    )


def router_carteira(portfolio: PortfolioUseCase, *, closes: Closes, terms: Terms) -> APIRouter:
    router = APIRouter(prefix="/api/carteira", tags=["carteira"])

    @router.get("")
    def carteira() -> CarteiraOut:
        return carteira_atual(portfolio, closes)[0]

    @router.get("/historico")
    def historico() -> list[OperacaoOut]:
        return [_operacao_out(v) for v in portfolio.history()]

    @router.get("/ir-mensal")
    def ir_mensal() -> list[MesIrOut]:
        return [_mes_ir_out(v) for v in reversed(portfolio.income_tax())]

    @router.post("/operacoes", status_code=201)
    def registrar(corpo: RegistroIn) -> OperacaoSalvaOut:
        return OperacaoSalvaOut(id=portfolio.register(_registro(corpo, terms)).id)

    @router.post("/acoes", status_code=201)
    def adicionar_acoes(corpo: AcoesIn) -> OperacaoSalvaOut:
        operacao = portfolio.add_stock(
            normalize_ticker(corpo.ativo), corpo.quantidade, corpo.preco_medio, corpo.data
        )
        return OperacaoSalvaOut(id=operacao.id)

    @router.post("/operacoes/{operacao_id}/encerrar")
    def encerrar(operacao_id: str, corpo: EncerrarIn) -> OperacaoSalvaOut:
        operacao = portfolio.close(
            operacao_id, corpo.perna, corpo.quantidade, corpo.preco, corpo.data, corpo.custos
        )
        return OperacaoSalvaOut(id=operacao.id)

    @router.post("/operacoes/{operacao_id}/exercer")
    def exercer(operacao_id: str, corpo: ExercicioIn) -> OperacaoSalvaOut:
        operacao = portfolio.exercise(
            operacao_id, corpo.perna, corpo.quantidade, corpo.data, corpo.custos
        )
        return OperacaoSalvaOut(id=operacao.id)

    @router.post("/operacoes/{operacao_id}/atribuir")
    def atribuir(operacao_id: str, corpo: ExercicioIn) -> OperacaoSalvaOut:
        operacao = portfolio.assign(
            operacao_id, corpo.perna, corpo.quantidade, corpo.data, corpo.custos
        )
        return OperacaoSalvaOut(id=operacao.id)

    return router

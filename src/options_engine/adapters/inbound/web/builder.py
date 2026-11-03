"""Router do montador: modelos prontos, análise de uma estrutura e simulações salvas."""

from datetime import date
from typing import Annotated, Final, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from options_engine.application.ports.inbound import (
    BuilderAnalysis,
    BuilderLegInput,
    BuilderRequest,
    BuilderStockInput,
    StrategyBuilderUseCase,
)
from options_engine.application.ports.simulations import (
    SavedSimulation,
    SimulationUseCase,
    UnreadableFile,
)
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.profile import normalize_ticker
from options_engine.domain.model.templates import Template

__all__ = ["MAX_PERNAS", "AnaliseIn", "pedido_out", "router_montador"]

MAX_PERNAS: Final = 8
Lado = Literal["compra", "venda"]
_LADO: Final[dict[Lado, Side]] = {"compra": Side.BUY, "venda": Side.SELL}
_TEXTO_DO_LADO: Final[dict[Side, Lado]] = {Side.BUY: "compra", Side.SELL: "venda"}
# A vol e o tau do montador estão em base 252 (dias úteis): theta por dia útil e vega por ponto.
_DIAS_UTEIS_NO_ANO: Final = 252.0
_PONTOS_DE_VOL: Final = 100.0


class PernaIn(BaseModel):
    ticker: str
    lado: Lado
    quantidade: int = Field(ge=1)
    preco: float | None = Field(default=None, ge=0)


class AcaoIn(BaseModel):
    lado: Lado
    quantidade: int = Field(ge=1)
    origem: Literal["compra", "carteira"]
    preco: float | None = Field(default=None, gt=0)


class AnaliseIn(BaseModel):
    ativo: str
    pernas: Annotated[list[PernaIn], Field(max_length=MAX_PERNAS)] = []
    acao: AcaoIn | None = None
    modelo: str | None = None


class SimulacaoIn(AnaliseIn):
    nome: str


class PernaModeloOut(BaseModel):
    tipo: str
    lado: Lado
    proporcao: int
    passo: int


class ModeloOut(BaseModel):
    chave: str
    familia: str
    nome: str
    pernas: list[PernaModeloOut]
    acao: Lado | None


class PernaOut(BaseModel):
    ticker: str
    tipo: str
    strike: float
    estilo: str
    lado: Lado
    quantidade: int
    lote: int | None
    preco: float | None
    origem: str | None


class AcaoOut(BaseModel):
    ticker: str
    lado: Lado
    quantidade: int
    origem: str
    preco: float | None
    origem_preco: str | None


class PontoOut(BaseModel):
    spot: float
    payoff: float
    resultado: float | None
    liquido: float | None


class NoVencimentoOut(BaseModel):
    """Em reais; ``None`` nos máximos é ilimitado."""

    caixa: float
    breakevens: list[float]
    ganho_max: float | None
    perda_max: float | None
    ganho_max_liquido: float | None
    perda_max_liquida: float | None
    custos_montagem: float
    ir_no_ganho_max: float | None
    probabilidade: float


class GregasOut(BaseModel):
    delta: float
    gamma: float
    theta_dia_util: float
    vega_ponto: float
    rho: float


class GradeOut(BaseModel):
    choques_spot: list[float]
    choques_vol: list[float]
    spots: list[float]
    valores: list[list[float | None]]


class PontoHojeOut(BaseModel):
    spot: float
    resultado: float


class HojeOut(BaseModel):
    curva: list[PontoHojeOut]
    gregas: GregasOut
    grade: GradeOut
    call_americana_aproximada: bool


class AnaliseOut(BaseModel):
    nome: str
    ativo: str
    vencimento: str
    dias_uteis: int
    spot: float
    fonte: str
    hora: str
    pernas: list[PernaOut]
    acao: AcaoOut | None
    curva: list[PontoOut]
    no_vencimento: NoVencimentoOut | None
    hoje: HojeOut | None
    hoje_indisponivel: str | None
    avisos: list[str]


class SimulacaoOut(BaseModel):
    id: str
    nome: str
    criada_em: str
    pedido: AnaliseIn


class IlegivelOut(BaseModel):
    arquivo: str
    motivo: str


class SimulacoesOut(BaseModel):
    simulacoes: list[SimulacaoOut]
    ilegiveis: list[IlegivelOut]


def _pedido(corpo: AnaliseIn) -> BuilderRequest:
    acao = corpo.acao
    return BuilderRequest(
        underlying=normalize_ticker(corpo.ativo),
        legs=tuple(
            BuilderLegInput(p.ticker.strip().upper(), _LADO[p.lado], p.quantidade, p.preco)
            for p in corpo.pernas
        ),
        stock=None
        if acao is None
        else BuilderStockInput(
            _LADO[acao.lado], acao.quantidade, StockOrigin(acao.origem), acao.preco
        ),
        template=corpo.modelo,
    )


def pedido_out(pedido: BuilderRequest) -> AnaliseIn:
    acao = pedido.stock
    return AnaliseIn(
        ativo=pedido.underlying,
        pernas=[
            PernaIn(
                ticker=p.symbol, lado=_TEXTO_DO_LADO[p.side], quantidade=p.quantity, preco=p.price
            )
            for p in pedido.legs
        ],
        acao=None
        if acao is None
        else AcaoIn(
            lado=_TEXTO_DO_LADO[acao.side],
            quantidade=acao.quantity,
            origem="compra" if acao.origin is StockOrigin.COMPRA else "carteira",
            preco=acao.price,
        ),
        modelo=pedido.template,
    )


def _modelo_out(modelo: Template) -> ModeloOut:
    return ModeloOut(
        chave=modelo.key,
        familia=modelo.family.value,
        nome=modelo.name,
        pernas=[
            PernaModeloOut(
                tipo=p.option_type.value,
                lado=_TEXTO_DO_LADO[p.side],
                proporcao=p.ratio,
                passo=p.offset,
            )
            for p in modelo.legs
        ],
        acao=None if modelo.stock is None else _TEXTO_DO_LADO[modelo.stock],
    )


def _analise_out(analise: BuilderAnalysis) -> AnaliseOut:
    vencimento = analise.at_expiry
    hoje = analise.today
    acao = analise.stock
    return AnaliseOut(
        nome=analise.name,
        ativo=analise.underlying,
        vencimento=analise.expiry.isoformat(),
        dias_uteis=analise.business_days,
        spot=analise.spot,
        fonte=analise.source.value,
        hora=analise.timestamp.isoformat(),
        pernas=[
            PernaOut(
                ticker=p.symbol,
                tipo=p.option_type.value,
                strike=p.strike,
                estilo=p.exercise_style.value,
                lado=_TEXTO_DO_LADO[p.side],
                quantidade=p.quantity,
                lote=p.lot,
                preco=p.price,
                origem=None if p.origin is None else p.origin.value,
            )
            for p in analise.legs
        ],
        acao=None
        if acao is None
        else AcaoOut(
            ticker=acao.symbol,
            lado=_TEXTO_DO_LADO[acao.side],
            quantidade=acao.quantity,
            origem=acao.origin.value,
            preco=acao.price,
            origem_preco=None if acao.price_origin is None else acao.price_origin.value,
        ),
        curva=[
            PontoOut(spot=p.spot, payoff=p.payoff, resultado=p.pnl, liquido=p.net)
            for p in analise.curve
        ],
        no_vencimento=None
        if vencimento is None
        else NoVencimentoOut(
            caixa=vencimento.net_premium,
            breakevens=list(vencimento.breakevens),
            ganho_max=vencimento.max_gain,
            perda_max=vencimento.max_loss,
            ganho_max_liquido=vencimento.net_max_gain,
            perda_max_liquida=vencimento.net_max_loss,
            custos_montagem=vencimento.setup_costs,
            ir_no_ganho_max=vencimento.income_tax_at_max_gain,
            probabilidade=vencimento.probability_of_profit,
        ),
        hoje=None
        if hoje is None
        else HojeOut(
            curva=[PontoHojeOut(spot=s, resultado=v) for s, v in hoje.curve],
            gregas=GregasOut(
                delta=hoje.greeks.delta,
                gamma=hoje.greeks.gamma,
                theta_dia_util=hoje.greeks.theta_per_year / _DIAS_UTEIS_NO_ANO,
                vega_ponto=hoje.greeks.vega_per_vol_unit / _PONTOS_DE_VOL,
                rho=hoje.greeks.rho,
            ),
            grade=GradeOut(
                choques_spot=list(hoje.grid.spot_shocks),
                choques_vol=list(hoje.grid.vol_shocks),
                spots=list(hoje.grid.spots),
                valores=[list(linha) for linha in hoje.grid.values],
            ),
            call_americana_aproximada=hoje.american_call_approximated,
        ),
        hoje_indisponivel=analise.today_unavailable,
        avisos=list(analise.warnings),
    )


def _simulacao_out(simulacao: SavedSimulation) -> SimulacaoOut:
    return SimulacaoOut(
        id=simulacao.id,
        nome=simulacao.name,
        criada_em=simulacao.created_at.isoformat(),
        pedido=pedido_out(simulacao.request),
    )


def router_montador(builder: StrategyBuilderUseCase, simulations: SimulationUseCase) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["montador"])

    @router.get("/montador/modelos")
    def modelos() -> list[ModeloOut]:
        return [_modelo_out(m) for m in builder.templates()]

    @router.get("/montador/sugestao")
    def sugestao(ativo: str, modelo: str, vencimento: date) -> AnaliseIn:
        return pedido_out(builder.suggest(normalize_ticker(ativo), modelo, vencimento))

    @router.post("/montador/analise")
    def analise(corpo: AnaliseIn) -> AnaliseOut:
        return _analise_out(builder.analyze(_pedido(corpo)))

    @router.get("/simulacoes")
    def listar() -> SimulacoesOut:
        itens = simulations.list()
        return SimulacoesOut(
            simulacoes=[_simulacao_out(i) for i in itens if isinstance(i, SavedSimulation)],
            ilegiveis=[
                IlegivelOut(arquivo=i.path, motivo=i.reason)
                for i in itens
                if isinstance(i, UnreadableFile)
            ],
        )

    @router.post("/simulacoes", status_code=201)
    def salvar(corpo: SimulacaoIn) -> SimulacaoOut:
        return _simulacao_out(simulations.save(corpo.nome, _pedido(corpo)))

    @router.get("/simulacoes/{simulacao_id}")
    def abrir(simulacao_id: str) -> SimulacaoOut:
        return _simulacao_out(simulations.load(simulacao_id))

    @router.delete("/simulacoes/{simulacao_id}", status_code=204)
    def apagar(simulacao_id: str) -> Response:
        simulations.delete(simulacao_id)
        return Response(status_code=204)

    return router

"""Router do book: as recomendações do perfil aberto e as Direcionais com visão.

O porquê de cada item é montado aqui, com os números formatados em pt-BR (a formatação é do
adapter); os números também vão crus, com a unidade, para a tela. Cada item leva o ``pedido`` no
formato do ``AnaliseIn`` do montador.
"""

from datetime import date
from typing import Final, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from options_engine.adapters.inbound.web.builder import AnaliseIn, pedido_out
from options_engine.adapters.inbound.web.profiles import BookOut as PresetOut
from options_engine.adapters.inbound.web.profiles import book_out
from options_engine.application.ports.book import (
    BookEntry,
    BookFamilyView,
    BookOutcome,
    BookUseCase,
    UnderlyingVol,
)
from options_engine.application.ports.inbound import ProfileUseCase
from options_engine.domain.book.direcionais import Direction, DirectionalView
from options_engine.domain.book.frases import short_reason
from options_engine.domain.book.model import BookExclusion, BookLabel, Metric, MetricUnit
from options_engine.domain.model.enums import Side
from options_engine.domain.model.profile import normalize_ticker
from options_engine.domain.model.templates import template

__all__ = ["format_metric", "router_book"]

Lado = Literal["compra", "venda"]
_LADO: Final[dict[Side, Lado]] = {Side.BUY: "compra", Side.SELL: "venda"}
_ROTULOS: Final = {
    BookLabel.SEM_SINAL_CLARO: "vol neutra: sem sinal claro",
    BookLabel.NAO_DIRECIONAL: "não direcional: opção barata pela vol",
    BookLabel.PERDA_ILIMITADA: "perda ilimitada",
    BookLabel.POSICAO_HIPOTETICA: "posição hipotética de 100 ações",
    BookLabel.CALL_AMERICANA_COMO_EUROPEIA: "call americana avaliada como europeia",
    BookLabel.REGIME_PELA_HV: "regime pela IV contra a HV (histórico curto para o IV rank)",
    BookLabel.IV_EXTRAPOLADA: "IV 30 extrapolada (vencimentos só de um lado dos 30 dias úteis)",
}


class MetricaOut(BaseModel):
    chave: str
    rotulo: str
    valor: float
    unidade: str
    texto: str


class PernaBookOut(BaseModel):
    ticker: str
    tipo: str
    strike: float
    lado: Lado
    quantidade: int
    premio: float
    qualidade: str


class AcaoBookOut(BaseModel):
    lado: Lado
    quantidade: int
    origem: str


class RotuloOut(BaseModel):
    chave: str
    texto: str


class ResultadoOut(BaseModel):
    """Ganho e perda brutos no vencimento, sem custos nem IR; ``null`` em ``ganha_ate`` e
    ``perde_ate`` = sem limite. A chance de lucro também é bruta."""

    ganha_ate: float | None
    perde_ate: float | None
    chance_de_lucro: float
    ganha_ate_texto: str
    perde_ate_texto: str
    chance_texto: str


class ItemOut(BaseModel):
    familia: str
    estrutura: str
    nome: str
    ativo: str
    vencimento: date
    dias_uteis: int
    pernas: list[PernaBookOut]
    acao: AcaoBookOut | None
    qualidade: str
    criterio: MetricaOut
    numeros: list[MetricaOut]
    porque: str
    porque_curto: str
    rotulos: list[RotuloOut]
    pedido: AnaliseIn
    resultado: ResultadoOut | None


class ExclusaoOut(BaseModel):
    simbolo: str
    motivo: str


class FamiliaOut(BaseModel):
    itens: list[ItemOut]
    referencias: list[ItemOut]
    exclusoes: list[ExclusaoOut]


class ContextoOut(BaseModel):
    ativo: str
    iv30: float | None
    hv21: float | None
    iv_rank: float | None
    iv_percentil: float | None
    regime: str | None
    regime_pela_hv: bool
    extrapolada: bool
    motivo: str | None


class BookRespostaOut(BaseModel):
    pregao: date | None
    fonte: str
    preset: PresetOut
    contextos: list[ContextoOut]
    familias: dict[str, FamiliaOut]
    indisponiveis: list[ExclusaoOut]


class VisaoIn(BaseModel):
    ativo: str
    direcao: Literal["alta", "baixa"]
    alvo: float = Field(gt=0)
    vencimento: date


def _numero(valor: float, casas: int) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def format_metric(metric: Metric) -> str:
    """O número como a tela mostra, em pt-BR."""
    v = metric.value
    if metric.unit is MetricUnit.PERCENT:
        return f"{_numero(100.0 * v, 1)}%"
    if metric.unit is MetricUnit.CURRENCY:
        return f"{'-' if v < 0 else ''}R$ {_numero(abs(v), 2)}"
    if metric.unit is MetricUnit.STD_DEVS:
        return f"{_numero(v, 2)} desvios-padrão"
    if metric.unit is MetricUnit.BUSINESS_DAYS:
        return f"{v:.0f} dias úteis"
    return _numero(v, 2)


def _metrica_out(metric: Metric) -> MetricaOut:
    return MetricaOut(
        chave=metric.key,
        rotulo=metric.label,
        valor=metric.value,
        unidade=metric.unit.value,
        texto=format_metric(metric),
    )


def _reais(chave: str, valor: float | None) -> str:
    if valor is None:
        return "sem limite"
    return format_metric(Metric(chave, chave, valor, MetricUnit.CURRENCY))


def _ganha_ate_texto(ganho: float | None) -> str:
    if ganho is not None and ganho <= 0:
        return "não dá lucro"
    return _reais("ganha_ate", ganho)


def _resultado_out(resultado: BookOutcome | None) -> ResultadoOut | None:
    if resultado is None:
        return None
    chance = Metric(
        "chance_de_lucro", "Chance de lucro", resultado.probability_of_profit, MetricUnit.PERCENT
    )
    return ResultadoOut(
        ganha_ate=resultado.max_gain,
        perde_ate=resultado.max_loss,
        chance_de_lucro=resultado.probability_of_profit,
        ganha_ate_texto=_ganha_ate_texto(resultado.max_gain),
        perde_ate_texto=_reais("perde_ate", resultado.max_loss),
        chance_texto=format_metric(chance),
    )


def _item_out(entrada: BookEntry) -> ItemOut:
    item = entrada.item
    return ItemOut(
        familia=item.family.value,
        estrutura=item.template_key,
        nome=template(item.template_key).name,
        ativo=item.underlying,
        vencimento=item.expiry,
        dias_uteis=item.business_days,
        pernas=[
            PernaBookOut(
                ticker=leg.symbol,
                tipo=leg.option_type.value,
                strike=leg.strike,
                lado=_LADO[leg.side],
                quantidade=leg.quantity,
                premio=leg.premium.premium,
                qualidade=leg.premium.quality.value,
            )
            for leg in item.legs
        ],
        acao=None
        if item.stock is None
        else AcaoBookOut(
            lado=_LADO[item.stock.side],
            quantidade=item.stock.quantity,
            origem=item.stock.origin.value,
        ),
        qualidade=item.quality.value,
        criterio=_metrica_out(item.criterion),
        numeros=[_metrica_out(m) for m in item.metrics],
        porque=item.render_reason(format_metric),
        porque_curto=short_reason(item.template_key),
        rotulos=[RotuloOut(chave=r.value, texto=_ROTULOS[r]) for r in item.labels],
        pedido=pedido_out(entrada.request),
        resultado=_resultado_out(entrada.outcome),
    )


def _exclusao_out(exclusao: BookExclusion) -> ExclusaoOut:
    return ExclusaoOut(simbolo=exclusao.symbol, motivo=exclusao.reason)


def _familia_out(familia: BookFamilyView) -> FamiliaOut:
    return FamiliaOut(
        itens=[_item_out(e) for e in familia.items],
        referencias=[_item_out(e) for e in familia.references],
        exclusoes=[_exclusao_out(e) for e in familia.exclusions],
    )


def _contexto_out(vol: UnderlyingVol) -> ContextoOut:
    c = vol.context
    return ContextoOut(
        ativo=vol.symbol,
        iv30=None if c is None else c.iv30,
        hv21=None if c is None else c.hv21,
        iv_rank=None if c is None else c.iv_rank,
        iv_percentil=None if c is None else c.iv_percentile,
        regime=None if c is None else c.regime.value,
        regime_pela_hv=c is not None and c.regime_from_hv,
        extrapolada=c is not None and c.extrapolated,
        motivo=vol.reason,
    )


def router_book(book: BookUseCase, profiles: ProfileUseCase) -> APIRouter:
    """``/api/book`` com o preset e a lista do perfil aberto."""
    router = APIRouter(prefix="/api", tags=["book"])

    @router.get("/book")
    def recomendacoes() -> BookRespostaOut:
        perfil = profiles.active()
        vista = book.book(perfil.book_settings, perfil.watchlist)
        return BookRespostaOut(
            pregao=vista.session,
            fonte=vista.source.value,
            preset=book_out(perfil.book_settings),
            contextos=[_contexto_out(c) for c in vista.contexts],
            familias={f.value: _familia_out(v) for f, v in vista.families.items()},
            indisponiveis=[_exclusao_out(e) for e in vista.unavailable],
        )

    @router.post("/book/direcional")
    def direcional(corpo: VisaoIn) -> FamiliaOut:
        perfil = profiles.active()
        visao = DirectionalView(
            normalize_ticker(corpo.ativo), Direction(corpo.direcao), corpo.alvo, corpo.vencimento
        )
        return _familia_out(book.directional(perfil.book_settings, visao))

    return router

"""Router da aba Aprender: os exemplos numéricos das operações, sem depender de perfil aberto."""

from typing import Final, Literal

from fastapi import APIRouter
from pydantic import BaseModel

from options_engine.domain.learn.examples import Example, ExampleLeg, examples
from options_engine.domain.model.enums import Side

__all__ = ["router_aprender"]

Lado = Literal["compra", "venda"]
_LADO: Final[dict[Side, Lado]] = {Side.BUY: "compra", Side.SELL: "venda"}


class PernaExemploOut(BaseModel):
    tipo: str
    lado: Lado
    strike: float
    premio: float
    quantidade: int


class CenarioOut(BaseModel):
    preco: float
    resultado: float


class ExemploOut(BaseModel):
    """Em reais, sem custos nem IR; ``premio_liquido`` > 0 recebe e < 0 paga (só as opções);
    ``null`` em ``ganho_maximo``/``perda_maxima`` = sem limite."""

    chave: str
    nome: str
    familia: str
    spot: float
    pernas: list[PernaExemploOut]
    acoes: int
    premio_liquido: float
    cenarios: list[CenarioOut]
    empates: list[float]
    ganho_maximo: float | None
    perda_maxima: float | None
    curva: list[tuple[float, float]]


def _perna_out(perna: ExampleLeg) -> PernaExemploOut:
    return PernaExemploOut(
        tipo=perna.option_type.value,
        lado=_LADO[perna.side],
        strike=perna.strike,
        premio=perna.premium,
        quantidade=perna.quantity,
    )


def _exemplo_out(e: Example) -> ExemploOut:
    return ExemploOut(
        chave=e.key,
        nome=e.name,
        familia=e.family.value,
        spot=e.spot,
        pernas=[_perna_out(p) for p in e.legs],
        acoes=e.stock_quantity,
        premio_liquido=e.net_premium,
        cenarios=[CenarioOut(preco=preco, resultado=resultado) for preco, resultado in e.scenarios],
        empates=list(e.breakevens),
        ganho_maximo=e.max_gain,
        perda_maxima=e.max_loss,
        curva=list(e.curve),
    )


def router_aprender() -> APIRouter:
    router = APIRouter(prefix="/api", tags=["aprender"])

    @router.get("/aprender/exemplos")
    def exemplos() -> list[ExemploOut]:
        return [_exemplo_out(e) for e in examples()]

    return router

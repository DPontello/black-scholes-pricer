"""Posições abertas, resultado realizado com custos, consolidado por ativo e ações livres."""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum

from options_engine.domain.income.costs import (
    CostSchedule,
    estimate_exercise_costs_by_leg,
    estimate_order_costs,
    schedule_on,
)
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Event,
    Exercise,
    Expired,
    LegRef,
    LegState,
    Open,
    Operation,
    OptionLegRef,
    StockLegRef,
    TransferOut,
    leg_states,
)

__all__ = [
    "AssetTotal",
    "consolidate",
    "free_shares",
    "is_closed",
    "leg_states",
    "open_legs",
    "realized_result",
]


@dataclass(frozen=True, slots=True)
class AssetTotal:
    symbol: str
    side: Side
    quantity: int
    average_price: float


def open_legs(operation: Operation) -> tuple[LegState, ...]:
    return tuple(estado for estado in leg_states(operation) if estado.quantity > 0)


def is_closed(operation: Operation) -> bool:
    return bool(operation.events) and not open_legs(operation)


def _custo(evento: Event, ref: LegRef, schedules: Sequence[CostSchedule]) -> float:
    if isinstance(evento, Expired | TransferOut):
        return 0.0
    if evento.costs is not None:
        return evento.costs
    tabela = schedule_on(schedules, evento.on)
    match evento:
        case Exercise() | Assignment():
            assert isinstance(ref, OptionLegRef)  # garantido por leg_states
            return estimate_exercise_costs_by_leg(
                tabela, exercised=[(ref.terms.strike, evento.quantity)]
            ).total
        case Open() | Close() if isinstance(ref, StockLegRef):
            return estimate_order_costs(
                tabela, option_legs=[], stock_trades=[(evento.price, evento.quantity)]
            ).total
        case Open() | Close():
            return estimate_order_costs(tabela, option_legs=[(evento.price, evento.quantity)]).total


def realized_result(operation: Operation, schedules: Sequence[CostSchedule]) -> float:
    """Bruto realizado menos os custos: os reais informados, senão a estimativa da ADR-0005."""
    custos = [_custo(e, operation.legs[e.leg], schedules) for e in operation.events]
    return fsum([*(estado.realized for estado in leg_states(operation)), *(-c for c in custos)])


def consolidate(operations: Sequence[Operation]) -> tuple[AssetTotal, ...]:
    """Por ticker e lado: a quantidade aberta e o preço médio ponderado das operações."""
    somas: dict[tuple[str, Side], tuple[int, list[float]]] = {}
    for operation in operations:
        for estado in open_legs(operation):
            assert estado.side is not None
            quantidade, valores = somas.get((estado.ref.symbol, estado.side), (0, []))
            valores.append(estado.average_price * estado.quantity)
            somas[(estado.ref.symbol, estado.side)] = (quantidade + estado.quantity, valores)
    return tuple(
        AssetTotal(simbolo, lado, quantidade, fsum(valores) / quantidade)
        for (simbolo, lado), (quantidade, valores) in sorted(
            somas.items(), key=lambda item: (item[0][0], item[0][1].value)
        )
    )


def free_shares(operations: Sequence[Operation], symbol: str) -> int:
    """Ações compradas no perfil menos as que cobrem call vendida aberta.

    Numa operação com a própria ação, as calls vendidas dela cobrem as ações dela. Numa operação
    com ação "da carteira", as calls vendidas consomem ações das outras operações.
    """
    livres, consumidas = 0, 0
    for operation in operations:
        estados = leg_states(operation)
        acoes = sum(
            e.quantity
            for e in estados
            if isinstance(e.ref, StockLegRef)
            and e.ref.symbol == symbol
            and e.ref.origin is StockOrigin.COMPRA
            and e.side is Side.BUY
        )
        calls_vendidas = sum(
            e.quantity
            for e in estados
            if isinstance(e.ref, OptionLegRef)
            and e.ref.terms.underlying == symbol
            and e.ref.terms.option_type is OptionType.CALL
            and e.side is Side.SELL
        )
        da_carteira = any(
            isinstance(leg, StockLegRef)
            and leg.symbol == symbol
            and leg.origin is StockOrigin.CARTEIRA
            for leg in operation.legs
        )
        if da_carteira:
            consumidas += calls_vendidas
        else:
            livres += max(acoes - calls_vendidas, 0)
    return max(livres - consumidas, 0)

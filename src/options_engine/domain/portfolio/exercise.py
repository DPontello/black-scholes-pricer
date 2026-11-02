"""Exercício e atribuição: a opção vira ação com o prêmio no preço (IN RFB 1.585/2015, art. 60).

- titular de call: a ação entra com custo = strike + prêmio pago (II, a e § 1º);
- lançador de call: a ação sai com venda = strike + prêmio recebido (II, b);
- titular de put: a ação sai com venda = strike - prêmio pago (II, c);
- lançador de put: a ação entra com custo = strike - prêmio recebido (II, d e § 1º).

O prêmio é o preço médio ponderado da perna (§ 2º).
"""

from dataclasses import dataclass, replace
from datetime import date

from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Event,
    Exercise,
    Open,
    Operation,
    OptionLegRef,
    StockLegRef,
    leg_states,
)

__all__ = ["StockMovement", "apply_exercise", "stock_from_option"]


@dataclass(frozen=True, slots=True)
class StockMovement:
    side: Side
    quantity: int
    price: float


def stock_from_option(
    option_type: OptionType, side: Side, *, strike: float, premium: float, quantity: int
) -> StockMovement:
    if option_type is OptionType.CALL:
        movimento = StockMovement(side, quantity, strike + premium)
    else:
        movimento = StockMovement(side.opposite, quantity, strike - premium)
    if not movimento.price > 0.0:
        raise InvalidDomainValueError(
            f"prêmio {premium!r} >= strike {strike!r}: a ação ficaria sem preço"
        )
    return movimento


def _perna_de_acao(operation: Operation, origem: StockOrigin) -> int | None:
    for i, leg in enumerate(operation.legs):
        if isinstance(leg, StockLegRef) and leg.origin is origem:
            return i
    return None


def apply_exercise(
    operation: Operation,
    leg: int,
    quantity: int,
    on: date,
    *,
    costs: float | None = None,
    portfolio_average: float | None = None,
) -> Operation:
    """Exercício (perna comprada) ou atribuição (vendida), com o movimento da ação.

    ``portfolio_average``: o preço médio das ações do perfil, exigido quando a ação que sai vem
    "da carteira".
    """
    if not 0 <= leg < len(operation.legs):
        raise InvalidDomainValueError(f"evento em perna inexistente: {leg}")
    ref = operation.legs[leg]
    if not isinstance(ref, OptionLegRef):
        raise InvalidDomainValueError(f"exercício só em perna de opção; {ref.symbol!r} é ação")
    estados = leg_states(operation)
    estado = estados[leg]
    if estado.side is None or quantity > estado.quantity:
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: exerce {quantity} com {estado.quantity} em aberto"
        )
    opcao: Event = (
        Exercise(leg, on, quantity, costs)
        if estado.side is Side.BUY
        else Assignment(leg, on, quantity, costs)
    )
    movimento = stock_from_option(
        ref.terms.option_type,
        estado.side,
        strike=ref.terms.strike,
        premium=estado.average_price,
        quantity=quantity,
    )
    pernas = operation.legs
    propria = _perna_de_acao(operation, StockOrigin.COMPRA)
    da_carteira = _perna_de_acao(operation, StockOrigin.CARTEIRA)
    comprada = (
        0 if propria is None or estados[propria].side is not Side.BUY else estados[propria].quantity
    )
    # A ação que sai vem da própria operação, senão da carteira; sem nenhuma, fica vendida.
    if movimento.side is Side.SELL and propria is not None and comprada >= quantity:
        acao: Event = Close(propria, on, quantity, movimento.price, costs=0.0)
    elif movimento.side is Side.SELL and da_carteira is not None:
        if portfolio_average is None:
            raise InvalidDomainValueError(
                "a ação sai da carteira: informe o preço médio da carteira para o resultado"
            )
        acao = Close(
            da_carteira, on, quantity, movimento.price, costs=0.0, cost_basis=portfolio_average
        )
    else:
        if propria is None:
            pernas = (*pernas, StockLegRef(operation.underlying, StockOrigin.COMPRA))
            propria = len(pernas) - 1
        acao = Open(propria, on, movimento.side, quantity, movimento.price, costs=0.0)
    return replace(operation, legs=pernas, events=(*operation.events, opcao, acao))

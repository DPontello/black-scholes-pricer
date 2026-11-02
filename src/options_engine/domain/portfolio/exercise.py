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

__all__ = ["StockMovement", "apply_exercise", "stock_from_option", "takes_portfolio_shares"]


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


def _movimento(operation: Operation, leg: int, quantity: int) -> tuple[Side, StockMovement]:
    if not 0 <= leg < len(operation.legs):
        raise InvalidDomainValueError(f"evento em perna inexistente: {leg}")
    ref = operation.legs[leg]
    if not isinstance(ref, OptionLegRef):
        raise InvalidDomainValueError(f"exercício só em perna de opção; {ref.symbol!r} é ação")
    estado = leg_states(operation)[leg]
    if estado.side is None or quantity > estado.quantity:
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: exerce {quantity} com {estado.quantity} em aberto"
        )
    return estado.side, stock_from_option(
        ref.terms.option_type,
        estado.side,
        strike=ref.terms.strike,
        premium=estado.average_price,
        quantity=quantity,
    )


def _acoes_proprias(operation: Operation) -> tuple[int | None, int]:
    propria = _perna_de_acao(operation, StockOrigin.COMPRA)
    if propria is None:
        return None, 0
    estado = leg_states(operation)[propria]
    return propria, estado.quantity if estado.side is Side.BUY else 0


def takes_portfolio_shares(operation: Operation, leg: int, quantity: int) -> bool:
    """A ação sai, a operação não tem as próprias e usa as "da carteira": o resultado precisa do
    preço médio delas (``apply_exercise``)."""
    _, movimento = _movimento(operation, leg, quantity)
    _, comprada = _acoes_proprias(operation)
    return (
        movimento.side is Side.SELL
        and comprada < quantity
        and _perna_de_acao(operation, StockOrigin.CARTEIRA) is not None
    )


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
    "da carteira" (``takes_portfolio_shares``).
    """
    lado, movimento = _movimento(operation, leg, quantity)
    opcao: Event = (
        Exercise(leg, on, quantity, costs)
        if lado is Side.BUY
        else Assignment(leg, on, quantity, costs)
    )
    pernas = operation.legs
    propria, comprada = _acoes_proprias(operation)
    # A ação que sai vem da própria operação, senão da carteira; sem nenhuma, fica vendida.
    if movimento.side is Side.SELL and propria is not None and comprada >= quantity:
        acao: Event = Close(propria, on, quantity, movimento.price, costs=0.0)
    elif takes_portfolio_shares(operation, leg, quantity):
        if portfolio_average is None:
            raise InvalidDomainValueError(
                "a ação sai da carteira: informe o preço médio da carteira para o resultado"
            )
        da_carteira = _perna_de_acao(operation, StockOrigin.CARTEIRA)
        assert da_carteira is not None  # garantido por takes_portfolio_shares
        acao = Close(
            da_carteira, on, quantity, movimento.price, costs=0.0, cost_basis=portfolio_average
        )
    else:
        if propria is None:
            pernas = (*pernas, StockLegRef(operation.underlying, StockOrigin.COMPRA))
            propria = len(pernas) - 1
        acao = Open(propria, on, movimento.side, quantity, movimento.price, costs=0.0)
    return replace(operation, legs=pernas, events=(*operation.events, opcao, acao))

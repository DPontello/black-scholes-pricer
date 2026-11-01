"""Resultado líquido no vencimento de qualquer estrutura do montador (ADR-0005, por perna).

Mesmo modelo do ``income/profile``, generalizado para quantidade por perna e ação comprada ou
vendida: bruto - montagem - exercício no cenário - IR estimado, com o IR limitado ao resultado do
prêmio (a valorização da ação fica fora da base).
"""

from math import fsum

from options_engine.domain.income.costs import (
    CostSchedule,
    OrderCosts,
    estimate_exercise_costs_by_leg,
    estimate_income_tax,
    estimate_order_costs,
)
from options_engine.domain.kernel.payoff import intrinsic
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import pnl

__all__ = ["net_result_at_expiry"]


def net_result_at_expiry(
    strategy: Strategy,
    spot: float,
    schedule: CostSchedule,
    *,
    stock_already_held: bool = False,
) -> float:
    """``stock_already_held``: a ação veio da carteira e não paga a ordem de compra."""
    bruto = pnl(strategy, spot)  # recusa prêmio ou preço ausente: o `or 0.0` abaixo só tipa
    pernas = [(leg.premium or 0.0, leg.quantity) for leg in strategy.legs]
    acoes = (
        []
        if stock_already_held
        else [(acao.price or 0.0, acao.quantity) for acao in strategy.stock_legs]
    )
    montagem = (
        estimate_order_costs(schedule, option_legs=pernas, stock_trades=acoes)
        if pernas or acoes
        else OrderCosts(schedule=schedule, exchange_fees=0.0, brokerage=0.0)
    )
    exercicio = estimate_exercise_costs_by_leg(
        schedule,
        exercised=[
            (leg.terms.strike, leg.quantity)
            for leg in strategy.legs
            if intrinsic(spot, leg.terms.strike, is_call=leg.terms.option_type.is_call) > 0.0
        ],
    )
    antes_do_ir = fsum((bruto, -montagem.total, -exercicio.total))
    ordens_de_opcao = estimate_order_costs(schedule, option_legs=pernas).total if pernas else 0.0
    resultado_do_premio = fsum(
        (
            *(
                -float(leg.side.sign) * premio * quantidade
                for leg, (premio, quantidade) in zip(strategy.legs, pernas, strict=True)
            ),
            -ordens_de_opcao,
        )
    )
    imposto = estimate_income_tax(
        schedule, pre_tax_result=antes_do_ir, premium_result=resultado_do_premio
    )
    return fsum((antes_do_ir, -imposto))

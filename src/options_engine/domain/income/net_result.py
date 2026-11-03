"""Resultado líquido no vencimento de qualquer estrutura do montador (ADR-0005, por perna).

Mesmo modelo do ``income/profile``, generalizado para quantidade por perna e ação comprada ou
vendida: bruto - montagem - exercício no cenário - IR estimado, com o IR limitado ao resultado do
prêmio (a valorização da ação fica fora da base). Aceita opção americana supondo que ela vai até
o vencimento (``expiry_pnl``).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from math import fsum, inf, nextafter

from options_engine.domain.income.costs import (
    CostSchedule,
    OrderCosts,
    estimate_exercise_costs_by_leg,
    estimate_income_tax,
    estimate_order_costs,
)
from options_engine.domain.kernel.payoff import intrinsic
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.valuation import expiry_pnl

__all__ = ["NetResult", "extreme_spots", "net_result_at_expiry", "net_result_breakdown"]


@dataclass(frozen=True, slots=True)
class NetResult:
    """Em moeda, no cenário: ``net`` = ``gross`` - ``setup`` - ``exercise`` - ``income_tax``."""

    gross: float
    setup: float
    exercise: float
    income_tax: float
    net: float


def extreme_spots(
    spot: float, strikes: Iterable[float], extra: Iterable[float] = ()
) -> tuple[float, ...]:
    """Onde o líquido pode ter extremo: o ativo a zero, cada strike e logo acima dele (onde o custo
    de exercício entra), a cauda depois do último strike e os pontos ``extra``."""
    ks = list(strikes)
    return tuple(
        sorted({0.0, *extra, *ks, *(nextafter(k, inf) for k in ks), 2.0 * max([spot, *ks])})
    )


def net_result_at_expiry(
    strategy: Strategy,
    spot: float,
    schedule: CostSchedule,
    *,
    stock_already_held: bool = False,
) -> float:
    """``stock_already_held``: a ação veio da carteira e não paga a ordem de compra."""
    return net_result_breakdown(strategy, spot, schedule, stock_already_held=stock_already_held).net


def net_result_breakdown(
    strategy: Strategy,
    spot: float,
    schedule: CostSchedule,
    *,
    stock_already_held: bool = False,
) -> NetResult:
    bruto = expiry_pnl(strategy, spot)  # recusa prêmio ou preço ausente: o `or 0.0` abaixo só tipa
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
    return NetResult(
        gross=bruto,
        setup=montagem.total,
        exercise=exercicio.total,
        income_tax=imposto,
        net=fsum((antes_do_ir, -imposto)),
    )

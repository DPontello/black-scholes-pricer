"""Construtores canônicos da suíte de renda.

Os valores da tabela de custos são ILUSTRATIVOS (escolhidos para golden
cases calculáveis à mão) — não são as tabelas vigentes da B3 nem da
corretora, que chegam pela configuração versionada.
"""

from datetime import date

from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.conventions import Compounding, RiskFreeRate

VIGENCIA_PADRAO = date(2026, 1, 2)
CDI_PADRAO = 0.12  # efetivo anual, base 252 — ilustrativo


def make_cost_schedule(
    valid_from: date = VIGENCIA_PADRAO,
    exchange_fee_rate: float = 0.0005,
    brokerage_per_order: float = 5.0,
    income_tax_rate: float = 0.15,
) -> CostSchedule:
    return CostSchedule(
        valid_from=valid_from,
        exchange_fee_rate=exchange_fee_rate,
        brokerage_per_order=brokerage_per_order,
        income_tax_rate=income_tax_rate,
    )


def zero_cost_schedule() -> CostSchedule:
    """Tabela sem custo algum: o líquido coincide com o bruto."""
    return make_cost_schedule(exchange_fee_rate=0.0, brokerage_per_order=0.0, income_tax_rate=0.0)


def make_cdi(rate: float = CDI_PADRAO) -> RiskFreeRate:
    """CDI como o painel o recebe: efetivo anual, base 252."""
    return RiskFreeRate(rate, Compounding.BUSINESS_DAILY_252)

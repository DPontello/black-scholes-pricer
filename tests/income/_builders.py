"""Construtores canônicos da suíte de renda.

Os valores de ``make_cost_schedule`` são ILUSTRATIVOS (escolhidos para golden
cases calculáveis à mão e com corretagem não nula, que a tabela vigente não
tem) — não são as tabelas vigentes da B3 nem da corretora, que chegam pela
configuração versionada.
"""

from datetime import date

from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.conventions import Compounding, RiskFreeRate

VIGENCIA_PADRAO = date(2026, 1, 2)
CDI_PADRAO = 0.12  # efetivo anual, base 252 — ilustrativo


def make_cost_schedule(
    valid_from: date = VIGENCIA_PADRAO,
    option_exchange_fee_rate: float = 0.0005,
    spot_exchange_fee_rate: float = 0.0002,
    brokerage_per_order: float = 5.0,
    exercise_brokerage_per_order: float = 2.0,
    income_tax_rate: float = 0.15,
) -> CostSchedule:
    return CostSchedule(
        valid_from=valid_from,
        option_exchange_fee_rate=option_exchange_fee_rate,
        spot_exchange_fee_rate=spot_exchange_fee_rate,
        brokerage_per_order=brokerage_per_order,
        exercise_brokerage_per_order=exercise_brokerage_per_order,
        income_tax_rate=income_tax_rate,
    )


def reference_cost_schedule() -> CostSchedule:
    """Valores de referência do spike (ADR-0005, 2026-10-26) — a linha inicial da tabela.

    Emolumentos de opções 0,1340% por perna; do à vista/exercício 0,0300%;
    corretagem R$ 0,00 por ordem e por exercício; IR 15%. Literais de teste:
    a tabela vigente chega pela configuração versionada (plano da fase 2, §3.2).
    """
    return make_cost_schedule(
        option_exchange_fee_rate=0.00134,
        spot_exchange_fee_rate=0.0003,
        brokerage_per_order=0.0,
        exercise_brokerage_per_order=0.0,
        income_tax_rate=0.15,
    )


def zero_cost_schedule() -> CostSchedule:
    """Tabela sem custo algum: o líquido coincide com o bruto."""
    return make_cost_schedule(
        option_exchange_fee_rate=0.0,
        spot_exchange_fee_rate=0.0,
        brokerage_per_order=0.0,
        exercise_brokerage_per_order=0.0,
        income_tax_rate=0.0,
    )


def make_cdi(rate: float = CDI_PADRAO) -> RiskFreeRate:
    """CDI como o painel o recebe: efetivo anual, base 252."""
    return RiskFreeRate(rate, Compounding.BUSINESS_DAILY_252)

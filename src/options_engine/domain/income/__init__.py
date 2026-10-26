"""Renda com opções — métricas em forma fechada e custos (Sprint 5, ADR-0005).

Módulo puro (stdlib only, zero I/O): recebe preços como floats e VOs do
domínio; nenhum valor de tabela de custo vive aqui — chega pela
``CostSchedule`` vinda da configuração versionada.
"""

from options_engine.domain.income.costs import (
    REFERENCE_POSITION_SHARES,
    CostSchedule,
    OperationCosts,
    estimate_operation_costs,
)
from options_engine.domain.income.metrics import (
    annualize_yield_252,
    excess_over_cdi_annual_252,
)

__all__ = [
    "REFERENCE_POSITION_SHARES",
    "CostSchedule",
    "OperationCosts",
    "annualize_yield_252",
    "estimate_operation_costs",
    "excess_over_cdi_annual_252",
]

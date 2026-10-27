"""Motor de simulação — payoff, P&L, grid de estresse e gregas de portfólio.

Imperative shell fino (ARCH §5): desembrulha os VOs em floats UMA vez na
entrada, roda o loop quente sobre primitivos do kernel e re-embrulha em VOs
na saída. Europeu-only por decisão ratificada nº 2 — qualquer leg AMERICAN
é rejeitada explicitamente, nunca precificada errado em silêncio; inclusive
a call americana, porque a aproximação da ADR-0002 exige uma marca que os
resultados do motor não carregam.
"""

from options_engine.domain.simulation.engine import (
    apply_scenario,
    mark_to_model_value,
    net_premium_cashflow,
    payoff_at_expiry,
    payoff_profile,
    pnl,
    pnl_curve,
    portfolio_greeks,
    stress_grid,
)

__all__ = [
    "apply_scenario",
    "mark_to_model_value",
    "net_premium_cashflow",
    "payoff_at_expiry",
    "payoff_profile",
    "pnl",
    "pnl_curve",
    "portfolio_greeks",
    "stress_grid",
]

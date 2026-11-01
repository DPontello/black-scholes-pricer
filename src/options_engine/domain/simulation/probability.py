"""Probabilidade risco-neutra de lucro no vencimento, com o spot lognormal.

As faixas de lucro saem dos breakevens exatos do kernel (curva linear por partes): entre dois
breakevens o sinal do resultado não muda, então basta testá-lo num ponto de cada faixa.
"""

from itertools import pairwise
from math import exp, inf, log, sqrt

from options_engine.domain.kernel.distributions import norm_cdf
from options_engine.domain.kernel.payoff import PayoffLeg, breakevens
from options_engine.domain.model.conventions import RiskFreeRate, TimeToExpiry, Volatility
from options_engine.domain.model.errors import MixedAnnualizationBaseError
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.engine import net_premium_cashflow, pnl

__all__ = ["probability_of_profit"]


def probability_of_profit(
    strategy: Strategy,
    spot: float,
    *,
    time_to_expiry: TimeToExpiry,
    rate: RiskFreeRate,
    vol: Volatility,
) -> float:
    """P(resultado no vencimento > 0) com ``ln S_T ~ N(ln S + (r - σ²/2)τ, σ²τ)``."""
    if vol.annualization_base is not time_to_expiry.convention:
        raise MixedAnnualizationBaseError(
            f"vol em {vol.annualization_base.name} com tau em {time_to_expiry.convention.name} "
            f"(CONVENTIONS §2)"
        )
    tau, r, sigma = time_to_expiry.year_fraction, rate.as_continuous(), vol.value
    if tau == 0.0 or sigma == 0.0:
        return 1.0 if pnl(strategy, spot * exp(r * tau)) > 0.0 else 0.0

    def acima(nivel: float) -> float:
        if nivel <= 0.0:
            return 1.0
        if nivel == inf:
            return 0.0
        d2 = (log(spot / nivel) + (r - sigma * sigma / 2.0) * tau) / (sigma * sqrt(tau))
        return norm_cdf(d2)

    legs = [
        PayoffLeg(
            k=leg.terms.strike, w=float(leg.signed_quantity), is_call=leg.terms.option_type.is_call
        )
        for leg in strategy.legs
    ]
    acoes = float(sum(leg.signed_quantity for leg in strategy.stock_legs))
    zeros = breakevens(legs, net_premium_cashflow(strategy), acoes)
    fronteiras = [0.0, *zeros, inf]
    probabilidade = 0.0
    for de, ate in pairwise(fronteiras):
        meio = (de + ate) / 2.0 if ate != inf else max(2.0 * de, de + 1.0)
        if pnl(strategy, meio) > 0.0:
            probabilidade += acima(de) - acima(ate)
    return min(max(probabilidade, 0.0), 1.0)

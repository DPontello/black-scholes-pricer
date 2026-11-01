"""Avaliação "hoje" do montador: cada perna de opção com a sua vol (a do smile).

Diferente do ``engine``, que é europeu-only e de vol única: aqui a call americana entra como
europeia, e quem mostra o número tem de mostrar ``american_call_approximated`` junto (ADR-0002).
A put americana não tem avaliação hoje. A ação vale o spot e tem delta igual à quantidade.

No vencimento (``expiry_pnl``, ``expiry_summary``) qualquer estilo entra: o resultado supõe que a
opção vai até o vencimento, e quem mostra avisa quando há americana (``has_american``).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from math import fsum, isfinite
from typing import Final

from options_engine.domain.kernel.black_scholes import BSOutputs, bs_outputs
from options_engine.domain.kernel.payoff import PayoffLeg, breakevens, payoff, payoff_extrema
from options_engine.domain.model.conventions import RiskFreeRate, TimeToExpiry, Volatility
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    MixedAnnualizationBaseError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.results import Greeks
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.engine import net_premium_cashflow

__all__ = [
    "DEFAULT_SPOT_SHOCKS",
    "DEFAULT_VOL_SHOCKS",
    "ScenarioMatrix",
    "american_call_approximated",
    "expiry_payoff",
    "expiry_pnl",
    "expiry_summary",
    "has_american",
    "scenario_matrix",
    "structure_greeks",
    "today_curve",
    "today_value",
]

DEFAULT_SPOT_SHOCKS: Final = (-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20)
DEFAULT_VOL_SHOCKS: Final = (-0.10, -0.05, 0.0, 0.05, 0.10)


@dataclass(frozen=True, slots=True)
class ScenarioMatrix:
    """P&L de hoje por cenário: ``values[i][j]`` com o spot chocado ``spot_shocks[i]`` e a vol
    de cada perna somada a ``vol_shocks[j]``. ``None`` onde alguma vol chocada fica <= 0."""

    spot_shocks: tuple[float, ...]
    vol_shocks: tuple[float, ...]
    spots: tuple[float, ...]
    values: tuple[tuple[float | None, ...], ...]


def american_call_approximated(strategy: Strategy) -> bool:
    return any(
        leg.terms.exercise_style is ExerciseStyle.AMERICAN
        and leg.terms.option_type is OptionType.CALL
        for leg in strategy.legs
    )


def has_american(strategy: Strategy) -> bool:
    return any(leg.terms.exercise_style is ExerciseStyle.AMERICAN for leg in strategy.legs)


def _payoff_legs(strategy: Strategy) -> list[PayoffLeg]:
    return [
        PayoffLeg(leg.terms.strike, float(leg.signed_quantity), leg.terms.option_type.is_call)
        for leg in strategy.legs
    ]


def expiry_payoff(strategy: Strategy, spot: float) -> float:
    """Valor bruto no vencimento, sem o caixa da montagem: não exige prêmio."""
    return payoff(spot, _payoff_legs(strategy), _acoes(strategy))


def expiry_pnl(strategy: Strategy, spot: float) -> float:
    """P&L no vencimento (payoff + caixa da montagem), aceitando opção americana."""
    return payoff(spot, _payoff_legs(strategy), _acoes(strategy)) + net_premium_cashflow(strategy)


def expiry_summary(strategy: Strategy) -> tuple[tuple[float, ...], float | None, float | None]:
    """(breakevens, ganho máximo, perda máxima) do P&L no vencimento; ``None`` = ilimitado."""
    legs, acoes, caixa = _payoff_legs(strategy), _acoes(strategy), net_premium_cashflow(strategy)
    maximo, minimo = payoff_extrema(legs, caixa, acoes)
    return breakevens(legs, caixa, acoes), maximo, minimo


def _sigmas(
    strategy: Strategy, time_to_expiry: TimeToExpiry, vols: Sequence[Volatility]
) -> tuple[float, ...]:
    for leg in strategy.legs:
        if (
            leg.terms.exercise_style is ExerciseStyle.AMERICAN
            and leg.terms.option_type is OptionType.PUT
        ):
            raise UnsupportedExerciseStyleError(
                f"put americana {leg.symbol!r} não tem avaliação hoje: a aproximação europeia da "
                f"ADR-0002 só vale para call"
            )
    if len(vols) != len(strategy.legs):
        raise InvalidDomainValueError(
            f"uma vol por perna de opção: {len(strategy.legs)} pernas e {len(vols)} vols"
        )
    for vol in vols:
        if vol.annualization_base is not time_to_expiry.convention:
            raise MixedAnnualizationBaseError(
                f"vol em {vol.annualization_base.name} com tau em "
                f"{time_to_expiry.convention.name} (CONVENTIONS §2)"
            )
    return tuple(vol.value for vol in vols)


def _acoes(strategy: Strategy) -> float:
    return fsum(float(leg.signed_quantity) for leg in strategy.stock_legs)


def _saidas(
    strategy: Strategy, spot: float, tau: float, r: float, sigmas: Sequence[float]
) -> list[tuple[float, BSOutputs]]:
    return [
        (
            float(leg.signed_quantity),
            bs_outputs(
                spot, leg.terms.strike, tau, r, sigma, is_call=leg.terms.option_type.is_call
            ),
        )
        for leg, sigma in zip(strategy.legs, sigmas, strict=True)
    ]


def _valor(strategy: Strategy, spot: float, tau: float, r: float, sigmas: Sequence[float]) -> float:
    pernas = _saidas(strategy, spot, tau, r, sigmas)
    return fsum([*(w * saida.price for w, saida in pernas), _acoes(strategy) * spot])


def today_value(
    strategy: Strategy,
    spot: float,
    *,
    time_to_expiry: TimeToExpiry,
    rate: RiskFreeRate,
    vols: Sequence[Volatility],
) -> float:
    """Valor bruto da estrutura agora (sem o caixa da montagem)."""
    sigmas = _sigmas(strategy, time_to_expiry, vols)
    return _valor(strategy, spot, time_to_expiry.year_fraction, rate.as_continuous(), sigmas)


def today_curve(
    strategy: Strategy,
    spots: Sequence[float],
    *,
    time_to_expiry: TimeToExpiry,
    rate: RiskFreeRate,
    vols: Sequence[Volatility],
) -> tuple[float, ...]:
    """P&L de hoje em cada spot: valor a mercado + caixa da montagem (exige prêmio e preço)."""
    sigmas = _sigmas(strategy, time_to_expiry, vols)
    caixa = net_premium_cashflow(strategy)
    tau, r = time_to_expiry.year_fraction, rate.as_continuous()
    return tuple(_valor(strategy, float(s), tau, r, sigmas) + caixa for s in spots)


def structure_greeks(
    strategy: Strategy,
    spot: float,
    *,
    time_to_expiry: TimeToExpiry,
    rate: RiskFreeRate,
    vols: Sequence[Volatility],
) -> Greeks:
    sigmas = _sigmas(strategy, time_to_expiry, vols)
    pernas = _saidas(strategy, spot, time_to_expiry.year_fraction, rate.as_continuous(), sigmas)
    return Greeks(
        delta=fsum([*(w * o.delta for w, o in pernas), _acoes(strategy)]),
        gamma=fsum(w * o.gamma for w, o in pernas),
        theta_per_year=fsum(w * o.theta_per_year for w, o in pernas),
        vega_per_vol_unit=fsum(w * o.vega_per_vol_unit for w, o in pernas),
        rho=fsum(w * o.rho for w, o in pernas),
    )


def scenario_matrix(
    strategy: Strategy,
    spot: float,
    *,
    time_to_expiry: TimeToExpiry,
    rate: RiskFreeRate,
    vols: Sequence[Volatility],
    spot_shocks: Sequence[float] = DEFAULT_SPOT_SHOCKS,
    vol_shocks: Sequence[float] = DEFAULT_VOL_SHOCKS,
) -> ScenarioMatrix:
    sigmas = _sigmas(strategy, time_to_expiry, vols)
    if any(not (isfinite(c) and c > -1.0) for c in spot_shocks):
        raise InvalidDomainValueError(f"choque de spot deve ser > -100%; recebido {spot_shocks!r}")
    caixa = net_premium_cashflow(strategy)
    tau, r = time_to_expiry.year_fraction, rate.as_continuous()
    spots = tuple(spot * (1.0 + choque) for choque in spot_shocks)

    def celula(s: float, choque_vol: float) -> float | None:
        chocadas = [sigma + choque_vol for sigma in sigmas]
        if any(not (sigma > 0.0) for sigma in chocadas):
            return None
        return _valor(strategy, s, tau, r, chocadas) + caixa

    return ScenarioMatrix(
        spot_shocks=tuple(spot_shocks),
        vol_shocks=tuple(vol_shocks),
        spots=spots,
        values=tuple(tuple(celula(s, c) for c in vol_shocks) for s in spots),
    )

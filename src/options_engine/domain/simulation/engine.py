"""Motor de simulação de estruturas — o imperative shell do domínio.

Três semânticas com NOMES distintos (CONVENTIONS §5) — nenhuma se mistura:

- ``payoff_at_expiry``: valor BRUTO no vencimento (não considera prêmio).
- ``pnl``: resultado LÍQUIDO no vencimento (payoff + fluxo de prêmios);
  exige prêmio em todas as legs (decisão nº 4) → ``MissingPremiumError``.
- ``pnl_curve``: P&L A MERCADO (mark-to-model) — reprecifica as legs via
  kernel com o tau REMANESCENTE; também exige prêmios.

Fronteiras deste módulo (defendidas em toda entrada pública):

- Europeu-only (decisão nº 2): leg AMERICAN →
  ``UnsupportedExerciseStyleError``. Vale inclusive para o payoff bruto —
  uma posição americana pode ser exercida antes; a curva no vencimento
  descreveria a posição errada em silêncio.
- Base de anualização: a vol do snapshot e o tau DEVEM estar na mesma base
  (CONVENTIONS §2) → ``MixedAnnualizationBaseError``. Os VOs carregam a
  base exatamente para esta checagem existir.

Agregações SEMPRE com ``math.fsum`` sobre as legs na ordem do agregado
(canônica, por strike nas factories) — iterar set/reordenar muda o último
bit e quebra os testes de 1e-12 (CONVENTIONS §6).

Sem dividendos no MVP: o ``q`` do kernel permanece no default 0.0; o seam
existe no kernel desde a Sprint 1 e entra pelo modelo na Fase 5.
"""

from collections.abc import Sequence
from math import fsum

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.kernel.payoff import (
    PayoffLeg,
    linspace,
    payoff_extrema,
)
from options_engine.domain.kernel.payoff import (
    breakevens as kernel_breakevens,
)
from options_engine.domain.kernel.payoff import (
    payoff as kernel_payoff,
)
from options_engine.domain.model.conventions import (
    Compounding,
    RiskFreeRate,
    TimeToExpiry,
    Volatility,
)
from options_engine.domain.model.enums import ExerciseStyle
from options_engine.domain.model.errors import (
    MissingPremiumError,
    MixedAnnualizationBaseError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.results import Greeks, PayoffProfile
from options_engine.domain.model.scenarios import ScenarioGrid, StressGridResult, StressScenario
from options_engine.domain.model.strategy import Strategy

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

# ---------------------------------------------------------------------------
# Fronteiras (VO -> primitivos) e guardas
# ---------------------------------------------------------------------------


def _require_european(strategy: Strategy) -> None:
    for leg in strategy.legs:
        if leg.terms.exercise_style is not ExerciseStyle.EUROPEAN:
            raise UnsupportedExerciseStyleError(
                f"leg {leg.symbol!r} tem exercício "
                f"{leg.terms.exercise_style.value!r}; o motor é europeu-only no "
                f"MVP (decisão nº 2 — americano entra na Fase 6 via binomial)"
            )


def _require_same_base(snapshot: MarketSnapshot, time_to_expiry: TimeToExpiry) -> None:
    if snapshot.volatility.annualization_base is not time_to_expiry.convention:
        raise MixedAnnualizationBaseError(
            f"vol anualizada em {snapshot.volatility.annualization_base.name} com tau "
            f"em {time_to_expiry.convention.name}: misturar bases produz preço "
            f"errado sem erro de runtime (CONVENTIONS §2)"
        )


def _payoff_legs(strategy: Strategy) -> tuple[PayoffLeg, ...]:
    """Fronteira única VO -> primitivo do kernel de payoff (enum -> bool)."""
    return tuple(
        PayoffLeg(
            k=leg.terms.strike,
            w=float(leg.signed_quantity),
            is_call=leg.terms.option_type.is_call,
        )
        for leg in strategy.legs
    )


def net_premium_cashflow(strategy: Strategy) -> float:
    """Fluxo de caixa líquido dos prêmios na montagem, em moeda.

    Convenção de sinal: POSITIVO = crédito recebido (vendas superam
    compras), NEGATIVO = débito pago. É o offset que transforma payoff
    bruto em ``pnl``: comprar paga prêmio (``-premium``), vender recebe
    (``+premium``) — o oposto do sinal de exposição da leg.
    """
    faltantes: list[str] = []
    fluxos: list[float] = []
    for leg in strategy.legs:
        if leg.premium is None:
            faltantes.append(leg.symbol)
        else:
            fluxos.append(-float(leg.side.sign) * leg.premium * leg.quantity)
    if faltantes:
        raise MissingPremiumError(
            f"pnl exige prêmio em todas as legs (decisão nº 4); sem prêmio: "
            f"{faltantes!r} — use payoff_at_expiry para o valor bruto"
        )
    return fsum(fluxos)


# ---------------------------------------------------------------------------
# Payoff e P&L no vencimento
# ---------------------------------------------------------------------------


def payoff_at_expiry(strategy: Strategy, spot: float) -> float:
    """Valor BRUTO da estrutura no vencimento com o subjacente em ``spot``."""
    _require_european(strategy)
    return kernel_payoff(spot, _payoff_legs(strategy))


def pnl(strategy: Strategy, spot: float) -> float:
    """Resultado LÍQUIDO no vencimento: payoff bruto + fluxo de prêmios."""
    _require_european(strategy)
    return kernel_payoff(spot, _payoff_legs(strategy)) + net_premium_cashflow(strategy)


def payoff_profile(strategy: Strategy, spots: Sequence[float]) -> PayoffProfile:
    """Perfil completo sobre um eixo de spots (crescente).

    Breakevens e extremos vêm da análise em forma fechada do kernel (kinks
    nos strikes), NUNCA de interpolação dos pontos amostrados — o eixo só
    determina onde a curva é amostrada para exibição.
    """
    _require_european(strategy)
    legs = _payoff_legs(strategy)
    eixo = tuple(float(s) for s in spots)
    bruto = tuple(kernel_payoff(s, legs) for s in eixo)
    if strategy.has_premiums:
        offset = net_premium_cashflow(strategy)
        maximo, minimo = payoff_extrema(legs, offset)
        return PayoffProfile(
            spots=eixo,
            payoff_at_expiry=bruto,
            pnl=tuple(v + offset for v in bruto),
            breakevens=kernel_breakevens(legs, offset),
            max_gain=maximo,
            max_loss=minimo,
        )
    maximo, minimo = payoff_extrema(legs, 0.0)
    return PayoffProfile(
        spots=eixo,
        payoff_at_expiry=bruto,
        pnl=None,
        breakevens=None,
        max_gain=maximo,
        max_loss=minimo,
    )


# ---------------------------------------------------------------------------
# Mark-to-model (reprecificação via kernel com tau remanescente)
# ---------------------------------------------------------------------------


def _value(strategy: Strategy, spot: float, tau: float, r: float, sigma: float) -> float:
    """Valor da estrutura: soma ponderada dos preços BS das legs (fsum)."""
    return fsum(
        leg.signed_quantity
        * bs_outputs(
            spot,
            leg.terms.strike,
            tau,
            r,
            sigma,
            is_call=leg.terms.option_type.is_call,
        ).price
        for leg in strategy.legs
    )


def mark_to_model_value(
    strategy: Strategy,
    spot: float,
    *,
    time_to_expiry: TimeToExpiry,
    snapshot: MarketSnapshot,
) -> float:
    """Valor a mercado da estrutura em ``spot``, BRUTO (sem prêmio).

    ``spot`` é o cenário avaliado; taxa e vol vêm do snapshot (atômico).
    Com ``tau = 0`` cai no ramo fechado do kernel: intrínseco descontado
    (decisão nº 5) — nunca NaN, nunca erro.
    """
    _require_european(strategy)
    _require_same_base(snapshot, time_to_expiry)
    return _value(
        strategy,
        spot,
        time_to_expiry.year_fraction,
        snapshot.risk_free_rate.as_continuous(),
        snapshot.volatility.value,
    )


def pnl_curve(
    strategy: Strategy,
    spots: Sequence[float],
    *,
    time_to_expiry: TimeToExpiry,
    snapshot: MarketSnapshot,
) -> tuple[float, ...]:
    """Curva de P&L A MERCADO: valor mark-to-model + fluxo de prêmios.

    Terceira semântica do CONVENTIONS §5 — não confundir com ``pnl`` (no
    vencimento). Exige prêmio em todas as legs.
    """
    _require_european(strategy)
    _require_same_base(snapshot, time_to_expiry)
    cashflow = net_premium_cashflow(strategy)
    tau = time_to_expiry.year_fraction
    r = snapshot.risk_free_rate.as_continuous()
    sigma = snapshot.volatility.value
    return tuple(_value(strategy, float(s), tau, r, sigma) + cashflow for s in spots)


def stress_grid(
    strategy: Strategy,
    grid: ScenarioGrid,
    *,
    time_to_expiry: TimeToExpiry,
    snapshot: MarketSnapshot,
) -> StressGridResult:
    """Grid spot x vol: valor mark-to-model BRUTO por célula.

    Eixos materializados via ``linspace`` do kernel (extremos exatos). As
    vols do eixo são absolutas, na MESMA base de anualização da vol do
    snapshot (verificada contra o tau). A taxa vem do snapshot. Posição
    vencida (``tau = 0``) preenche as células com intrínseco descontado
    (decisão nº 5) — o VO de resultado rejeita NaN por construção.
    """
    _require_european(strategy)
    _require_same_base(snapshot, time_to_expiry)
    spots = linspace(grid.spot_min, grid.spot_max, grid.spot_steps)
    vols = linspace(grid.vol_min, grid.vol_max, grid.vol_steps)
    tau = time_to_expiry.year_fraction
    r = snapshot.risk_free_rate.as_continuous()
    values = tuple(tuple(_value(strategy, spot, tau, r, sigma) for sigma in vols) for spot in spots)
    return StressGridResult(grid=grid, spots=spots, vols=vols, values=values)


def portfolio_greeks(
    strategy: Strategy,
    *,
    time_to_expiry: TimeToExpiry,
    snapshot: MarketSnapshot,
) -> Greeks:
    """Gregas agregadas do portfólio no spot do snapshot.

    Soma ponderada por ``side.sign * quantity`` de CADA componente —
    inclusive rho (casa com ``StressScenario.rate_shift``) — com ``fsum``
    por grega, na ordem das legs do agregado.
    """
    _require_european(strategy)
    _require_same_base(snapshot, time_to_expiry)
    tau = time_to_expiry.year_fraction
    r = snapshot.risk_free_rate.as_continuous()
    sigma = snapshot.volatility.value
    ponderadas = [
        (
            float(leg.signed_quantity),
            bs_outputs(
                snapshot.spot,
                leg.terms.strike,
                tau,
                r,
                sigma,
                is_call=leg.terms.option_type.is_call,
            ),
        )
        for leg in strategy.legs
    ]
    return Greeks(
        delta=fsum(w * o.delta for w, o in ponderadas),
        gamma=fsum(w * o.gamma for w, o in ponderadas),
        theta_per_year=fsum(w * o.theta_per_year for w, o in ponderadas),
        vega_per_vol_unit=fsum(w * o.vega_per_vol_unit for w, o in ponderadas),
        rho=fsum(w * o.rho for w, o in ponderadas),
    )


# ---------------------------------------------------------------------------
# Cenários nomeados
# ---------------------------------------------------------------------------


def apply_scenario(snapshot: MarketSnapshot, scenario: StressScenario) -> MarketSnapshot:
    """Snapshot chocado por um cenário nomeado — VO puro em, VO puro fora.

    Spot E book (bid/mid/ask) escalam pelo mesmo fator multiplicativo
    (coerência interna preservada); vol recebe o shift aditivo em decimal;
    a taxa é convertida para contínua e chocada aditivamente (a base
    canônica do kernel — casa com rho). Um choque que levaria a vol abaixo
    de zero é irrepresentável: o VO ``Volatility`` rejeita na construção.
    """
    return MarketSnapshot(
        underlying_symbol=snapshot.underlying_symbol,
        spot=snapshot.spot * scenario.spot_shift,
        bid=snapshot.bid * scenario.spot_shift,
        ask=snapshot.ask * scenario.spot_shift,
        mid=snapshot.mid * scenario.spot_shift,
        risk_free_rate=RiskFreeRate(
            snapshot.risk_free_rate.as_continuous() + scenario.rate_shift,
            Compounding.CONTINUOUS,
        ),
        volatility=Volatility(
            snapshot.volatility.value + scenario.vol_shift,
            snapshot.volatility.annualization_base,
        ),
        timestamp=snapshot.timestamp,
    )

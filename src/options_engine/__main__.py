"""Smoke executável — documentação viva do hexágono (ROADMAP S3).

``python -m options_engine [seed]`` precifica uma call e um iron condor de
crédito via mock GBM, imprime payoff e estresse nomeado. Saída 100%
reprodutível dada a seed: relógio CONGELADO em 2026-07-03 (pregão de sexta)
e toda aleatoriedade vem da ``SeededRandomSource`` — rodar duas vezes com a
mesma seed produz bytes idênticos.

É um adapter inbound de console minimalista: consome APENAS os Protocols
inbound via ``Application`` — nenhum tipo concreto de adapter aparece aqui
além do ``FixedClock`` que congela o cenário.
"""

import sys
from datetime import date, datetime

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.inbound import PriceOptionCommand
from options_engine.config.composition import DEFAULT_UNDERLYING, build_application
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.factories import iron_condor
from options_engine.domain.model.scenarios import SpotAxis, StressScenario
from options_engine.domain.model.strategy import StrategyLeg

DEFAULT_SEED = 42
VALUATION_INSTANT = datetime(2026, 7, 3, 14, 0, tzinfo=B3_UTC_OFFSET)
EXPIRY = date(2026, 12, 18)

# Condor de crédito canônico da suíte de domínio: crédito líquido 1.00 por
# unidade ((0.80 + 0.85) - (0.30 + 0.35)) → breakevens em forma fechada
# K2 - 1 = 27 e K3 + 1 = 33.
CONDOR_STRIKES = (26.0, 28.0, 32.0, 34.0)
CONDOR_PREMIUMS = (0.30, 0.80, 0.85, 0.35)
CONDOR_QUANTITY = 10

PAYOFF_AXIS = SpotAxis(spot_min=24.0, spot_max=36.0, steps=13)
SCENARIOS = (
    StressScenario(label="base"),
    StressScenario(label="crise: spot -20%, vol +10 pts", spot_shift=0.80, vol_shift=0.10),
    StressScenario(label="rally: spot +15%, vol -5 pts", spot_shift=1.15, vol_shift=-0.05),
    StressScenario(label="aperto: taxa +200 bps", rate_shift=0.02),
)


def _condor_legs() -> list[StrategyLeg]:
    tipos = (OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL)
    lados = (Side.BUY, Side.SELL, Side.SELL, Side.BUY)  # asas compradas, corpo vendido
    return [
        StrategyLeg(
            symbol=f"PETR{'C' if tipo is OptionType.CALL else 'P'}{round(strike * 100)}",
            terms=OptionTerms(
                underlying=DEFAULT_UNDERLYING,
                strike=strike,
                expiry=EXPIRY,
                option_type=tipo,
            ),
            side=lado,
            quantity=CONDOR_QUANTITY,
            premium=premium,
        )
        for strike, premium, tipo, lado in zip(
            CONDOR_STRIKES, CONDOR_PREMIUMS, tipos, lados, strict=True
        )
    ]


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    seed = int(args[0]) if args else DEFAULT_SEED
    app = build_application(seed=seed, clock=FixedClock(VALUATION_INSTANT))

    print(f"options-engine smoke — seed={seed}, valoração={VALUATION_INSTANT.date()}")
    print()

    # 1. Uma call europeia seca via PriceOptionUseCase.
    terms = OptionTerms(
        underlying=DEFAULT_UNDERLYING, strike=30.0, expiry=EXPIRY, option_type=OptionType.CALL
    )
    result = app.price_option.execute(PriceOptionCommand(terms=terms))
    snapshot = result.snapshot
    print(f"[price] call {DEFAULT_UNDERLYING} K={terms.strike} exp={terms.expiry}")
    print(
        f"  snapshot: spot={snapshot.spot:.4f} bid={snapshot.bid:.4f} "
        f"ask={snapshot.ask:.4f} vol={snapshot.volatility.value:.2%}"
    )
    print(
        f"  tau={result.time_to_expiry.year_fraction:.6f} "
        f"({result.time_to_expiry.convention.name}) modelo={result.model_id}"
    )
    greeks = result.greeks
    print(f"  preço={result.price:.4f}")
    print(
        f"  gregas: delta={greeks.delta:.4f} gamma={greeks.gamma:.4f} "
        f"theta/ano={greeks.theta_per_year:.4f} vega={greeks.vega_per_vol_unit:.4f} "
        f"rho={greeks.rho:.4f}"
    )
    print()

    # 2. Iron condor de crédito: payoff no vencimento via SpotAxis.
    condor = iron_condor(_condor_legs())
    profile = app.analyze_payoff.execute(condor, PAYOFF_AXIS)
    print(f"[payoff] {condor.name} — strikes {CONDOR_STRIKES}, qty {CONDOR_QUANTITY}")
    assert profile.pnl is not None and profile.breakevens is not None  # prêmios informados
    print(f"  breakevens={tuple(f'{b:.2f}' for b in profile.breakevens)}")
    print(f"  max_gain={profile.max_gain:.2f} max_loss={profile.max_loss:.2f}")
    print("  spot    payoff bruto   P&L")
    for spot, bruto, pnl in zip(profile.spots, profile.payoff_at_expiry, profile.pnl, strict=True):
        print(f"  {spot:5.2f}  {bruto:12.2f}  {pnl:8.2f}")
    print()

    # 3. Estresse por cenários nomeados (mark-to-model com tau remanescente).
    report = app.stress_test.execute(condor, SCENARIOS)
    print(f"[stress] {report.strategy_name} — base={report.base_value:.4f}")
    for outcome in report.outcomes:
        variacao = report.change_from_base(outcome)
        # Saída ASCII-safe: o console default do Windows (cp1252) não tem Δ.
        print(f"  {outcome.scenario.label:<32} valor={outcome.value:9.4f}  var={variacao:+9.4f}")


if __name__ == "__main__":
    main()

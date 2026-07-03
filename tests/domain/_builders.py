"""Construtores canônicos de objetos válidos para a suíte de domínio.

Cada builder devolve um objeto VÁLIDO por default; os testes sobrescrevem
apenas o campo sob exame. Centralizar aqui evita que uma mudança de
assinatura de VO espalhe edições por dezenas de testes.
"""

from datetime import UTC, date, datetime

from hypothesis import strategies as st

from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    Volatility,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.strategy import Strategy, StrategyLeg

VENCIMENTO_PADRAO = date(2026, 12, 18)


def make_terms(
    underlying: str = "PETR4",
    strike: float = 30.0,
    expiry: date = VENCIMENTO_PADRAO,
    option_type: OptionType = OptionType.CALL,
    exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN,
) -> OptionTerms:
    return OptionTerms(
        underlying=underlying,
        strike=strike,
        expiry=expiry,
        option_type=option_type,
        exercise_style=exercise_style,
    )


def make_contract(symbol: str = "PETRA300", terms: OptionTerms | None = None) -> OptionContract:
    return OptionContract(symbol=symbol, terms=terms if terms is not None else make_terms())


def make_leg(
    symbol: str = "PETRA300",
    terms: OptionTerms | None = None,
    side: Side = Side.BUY,
    quantity: int = 10,
    premium: float | None = None,
) -> StrategyLeg:
    return StrategyLeg(
        symbol=symbol,
        terms=terms if terms is not None else make_terms(),
        side=side,
        quantity=quantity,
        premium=premium,
    )


# --- legs canônicas das estruturas nomeadas ---------------------------------
# Condor de crédito padrão: prêmios com crédito líquido unitário = 1.00
# ((0.80 + 0.85) - (0.30 + 0.35)) -> breakevens em forma fechada K2-1=27 e
# K3+1=33, convenientes para os testes exatos.

STRIKES_CONDOR = (26.0, 28.0, 32.0, 34.0)
PREMIOS_CONDOR = (0.30, 0.80, 0.85, 0.35)


def _symbol_por(tipo: OptionType, strike: float) -> str:
    letra = "C" if tipo is OptionType.CALL else "P"
    return f"PETR{letra}{round(strike * 100)}"


def make_condor_legs(
    direction: Side = Side.SELL,
    quantity: int = 10,
    premiums: tuple[float, float, float, float] | None = PREMIOS_CONDOR,
    strikes: tuple[float, float, float, float] = STRIKES_CONDOR,
) -> list[StrategyLeg]:
    """Condor com corpo em ``direction`` (SELL = crédito clássico)."""
    tipos = (OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL)
    lados = (direction.opposite, direction, direction, direction.opposite)
    return [
        make_leg(
            symbol=_symbol_por(tipo, k),
            terms=make_terms(strike=k, option_type=tipo),
            side=lado,
            quantity=quantity,
            premium=None if premiums is None else premiums[i],
        )
        for i, (k, tipo, lado) in enumerate(zip(strikes, tipos, lados, strict=True))
    ]


def make_straddle_legs(
    direction: Side = Side.BUY,
    strike: float = 30.0,
    quantity: int = 10,
    premiums: tuple[float, float] | None = (1.90, 1.55),
) -> list[StrategyLeg]:
    """Straddle em ``strike``: (call, put), ambas em ``direction``."""
    tipos = (OptionType.CALL, OptionType.PUT)
    return [
        make_leg(
            symbol=_symbol_por(tipo, strike),
            terms=make_terms(strike=strike, option_type=tipo),
            side=direction,
            quantity=quantity,
            premium=None if premiums is None else premiums[i],
        )
        for i, tipo in enumerate(tipos)
    ]


def make_strangle_legs(
    direction: Side = Side.BUY,
    put_strike: float = 28.0,
    call_strike: float = 32.0,
    quantity: int = 10,
    premiums: tuple[float, float] | None = (0.80, 0.85),
) -> list[StrategyLeg]:
    """Strangle: (put abaixo, call acima), ambas em ``direction``."""
    especs = ((OptionType.PUT, put_strike), (OptionType.CALL, call_strike))
    return [
        make_leg(
            symbol=_symbol_por(tipo, k),
            terms=make_terms(strike=k, option_type=tipo),
            side=direction,
            quantity=quantity,
            premium=None if premiums is None else premiums[i],
        )
        for i, (tipo, k) in enumerate(especs)
    ]


def make_butterfly_legs(
    direction: Side = Side.BUY,
    strikes: tuple[float, float, float] = (28.0, 30.0, 32.0),
    quantity: int = 10,
    premiums: tuple[float, float, float] | None = (2.60, 1.35, 0.55),
    option_type: OptionType = OptionType.CALL,
) -> list[StrategyLeg]:
    """Butterfly 1x/2x/1x com asas em ``direction`` e corpo no oposto."""
    lados = (direction, direction.opposite, direction)
    quantidades = (quantity, 2 * quantity, quantity)
    return [
        make_leg(
            symbol=_symbol_por(option_type, k),
            terms=make_terms(strike=k, option_type=option_type),
            side=lado,
            quantity=qty,
            premium=None if premiums is None else premiums[i],
        )
        for i, (k, lado, qty) in enumerate(zip(strikes, lados, quantidades, strict=True))
    ]


def make_snapshot(
    underlying_symbol: str = "PETR4",
    spot: float = 30.0,
    bid: float = 29.95,
    ask: float = 30.05,
    mid: float = 30.0,
    rate: float = 0.10,
    compounding: Compounding = Compounding.CONTINUOUS,
    vol: float = 0.25,
    vol_base: DayCountConvention = DayCountConvention.BUSINESS_252,
    timestamp: datetime = datetime(2026, 7, 3, 14, 0, tzinfo=UTC),
) -> MarketSnapshot:
    return MarketSnapshot(
        underlying_symbol=underlying_symbol,
        spot=spot,
        bid=bid,
        ask=ask,
        mid=mid,
        risk_free_rate=RiskFreeRate(rate, compounding),
        volatility=Volatility(vol, vol_base),
        timestamp=timestamp,
    )


# --- estratégias Hypothesis (estruturas aleatórias válidas) ------------------
# Strikes em meios-pontos e prêmios em quartos: valores exatos em binário,
# para que as propriedades de 1e-12 midam a lógica, não ruído de parsing.


@st.composite
def st_strategy(
    draw: st.DrawFn,
    min_legs: int = 1,
    max_legs: int = 5,
    with_premiums: bool = False,
) -> Strategy:
    n = draw(st.integers(min_value=min_legs, max_value=max_legs))
    legs = []
    for i in range(n):
        strike = draw(st.integers(min_value=20, max_value=120)) / 2.0
        tipo = draw(st.sampled_from([OptionType.CALL, OptionType.PUT]))
        lado = draw(st.sampled_from([Side.BUY, Side.SELL]))
        quantity = draw(st.integers(min_value=1, max_value=20))
        premium = draw(st.integers(min_value=0, max_value=40)) / 4.0 if with_premiums else None
        legs.append(
            make_leg(
                symbol=f"LEG{i}",
                terms=make_terms(strike=strike, option_type=tipo),
                side=lado,
                quantity=quantity,
                premium=premium,
            )
        )
    return Strategy.create("estrutura aleatória", legs)

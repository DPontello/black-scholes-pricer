"""Construtores canônicos de objetos válidos para a suíte de domínio.

Cada builder devolve um objeto VÁLIDO por default; os testes sobrescrevem
apenas o campo sob exame. Centralizar aqui evita que uma mudança de
assinatura de VO espalhe edições por dezenas de testes.
"""

from datetime import UTC, date, datetime

from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    Volatility,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.market import MarketSnapshot

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

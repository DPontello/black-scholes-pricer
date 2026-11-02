"""Pernas e operações sintéticas da carteira: PETR4, vencimento 19/11/2026."""

from collections.abc import Sequence
from datetime import date

from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import ExerciseStyle, OptionType, StockOrigin
from options_engine.domain.portfolio.model import (
    Event,
    LegRef,
    Operation,
    OptionLegRef,
    StockLegRef,
)

NOVEMBRO = date(2026, 11, 19)
D1, D2, D3 = date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 10)


def call(strike: float, symbol: str | None = None) -> OptionLegRef:
    return OptionLegRef(
        symbol or f"PETRK{int(strike * 10)}",
        OptionTerms("PETR4", strike, NOVEMBRO, OptionType.CALL, ExerciseStyle.AMERICAN),
    )


def put(strike: float, symbol: str | None = None) -> OptionLegRef:
    return OptionLegRef(
        symbol or f"PETRW{int(strike * 10)}",
        OptionTerms("PETR4", strike, NOVEMBRO, OptionType.PUT, ExerciseStyle.EUROPEAN),
    )


def acao(origem: StockOrigin = StockOrigin.COMPRA) -> StockLegRef:
    return StockLegRef("PETR4", origem)


def operacao(
    legs: Sequence[LegRef], events: Sequence[Event], id_: str = "op1", nome: str = "teste"
) -> Operation:
    return Operation(id_, "PETR4", nome, D1, tuple(legs), tuple(events))

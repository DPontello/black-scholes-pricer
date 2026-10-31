"""Vencimentos listados de um ativo e a escolha padrão da cadeia."""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

__all__ = ["ListedExpiry", "default_expiries", "is_weekly_series", "list_expiries"]

# B3: a série semanal termina em "W" + semana do mês (PETRK380W1); a mensal não (PETRK380).
_WEEKLY_SYMBOL: Final = re.compile(r"[A-Z0-9]{4}[A-X]\d+W\d")


def is_weekly_series(symbol: str) -> bool:
    return _WEEKLY_SYMBOL.fullmatch(symbol) is not None


@dataclass(frozen=True, slots=True)
class ListedExpiry:
    expiry: date
    weekly: bool


def list_expiries(series: Iterable[tuple[str, date]], today: date) -> tuple[ListedExpiry, ...]:
    """``series``: pares (ticker, vencimento). Semanal é o vencimento só de séries semanais."""
    weekly: dict[date, bool] = {}
    for symbol, expiry in series:
        if expiry >= today:
            weekly[expiry] = weekly.get(expiry, True) and is_weekly_series(symbol)
    return tuple(ListedExpiry(expiry, weekly[expiry]) for expiry in sorted(weekly))


def default_expiries(listed: Sequence[ListedExpiry]) -> frozenset[date]:
    """O vencimento mais próximo e o próximo mensal (as semanais escondiam o mensal)."""
    if not listed:
        return frozenset()
    nearest = min(item.expiry for item in listed)
    monthly = min((item.expiry for item in listed if not item.weekly), default=nearest)
    return frozenset({nearest, monthly})

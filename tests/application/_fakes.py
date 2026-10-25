"""Fakes dos ports outbound para os testes unitários dos use cases.

Fakes, não mocks de framework: implementações mínimas e determinísticas dos
Protocols, com gravação explícita do que foi consultado — o teste afirma
comportamento observável (o que o use case pediu aos ports), nunca detalhes
de implementação.

Sem fake de ``Clock`` aqui: ``FixedClock`` (``adapters/outbound/clock.py``)
já é frozen, determinístico e valida tz-awareness na construção — duplicá-lo
sem essa validação divergiria do contrato do port sem nenhum ganho.
"""

from dataclasses import dataclass, field
from datetime import date

from options_engine.domain.model.errors import InvalidDomainValueError, UnknownSymbolError
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["FakeMarketData", "FakeTradingCalendar"]


@dataclass(slots=True)
class FakeMarketData:
    """Devolve o snapshot configurado para o seu símbolo; grava as consultas.

    Símbolo divergente → ``UnknownSymbolError``, como manda o contrato do
    ``MarketDataPort`` (nunca ``KeyError``/``None``).
    """

    snapshot: MarketSnapshot
    requested_symbols: list[str] = field(default_factory=list)

    def get_snapshot(self, underlying_symbol: str) -> MarketSnapshot:
        self.requested_symbols.append(underlying_symbol)
        if underlying_symbol != self.snapshot.underlying_symbol:
            raise UnknownSymbolError(f"símbolo desconhecido no fake: {underlying_symbol!r}")
        return self.snapshot


@dataclass(slots=True)
class FakeTradingCalendar:
    """Contagem enlatada de dias úteis; grava os intervalos consultados.

    A semântica [start, end) pertence ao adapter real e à sua suíte — aqui
    só interessa QUE intervalo o use case pediu e QUANTOS dias voltaram.
    """

    business_days: int
    requested_ranges: list[tuple[date, date]] = field(default_factory=list)

    def business_days_between(self, start: date, end: date) -> int:
        if start > end:
            raise InvalidDomainValueError(
                f"contagem negativa não tem semântica; recebido [{start}, {end})"
            )
        self.requested_ranges.append((start, end))
        return self.business_days

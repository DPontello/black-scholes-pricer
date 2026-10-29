"""Cotação do ativo-objeto, com a fonte do dado (ao vivo, atrasado ou fim de dia).

Mesmas regras de lado ausente do ``OptionQuote`` (ADR-0003): ``None``,
nunca ``0``. A tradução "zero da fonte → ``None``" (inclusive os zeros
iniciais do RTD antes da carga) é do adapter; aqui ``0`` é irrepresentável.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from math import isfinite

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["DataSource", "UnderlyingQuote"]


@unique
class DataSource(Enum):
    """De onde veio o número exibido — nenhuma cotação sai sem este rótulo."""

    AO_VIVO = "ao_vivo"
    ATRASADO = "atrasado"
    FIM_DE_DIA = "fim_de_dia"


@dataclass(frozen=True, slots=True)
class UnderlyingQuote:
    """Cotação de um ativo-objeto num instante: book, último, fechamento anterior e liquidez.

    ``last``, ``bid``, ``ask`` e ``previous_close`` são ``None`` (ausente) ou
    finitos e ``> 0``. Com os dois lados presentes, ``bid <= ask``: book
    travado é coerente, cruzado não. ``volume`` é o volume FINANCEIRO
    negociado, como no ``OptionQuote``; ``trades`` é o número de negócios.
    """

    symbol: str
    last: float | None
    bid: float | None
    ask: float | None
    previous_close: float | None
    trades: int
    volume: float
    timestamp: datetime
    source: DataSource

    def __post_init__(self) -> None:
        for nome, valor in (
            ("last", self.last),
            ("bid", self.bid),
            ("ask", self.ask),
            ("previous_close", self.previous_close),
        ):
            # Forma negada: NaN falha em qualquer comparação e cairia no
            # caminho "válido" de um `valor <= 0.0`.
            if valor is not None and not (isfinite(valor) and valor > 0.0):
                raise InvalidDomainValueError(
                    f"{nome} de {self.symbol!r} deve ser None (ausente) ou finito e > 0 — "
                    f"zero de 'sem oferta' vira None no adapter (ADR-0003); recebido {valor!r}"
                )
        if self.bid is not None and self.ask is not None and not (self.bid <= self.ask):
            raise InvalidDomainValueError(
                f"book cruzado em {self.symbol!r}: exigido bid <= ask; recebido "
                f"bid={self.bid!r}, ask={self.ask!r}"
            )
        if self.trades < 0:
            raise InvalidDomainValueError(
                f"trades de {self.symbol!r} deve ser >= 0; recebido {self.trades!r}"
            )
        if not (isfinite(self.volume) and self.volume >= 0.0):
            raise InvalidDomainValueError(
                f"volume de {self.symbol!r} deve ser finito e >= 0; recebido {self.volume!r}"
            )
        # tzinfo presente não basta: um tzinfo que devolve utcoffset None
        # ainda é naive na prática (mesma regra do MarketSnapshot).
        if self.timestamp.tzinfo is None or self.timestamp.tzinfo.utcoffset(self.timestamp) is None:
            raise InvalidDomainValueError(
                f"timestamp de {self.symbol!r} deve ser tz-aware; recebido {self.timestamp!r}"
            )

    @property
    def change_pct(self) -> float | None:
        """Variação sobre o fechamento anterior (``last / previous_close - 1``), em fração.

        ``None`` quando falta ``last`` ou ``previous_close``. Sem divisão por
        zero: ``previous_close`` presente é sempre ``> 0``.
        """
        if self.last is None or self.previous_close is None:
            return None
        return self.last / self.previous_close - 1.0

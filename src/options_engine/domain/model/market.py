"""Foto atômica e imutável do mercado.

Atomicidade é a razão de existir deste VO: preço + gregas + grid inteiro
usam dados coerentes entre si — o spot não muda no meio do cálculo. O
snapshot NÃO sabe de onde veio (JSON do feed, schema da B3): a tradução
feed -> VO acontece exclusivamente dentro do adapter (risco arquitetural
vigiado do ARCHITECTURE §1).
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from options_engine.domain.model.conventions import RiskFreeRate, Volatility
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["MarketSnapshot"]


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    """Spot, book (bid/ask/mid), taxa e vol num instante único, tz-aware.

    Taxa e vol entram como VOs com convenção explícita — ``float`` nu é
    proibido em qualquer port (CONVENTIONS §3). O ``mid`` é armazenado como
    veio do feed (não recalculado): a definição de mid pertence à fonte;
    aqui vale apenas a coerência ``bid <= mid <= ask``.
    """

    underlying_symbol: str
    spot: float
    bid: float
    ask: float
    mid: float
    risk_free_rate: RiskFreeRate
    volatility: Volatility
    timestamp: datetime

    def __post_init__(self) -> None:
        if not self.underlying_symbol:
            raise InvalidDomainValueError("underlying_symbol não pode ser vazio")
        if not (isfinite(self.spot) and self.spot > 0.0):
            raise InvalidDomainValueError(f"spot deve ser finito e > 0; recebido {self.spot!r}")
        if not (isfinite(self.bid) and isfinite(self.ask) and isfinite(self.mid)):
            raise InvalidDomainValueError(
                f"bid/mid/ask devem ser finitos; recebido "
                f"bid={self.bid!r}, mid={self.mid!r}, ask={self.ask!r}"
            )
        # `not (a <= b)` em vez de `a > b`: NaN já foi barrado acima, mas a
        # forma negada mantém o padrão de defesa em profundidade do kernel.
        if not (0.0 <= self.bid <= self.mid <= self.ask):
            raise InvalidDomainValueError(
                f"book incoerente: exigido 0 <= bid <= mid <= ask; recebido "
                f"bid={self.bid!r}, mid={self.mid!r}, ask={self.ask!r}"
            )
        # tzinfo presente não basta: um tzinfo que devolve utcoffset None
        # ainda é naive na prática (contrato do MarketDataPort, ARCH §8).
        if self.timestamp.tzinfo is None or self.timestamp.tzinfo.utcoffset(self.timestamp) is None:
            raise InvalidDomainValueError(
                f"timestamp deve ser tz-aware; recebido {self.timestamp!r}"
            )

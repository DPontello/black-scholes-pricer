"""Cadeia de opções (ADR-0003) e preço executável por lado (ADR-0004).

Cuidado estrutural que atravessa o módulo: **lado ausente é ``None``, nunca
``0``** (ADR-0003). Nas fontes reais (COTAHIST, brapi) melhor compra e
melhor venda vêm zeradas com frequência; um zero de "sem oferta" que
atravessasse a fronteira viraria um preço real, sem nenhum erro de runtime.
A tradução "zero da fonte → ``None``" acontece exclusivamente no adapter
(ARCH §1) — aqui ``0`` é irrepresentável.
"""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from options_engine.domain.model.contracts import OptionContract
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["OptionQuote"]


def _is_tz_aware(timestamp: datetime) -> bool:
    # tzinfo presente não basta: um tzinfo que devolve utcoffset None ainda
    # é naive na prática (mesma regra do MarketSnapshot).
    return timestamp.tzinfo is not None and timestamp.tzinfo.utcoffset(timestamp) is not None


@dataclass(frozen=True, slots=True)
class OptionQuote:
    """Cotação de uma série num pregão: book, último negócio e liquidez.

    ``bid``, ``ask`` e ``last`` são ``None`` (lado ausente / sem negócio) ou
    finitos e ``> 0``. Com os dois lados presentes, ``bid <= ask``: spread
    zero (book travado) é coerente, book cruzado não. Não há ``mid``: ele
    serve só para exibir o smile, nunca para calcular rendimento (ADR-0004)
    — derivá-lo é da apresentação.

    ``trades`` (número de negócios) e ``volume`` (volume negociado) são do
    pregão de referência e alimentam os filtros de liquidez, que são
    parâmetros do comando, não invariantes deste VO (ADR-0004). A unidade de
    ``volume`` (financeiro ou quantidade de contratos) não é fixada pela
    ADR-0003; o domínio só exige finito e ``>= 0``.

    Não há invariante cruzando ``last`` e ``trades``: uma fonte pode trazer
    o último preço de um pregão anterior com ``trades == 0``. Decidir se o
    ``last`` é utilizável é da regra de preço, não da cotação.
    """

    contract: OptionContract
    bid: float | None
    ask: float | None
    last: float | None
    trades: int
    volume: float
    timestamp: datetime

    def __post_init__(self) -> None:
        for nome, valor in (("bid", self.bid), ("ask", self.ask), ("last", self.last)):
            # Forma negada: NaN falha em qualquer comparação e cairia no
            # caminho "válido" de um `valor <= 0.0`.
            if valor is not None and not (isfinite(valor) and valor > 0.0):
                raise InvalidDomainValueError(
                    f"{nome} de {self.contract.symbol!r} deve ser None (ausente) ou finito e "
                    f"> 0 — zero de 'sem oferta' vira None no adapter (ADR-0003); "
                    f"recebido {valor!r}"
                )
        if self.bid is not None and self.ask is not None and not (self.bid <= self.ask):
            raise InvalidDomainValueError(
                f"book cruzado em {self.contract.symbol!r}: exigido bid <= ask; recebido "
                f"bid={self.bid!r}, ask={self.ask!r}"
            )
        if self.trades < 0:
            raise InvalidDomainValueError(
                f"trades de {self.contract.symbol!r} deve ser >= 0; recebido {self.trades!r}"
            )
        if not (isfinite(self.volume) and self.volume >= 0.0):
            raise InvalidDomainValueError(
                f"volume de {self.contract.symbol!r} deve ser finito e >= 0; "
                f"recebido {self.volume!r}"
            )
        if not _is_tz_aware(self.timestamp):
            raise InvalidDomainValueError(
                f"timestamp de {self.contract.symbol!r} deve ser tz-aware; "
                f"recebido {self.timestamp!r}"
            )

"""``LiveBoard`` — quadro ao vivo: o último valor cru de cada (ativo, campo).

Só guarda o que chega da ponte, como chegou (tipo de origem e valor, com o instante de
chegada). Zero inicial do RTD, texto de hora e lado vazio são interpretados na tradução
(Task 10), nunca aqui. Thread-safe: a thread do cliente escreve; as requisições leem.

Só guarda ativo assinado (``mark_subscribed``): a ponte difunde os tópicos de todos os clientes
(o ``espiar``, uma instância antiga do app) e um ativo esquecido (``forget``) não pode receber
o ``Valor`` que ainda estava em trânsito. ``Valor`` de ativo que ninguém assinou é descartado.

Regra de carga: o ``Valor`` inicial (o do ``ConnectData``, zero até o Tryd carregar o tópico,
``Valor.inicial``) é guardado mas NÃO carrega o ativo. Carregado = chegou algum ``Valor`` que
não é inicial (uma atualização de verdade) depois da assinatura, ou passou ``TEMPO_CARGA_S``.
"""

import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from options_engine.adapters.outbound.tryd.settings import TEMPO_CARGA_S
from options_ponte.protocolo import Valor

__all__ = ["LiveBoard", "RawValue"]

_log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RawValue:
    """Valor de um campo como veio do RTD. ``received_at`` é o relógio monotônico do quadro.

    ``initial``: ainda é o valor do ``ConnectData`` (o zero de antes da carga), nenhuma
    atualização de verdade chegou para este campo (``Valor.inicial`` do que o produziu).
    """

    kind: str
    value: float | int | str | None
    received_at: float
    initial: bool = False


class LiveBoard:
    """Último ``RawValue`` por ativo e campo, mais o controle de "já carregou"."""

    def __init__(self, monotonic: Callable[[], float] = time.monotonic) -> None:
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._values: dict[str, dict[str, RawValue]] = {}
        self._subscribed_at: dict[str, float] = {}
        self._updated: set[str] = set()

    def mark_subscribed(self, tickers: Iterable[str]) -> None:
        """Começa a contar ``TEMPO_CARGA_S`` dos ativos novos; quem já estava na lista segue."""
        now = self._monotonic()
        with self._lock:
            for ticker in tickers:
                self._subscribed_at.setdefault(ticker, now)

    def forget(self, tickers: Iterable[str]) -> None:
        """Volta os ativos ao estado de nunca assinados: sem valores, sem "atualizado", sem
        contagem de carga. Para o ativo cancelado, ou quando a ponte (e o que ela guardava)
        pode ser outra: o que ficou no quadro não vale para a assinatura nova.
        """
        with self._lock:
            for ticker in tickers:
                self._values.pop(ticker, None)
                self._subscribed_at.pop(ticker, None)
                self._updated.discard(ticker)

    def apply(self, valor: Valor) -> None:
        """Guarda o valor de um ativo assinado; o de ativo não assinado é descartado.

        O inicial fica disponível em ``values`` (com ``initial=True``), mas não conta como carga.
        """
        received = RawValue(valor.tipo_valor, valor.valor, self._monotonic(), valor.inicial)
        with self._lock:
            if valor.ticker not in self._subscribed_at:
                _log.debug("valor de %s descartado: ativo não assinado", valor.ticker)
                return
            self._values.setdefault(valor.ticker, {})[valor.campo] = received
            if not valor.inicial:
                self._updated.add(valor.ticker)

    def values(self, ticker: str) -> Mapping[str, RawValue]:
        """Foto dos campos do ativo: não muda quando chegam valores novos."""
        with self._lock:
            return dict(self._values.get(ticker, {}))

    def is_loaded(self, ticker: str) -> bool:
        """Chegou um ``Valor`` não inicial do ativo, ou passaram ``TEMPO_CARGA_S`` desde a
        assinatura. O zero inicial do RTD sozinho não basta: é o "ainda não carregou" do Tryd.
        """
        with self._lock:
            if ticker in self._updated:
                return True
            subscribed_at = self._subscribed_at.get(ticker)
        return subscribed_at is not None and self._monotonic() - subscribed_at >= TEMPO_CARGA_S

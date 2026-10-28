"""``TrydBridgeClient`` — cliente TCP da ponte do Tryd (``options_ponte``).

Uma thread daemon mantém a conexão com ``127.0.0.1:PORTA_PONTE``: conecta, reenvia a
assinatura completa (a ponte reemite o último valor de cada tópico) e entrega cada ``Valor``
ao ``LiveBoard``. Se a ponte cai ou ainda não subiu, tenta de novo a cada
``RECONNECT_INTERVAL_S``: Tryd fechado não é erro do app.
"""

import contextlib
import enum
import logging
import socket
import threading
import time
from collections.abc import Callable

from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.settings import (
    PONTE_ATRASADA_S,
    PONTE_PERDIDA_S,
    PORTA_PONTE,
)
from options_ponte.protocolo import (
    TRYD_INICIANDO,
    TRYD_PERDIDO,
    Assinar,
    Cancelar,
    Encerrar,
    ErroDeProtocolo,
    Mensagem,
    Ping,
    Pong,
    Status,
    Valor,
    codificar,
    decodificar,
)

__all__ = ["PING_TIMEOUT_S", "RECONNECT_INTERVAL_S", "BridgeHealth", "TrydBridgeClient"]

_log = logging.getLogger(__name__)

RECONNECT_INTERVAL_S = 2.0
PING_TIMEOUT_S = 2.0

_CONNECT_TIMEOUT_S = 2.0
_SOCKET_TIMEOUT_S = 1.0  # leitura sem dados volta ao laço (para ver o stop); envio que trava cai
_JOIN_TIMEOUT_S = 5.0
_BYTES_PER_READ = 65536

Topic = tuple[str, str]

# Status em que a ponte fala, mas o Tryd não está entregando dado de verdade.
_TRYD_SEM_DADO = (TRYD_INICIANDO, TRYD_PERDIDO)


class BridgeHealth(enum.Enum):
    """Saúde da ponte pela idade da última mensagem dela."""

    CONECTADA = "conectada"
    ATRASADA = "atrasada"
    DESCONECTADA = "desconectada"


class TrydBridgeClient:
    """Fala com a ponte em thread própria; ``ensure_subscribed`` e ``health`` são thread-safe."""

    def __init__(
        self,
        board: LiveBoard,
        host: str = "127.0.0.1",
        port: int = PORTA_PONTE,
        monotonic: Callable[[], float] = time.monotonic,
        *,
        reconnect_interval_s: float = RECONNECT_INTERVAL_S,
    ) -> None:
        self._board = board
        self._host = host
        self._port = port
        self._monotonic = monotonic
        self._reconnect_interval_s = reconnect_interval_s
        # `_conn_lock`: assinatura desejada, socket atual e todo envio por ele. Decidir a
        # diferença e enviá-la sob a mesma trava impede que um Cancelar corra com o Assinar
        # completo da reconexão e deixe na ponte um tópico que ninguém mais quer.
        self._conn_lock = threading.Lock()
        self._wanted: frozenset[Topic] = frozenset()
        self._sock: socket.socket | None = None
        # `_state_lock`: o que `health` lê. Separada para a leitura não esperar um envio.
        self._state_lock = threading.Lock()
        self._last_message_at: float | None = None
        self._tryd_state: str | None = None  # `tryd` do último Status desta conexão
        self._last_status: tuple[str, str | None] | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Sobe a thread que conecta e reconecta. Não faz nada se ela já está de pé."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="tryd-bridge-client", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Para a thread e solta a conexão. Pode ser chamado mais de uma vez."""
        self._stop.set()
        with self._conn_lock:
            sock = self._sock
        if sock is not None:
            _shutdown(sock)  # acorda o recv da thread
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=_JOIN_TIMEOUT_S)

    def ensure_subscribed(self, topics: frozenset[Topic]) -> None:
        """Deixa a ponte assinando exatamente ``topics``: manda só a diferença.

        O quadro acompanha, sob a mesma trava e antes de qualquer envio: o ativo que sai de vez
        (nenhum tópico dele continua desejado) é esquecido, e o ativo novo começa a assinatura
        do zero (``forget`` + ``mark_subscribed``), sem herdar valor nem "carregou" de antes. A
        composição não precisa chamar ``mark_subscribed``. Sem conexão, só guarda: a assinatura
        completa vai quando a conexão sobe.
        """
        with self._conn_lock:
            added = topics - self._wanted
            removed = self._wanted - topics
            leaving = _tickers(self._wanted) - _tickers(topics)
            entering = _tickers(topics) - _tickers(self._wanted)
            self._board.forget(leaving | entering)
            self._board.mark_subscribed(entering)
            self._wanted = topics
            if removed:  # cancela antes de assinar: libera espaço no limite de tópicos da ponte
                self._send_locked(Cancelar(tuple(sorted(removed))))
            if added:
                self._send_locked(Assinar(tuple(sorted(added))))

    def health(self) -> BridgeHealth:
        """Pela idade da última mensagem da ponte (``< PONTE_ATRASADA_S`` conectada,
        ``< PONTE_PERDIDA_S`` atrasada, senão ou nunca ouvida, desconectada).

        Só ``Status(tryd="conectado")`` (ou nenhum Status ainda nesta conexão, com ``Valor``/
        ``Pong`` chegando) permite CONECTADA: o último Status ``iniciando`` ou ``perdido``
        limita a ATRASADA, porque a ponte está no ar mas o Tryd não entrega dado de verdade.
        """
        with self._state_lock:
            last_message_at = self._last_message_at
            tryd_state = self._tryd_state
        if last_message_at is None:
            return BridgeHealth.DESCONECTADA
        age_s = self._monotonic() - last_message_at
        if age_s >= PONTE_PERDIDA_S:
            return BridgeHealth.DESCONECTADA
        if age_s >= PONTE_ATRASADA_S or tryd_state in _TRYD_SEM_DADO:
            return BridgeHealth.ATRASADA
        return BridgeHealth.CONECTADA

    def shutdown_bridge(self) -> None:
        """Pede à ponte que encerre (``Encerrar``), pela conexão aberta ou por uma só para isso."""
        with self._conn_lock:
            if self._send_locked(Encerrar()):
                return
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=_CONNECT_TIMEOUT_S
            ) as conn:
                conn.sendall(codificar(Encerrar()))
        except OSError as erro:
            _log.info("Encerrar não chegou à ponte: %s", erro)

    def bridge_responds(self, timeout_s: float = PING_TIMEOUT_S) -> bool:
        """Verdadeiro se uma ponte responde ``Pong`` a um ``Ping`` em até ``timeout_s``.

        Usa uma conexão só para isso e o relógio real: o prazo é de socket, não de saúde.
        """
        deadline = time.monotonic() + timeout_s
        try:
            with socket.create_connection((self._host, self._port), timeout=timeout_s) as conn:
                conn.sendall(codificar(Ping()))
                rest = b""
                while (remaining_s := deadline - time.monotonic()) > 0:
                    conn.settimeout(remaining_s)
                    try:
                        data = conn.recv(_BYTES_PER_READ)
                    except TimeoutError:
                        return False
                    if not data:  # quem atende fechou sem responder
                        return False
                    *lines, rest = (rest + data).split(b"\n")
                    if any(_is_pong(line) for line in lines):
                        return True
        except OSError:
            return False
        return False

    def _run(self) -> None:
        while not self._stop.is_set():
            sock = self._connect()
            if sock is not None:
                try:
                    self._read_until_closed(sock)
                except Exception:  # a thread é a única ponte com o Tryd: não pode morrer calada
                    _log.exception("falha inesperada ao ler a ponte do Tryd")
                self._drop(sock)
            self._stop.wait(self._reconnect_interval_s)

    def _connect(self) -> socket.socket | None:
        try:
            sock = socket.create_connection((self._host, self._port), timeout=_CONNECT_TIMEOUT_S)
        except OSError as erro:  # ponte fora do ar é o estado normal com o Tryd fechado
            _log.debug("ponte indisponível em %s:%s: %s", self._host, self._port, erro)
            return None
        sock.settimeout(_SOCKET_TIMEOUT_S)
        # linhas pequenas e sem espera por ACK: atraso aqui vira atraso de cotação
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self._state_lock:
            self._tryd_state = None  # a ponte pode ser outra: o Status antigo não vale
        with self._conn_lock:
            self._sock = sock
            if self._wanted:
                # A ponte nova (relançada) manda zeros iniciais; a mesma reemite os últimos valores
                # logo ao assinar. Em qualquer caso o quadro recomeça: nada herdado vale como carga.
                tickers = _tickers(self._wanted)
                self._board.forget(tickers)
                self._board.mark_subscribed(tickers)
                self._send_locked(Assinar(tuple(sorted(self._wanted))))
        return sock

    def _drop(self, sock: socket.socket) -> None:
        with self._conn_lock:
            if self._sock is sock:
                self._sock = None
        sock.close()

    def _send_locked(self, mensagem: Mensagem) -> bool:
        """Envia pela conexão atual (``_conn_lock`` tomada). Falha derruba a conexão."""
        sock = self._sock
        if sock is None:
            return False
        try:
            sock.sendall(codificar(mensagem))
        except OSError as erro:
            _log.warning("envio à ponte falhou (%s); vai reconectar", erro)
            _shutdown(sock)  # a thread de leitura vê o fim e reconecta com a assinatura completa
            return False
        return True

    def _read_until_closed(self, sock: socket.socket) -> None:
        rest = b""
        while not self._stop.is_set():
            try:
                data = sock.recv(_BYTES_PER_READ)
            except TimeoutError:
                continue
            except OSError:
                return
            if not data:
                return
            *lines, rest = (rest + data).split(b"\n")
            for line in lines:
                if line.strip():
                    self._handle_line(line)

    def _handle_line(self, line: bytes) -> None:
        try:
            mensagem = decodificar(line)
        except ErroDeProtocolo as erro:
            _log.warning("linha recusada da ponte: %s", erro)
            return
        now = self._monotonic()
        with self._state_lock:
            self._last_message_at = now
            if isinstance(mensagem, Status):
                self._tryd_state = mensagem.tryd
        if isinstance(mensagem, Valor):
            self._board.apply(mensagem)
        elif isinstance(mensagem, Status):
            self._log_status_change(mensagem)

    def _log_status_change(self, status: Status) -> None:
        current = (status.tryd, status.motivo)
        if current != self._last_status:
            self._last_status = current
            _log.info(
                "ponte: Tryd %s (%s tópicos) %s", status.tryd, status.topicos, status.motivo or ""
            )


def _tickers(topics: frozenset[Topic]) -> frozenset[str]:
    return frozenset(ticker for ticker, _campo in topics)


def _is_pong(line: bytes) -> bool:
    try:
        return isinstance(decodificar(line), Pong)
    except ErroDeProtocolo:
        return False


def _shutdown(sock: socket.socket) -> None:
    with contextlib.suppress(OSError):
        sock.shutdown(socket.SHUT_RDWR)

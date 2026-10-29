"""Ponte falsa em TCP local (porta 0) — testa cliente e lançador sem Tryd, Wine nem distrobox.

Fala o protocolo de verdade (``options_ponte.protocolo``): guarda o que recebe, responde
``Ping`` com ``Pong`` e ``Assinar`` com os ``Valor`` que o teste deixou em ``valores``.
"""

import contextlib
import itertools
import socket
import threading
import time
from collections.abc import Callable

from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_ponte.protocolo import (
    Assinar,
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

_PASSO_S = 0.02  # as threads voltam ao laço nesse intervalo para ver o fim
_LIMITE_DE_ESPERA_S = 3.0


def esperar(condicao: Callable[[], bool], limite_s: float = _LIMITE_DE_ESPERA_S) -> None:
    fim = time.monotonic() + limite_s
    while not condicao():
        assert time.monotonic() < fim, f"condição não aconteceu em {limite_s:g} s"
        time.sleep(0.005)


def porta_sem_ninguem() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class PonteFalsa:
    """Servidor TCP que imita a ponte. ``fechar`` solta a porta (a ponte que caiu)."""

    def __init__(
        self,
        porta: int = 0,
        *,
        responde_ping: bool = True,
        fecha_ao_encerrar: bool = False,
    ) -> None:
        self.responde_ping = responde_ping
        self.fecha_ao_encerrar = fecha_ao_encerrar
        self.valores: dict[tuple[str, str], Valor] = {}
        self.total_aceitas = 0  # conexões aceitas desde o início, inclusive as que já saíram
        self._escuta = socket.create_server(("127.0.0.1", porta))
        self._escuta.settimeout(_PASSO_S)
        self.porta = int(self._escuta.getsockname()[1])
        self._trava = threading.Lock()  # protege _conexoes e _recebidas
        self._envio = threading.Lock()  # uma linha por vez em cada socket
        self._conexoes: list[socket.socket] = []
        self._recebidas: list[Mensagem] = []
        self._fim = threading.Event()
        self._aceite = threading.Thread(target=self._aceitar, daemon=True)
        self._aceite.start()

    @property
    def fechada(self) -> bool:
        """Verdadeiro quando a porta já foi solta (depois de ``fechar`` ou do ``Encerrar``)."""
        return not self._aceite.is_alive()

    def recebidas(self) -> list[Mensagem]:
        with self._trava:
            return list(self._recebidas)

    def conexoes(self) -> int:
        with self._trava:
            return len(self._conexoes)

    def enviar(self, *itens: Mensagem | bytes) -> None:
        """Difunde a todos os clientes (``bytes`` vai como veio: linha malformada incluída)."""
        linhas = b"".join(i if isinstance(i, bytes) else codificar(i) for i in itens)
        with self._trava:
            conexoes = list(self._conexoes)
        for conexao in conexoes:
            self._enviar_a(conexao, linhas)

    def derrubar_clientes(self) -> None:
        with self._trava:
            conexoes = list(self._conexoes)
        for conexao in conexoes:
            _fechar(conexao)

    def fechar(self) -> None:
        """Para de ouvir, derruba os clientes e espera a porta ficar livre."""
        self._fim.set()
        if threading.current_thread() is not self._aceite:
            self._aceite.join(timeout=5)

    def _enviar_a(self, conexao: socket.socket, dados: bytes) -> None:
        with self._envio, contextlib.suppress(OSError):  # cliente que já saiu
            conexao.sendall(dados)

    def _aceitar(self) -> None:
        try:
            while not self._fim.is_set():
                try:
                    conexao, _ = self._escuta.accept()
                except TimeoutError:
                    continue
                except OSError:
                    break
                conexao.settimeout(_PASSO_S)
                with self._trava:
                    self._conexoes.append(conexao)
                    self.total_aceitas += 1
                threading.Thread(target=self._atender, args=(conexao,), daemon=True).start()
        finally:
            self._escuta.close()
            self.derrubar_clientes()

    def _atender(self, conexao: socket.socket) -> None:
        resto = b""
        try:
            while not self._fim.is_set():
                try:
                    dados = conexao.recv(65536)
                except TimeoutError:
                    continue
                if not dados:
                    return
                *linhas, resto = (resto + dados).split(b"\n")
                for linha in linhas:
                    if linha.strip():
                        self._tratar(conexao, linha)
        except OSError:  # reset do cliente, ou o fechamento feito por derrubar_clientes
            pass
        finally:
            with self._trava:
                if conexao in self._conexoes:
                    self._conexoes.remove(conexao)
            _fechar(conexao)

    def _tratar(self, conexao: socket.socket, linha: bytes) -> None:
        try:
            mensagem = decodificar(linha)
        except ErroDeProtocolo:
            return
        with self._trava:
            self._recebidas.append(mensagem)
        if isinstance(mensagem, Ping) and self.responde_ping:
            self._enviar_a(conexao, codificar(Pong()))
        elif isinstance(mensagem, Assinar):
            valores = [self.valores[t] for t in mensagem.topicos if t in self.valores]
            if valores:
                self._enviar_a(conexao, b"".join(codificar(v) for v in valores))
        elif isinstance(mensagem, Encerrar) and self.fecha_ao_encerrar:
            self._fim.set()


def _fechar(conexao: socket.socket) -> None:
    with contextlib.suppress(OSError):
        conexao.shutdown(socket.SHUT_RDWR)
    conexao.close()


_sentinelas = itertools.count(1)


def entregar(
    ponte: PonteFalsa,
    quadro: LiveBoard,
    t: list[float],
    instante: float,
    *mensagens: Status | Valor | Pong,
) -> None:
    """Move o relógio do cliente (``t``) para ``instante``, manda as mensagens e espera o cliente.

    A mensagem sentinela (um ``NEG`` novo de PETR4, que o teste precisa ter assinado) vai por
    último: o cliente trata as linhas em ordem, então quando ela aparece no quadro tudo o que
    veio antes já foi tratado.
    """
    t[0] = instante
    sentinela = next(_sentinelas)
    ponte.enviar(*mensagens, Valor("PETR4", "NEG", "int", sentinela, "2026-10-28T12:03:00-03:00"))
    esperar(lambda: _neg_de_petr4(quadro) == sentinela)


def _neg_de_petr4(quadro: LiveBoard) -> float | int | str | None:
    raw = quadro.values("PETR4").get("NEG")
    return None if raw is None else raw.value

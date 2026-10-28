"""Ponte — traduz comandos em chamadas RTD e o laço do servidor TCP local.

Só stdlib. A sessão RTD (``SessaoRtd``) é do COM e vive na thread principal (STA): as
threads de socket só enfileiram comandos e escrevem linhas, nunca tocam na sessão. Por
isso o laço não bloqueia em socket nenhum: a thread principal alterna ``bombear`` (que, no
COM, é o ``PumpWaitingMessages`` que entrega os ``UpdateNotify``), a fila de comandos e o
``ciclo`` da ponte.
"""

import contextlib
import logging
import queue
import socket
import threading
from collections.abc import Callable
from typing import Protocol

from options_ponte.assinaturas import LimiteDeTopicos, RegistroDeTopicos
from options_ponte.protocolo import (
    TRYD_CONECTADO,
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
    classificar_valor,
    codificar,
    decodificar,
    topico_rtd,
)

__all__ = ["Ponte", "ServidorTcp", "SessaoRtd"]

_log = logging.getLogger(__name__)

INTERVALO_STATUS_S = 2.0
# Como o Excel: sem aviso por este tempo, pergunta ao servidor se ele ainda está vivo.
SILENCIO_ATE_HEARTBEAT_S = 5.0

_PASSO_S = 0.05  # quanto o laço bombeia por volta; limita a demora para atender um comando
_ESPERA_ACEITE_S = 0.05  # tempo máximo para a thread de aceite notar o fim
_ESPERA_CLIENTE_S = 1.0  # leitura sem dados volta ao laço; escrita que trava derruba o cliente
_BYTES_POR_LEITURA = 65536


class SessaoRtd(Protocol):
    """O que a ponte pede ao servidor RTD. Sempre chamada pela thread principal (STA)."""

    def conectar(self, id_: int, strings: tuple[str, str]) -> object:
        """``ConnectData``: assina o tópico e devolve o valor inicial, como veio."""
        ...

    def desconectar(self, id_: int) -> None:
        """``DisconnectData``."""
        ...

    def atualizar(self) -> list[tuple[int, object]]:
        """``RefreshData``: ``(id, valor)`` dos tópicos que mudaram desde a última chamada."""
        ...

    def vivo(self) -> bool:
        """``Heartbeat``: o servidor ainda responde?"""
        ...

    def avisos(self) -> int:
        """Quantos ``UpdateNotify`` o servidor já mandou (só cresce)."""
        ...

    def encerrar(self) -> None:
        """Desconecta o que sobrou e termina o servidor (``ServerTerminate``)."""
        ...


class Ponte:
    """Estado da ponte diante do Tryd: o que assinar, quando buscar e quando avisar o app.

    Sem threads e sem socket: ``tratar`` e ``ciclo`` devolvem as mensagens a difundir,
    e o tempo vem de ``relogio`` (monotônico, em segundos) e ``agora_iso`` (carimbo do
    ``Valor``), para o teste não depender de relógio real.

    Guarda o último ``Valor`` de cada tópico: quem assina um tópico que já estava assinado
    (o app que reconectou, um segundo cliente) recebe esse valor, com o carimbo original,
    em vez de esperar o tópico mudar. A assinatura repetida não chama ``conectar`` de novo.
    """

    def __init__(
        self,
        sessao: SessaoRtd,
        relogio: Callable[[], float],
        agora_iso: Callable[[], str],
        limite: int,
    ) -> None:
        self._sessao = sessao
        self._relogio = relogio
        self._agora_iso = agora_iso
        self._registro = RegistroDeTopicos(limite)
        self._ultimos: dict[tuple[str, str], Valor] = {}
        self._estado = TRYD_INICIANDO
        self._motivo: str | None = None
        self._avisos_vistos = 0
        self._ultimo_sinal = relogio()  # último aviso, ou última pergunta de Heartbeat
        self._ultimo_status = self._ultimo_sinal
        self._encerrando = False
        self._sessao_encerrada = False

    @property
    def encerrando(self) -> bool:
        """Verdadeiro depois de um ``Encerrar``: o laço do servidor deve parar."""
        return self._encerrando

    def tratar(self, cmd: Mensagem) -> list[Mensagem]:
        """Atende um comando do app. Mensagem que não é comando é ignorada."""
        match cmd:
            case Assinar(topicos=topicos):
                return self._assinar(topicos)
            case Cancelar(topicos=topicos):
                return self._cancelar(topicos)
            case Ping():
                return [Pong()]
            case Encerrar():
                self._encerrando = True
                return []
            case _:
                return []

    def ciclo(self) -> list[Mensagem]:
        """Uma volta do laço: busca o que mudou, confere o servidor e dá o status periódico."""
        agora = self._relogio()
        mensagens: list[Mensagem] = []
        avisos = self._sessao.avisos()
        if avisos > self._avisos_vistos:
            mensagens += self._buscar_mudancas(avisos, agora)
        elif agora - self._ultimo_sinal >= SILENCIO_ATE_HEARTBEAT_S:
            self._ultimo_sinal = agora
            mensagens += self._conferir_servidor()
        if any(isinstance(m, Status) for m in mensagens):  # o perdido já serviu de status
            self._ultimo_status = agora
        elif agora - self._ultimo_status >= INTERVALO_STATUS_S:
            self._ultimo_status = agora
            mensagens.append(self._status(self._motivo))
        return mensagens

    def encerrar(self) -> None:
        """Encerra a sessão RTD (uma vez só, por mais que seja chamado)."""
        if not self._sessao_encerrada:
            self._sessao_encerrada = True
            self._sessao.encerrar()

    def _assinar(self, topicos: tuple[tuple[str, str], ...]) -> list[Mensagem]:
        try:
            novos = self._registro.adicionar(topicos)
        except LimiteDeTopicos as erro:
            return [self._status(str(erro))]
        # antes de conectar os novos: aqui só existe valor guardado de tópico já assinado
        mensagens: list[Mensagem] = [
            self._ultimos[topico] for topico in dict.fromkeys(topicos) if topico in self._ultimos
        ]
        for posicao, (id_, (ticker, campo)) in enumerate(novos):
            try:
                inicial = self._sessao.conectar(id_, topico_rtd(ticker, campo))
            except Exception as erro:
                # o que não conectou não fica registrado: o app pode pedir de novo
                self._registro.remover(topico for _, topico in novos[posicao:])
                mensagens.append(self._perdeu(erro))
                return mensagens
            mensagens.append(self._guardar_valor(ticker, campo, inicial))
        if novos:
            self._marcar_conectado()
        return mensagens

    def _cancelar(self, topicos: tuple[tuple[str, str], ...]) -> list[Mensagem]:
        mensagens: list[Mensagem] = []
        for topico in topicos:
            self._ultimos.pop(topico, None)
        for id_ in self._registro.remover(topicos):
            try:
                self._sessao.desconectar(id_)
            except Exception as erro:
                mensagens.append(self._perdeu(erro))
        return mensagens

    def _buscar_mudancas(self, avisos: int, agora: float) -> list[Mensagem]:
        """``RefreshData`` do aviso novo. O aviso só conta como atendido se der certo.

        Se falhar, o próximo ``ciclo`` tenta de novo sem esperar outro ``UpdateNotify``: o
        servidor pode só avisar depois de um ``RefreshData`` bem-sucedido, e o feed ficaria
        parado com o Heartbeat dizendo que está tudo bem. O ``Status`` perdido sai uma vez, na
        passagem para perdido; depois quem repete é o status periódico.
        """
        try:
            mudancas = self._sessao.atualizar()
        except Exception as erro:
            ja_perdido = self._estado == TRYD_PERDIDO
            status = self._perdeu(erro)
            return [] if ja_perdido else [status]
        self._avisos_vistos = avisos
        self._ultimo_sinal = agora
        self._marcar_conectado()
        valores: list[Mensagem] = []
        for id_, bruto in mudancas:
            topico = self._registro.topico(id_)
            if topico is not None:  # cancelado enquanto o aviso estava a caminho
                valores.append(self._guardar_valor(*topico, bruto))
        return valores

    def _conferir_servidor(self) -> list[Mensagem]:
        try:
            vivo = self._sessao.vivo()
        except Exception as erro:
            return [self._perdeu(erro)]
        if vivo:
            self._marcar_conectado()
            return []
        silencio = f"{SILENCIO_ATE_HEARTBEAT_S:g} s sem aviso"
        return [self._marcar_perdido(f"o servidor RTD não respondeu ao Heartbeat após {silencio}")]

    def _perdeu(self, erro: Exception) -> Status:
        return self._marcar_perdido(f"{type(erro).__name__}: {erro}")

    def _marcar_perdido(self, motivo: str) -> Status:
        self._estado = TRYD_PERDIDO
        self._motivo = motivo
        return self._status(motivo)

    def _marcar_conectado(self) -> None:
        self._estado = TRYD_CONECTADO
        self._motivo = None

    def _status(self, motivo: str | None) -> Status:
        return Status(self._estado, motivo, self._registro.total)

    def _guardar_valor(self, ticker: str, campo: str, bruto: object) -> Valor:
        """O ``Valor`` do bruto recebido, já guardado como o último do tópico."""
        tipo_valor, valor = classificar_valor(bruto)
        recebido = Valor(ticker, campo, tipo_valor, valor, self._agora_iso())
        self._ultimos[(ticker, campo)] = recebido
        return recebido


class ServidorTcp:
    """Servidor TCP local (127.0.0.1): vários clientes, tudo que a ponte emite vai a todos.

    O ``bind`` acontece no construtor (porta ocupada falha logo; ``porta=0`` escolhe uma
    livre, que ``endereco`` informa). ``rodar`` serve uma vez só e é chamado pela thread que
    é dona da sessão RTD: ela bombeia, atende a fila de comandos e difunde as respostas. As
    threads de socket (aceite e uma de leitura por cliente) só enfileiram comandos.
    """

    def __init__(self, ponte: Ponte, porta: int, bombear: Callable[[float], None]) -> None:
        self._ponte = ponte
        self._bombear = bombear
        # create_server não liga SO_REUSEADDR no Windows (onde ele deixaria roubar a porta)
        self._escuta = socket.create_server(("127.0.0.1", porta))
        self._escuta.settimeout(_ESPERA_ACEITE_S)
        host, porta_real = self._escuta.getsockname()[:2]
        self._endereco = (str(host), int(porta_real))
        self._comandos: queue.Queue[Mensagem] = queue.Queue()
        self._clientes: list[socket.socket] = []
        self._leitores: list[threading.Thread] = []
        self._trava = threading.Lock()  # protege _clientes e _leitores
        self._fim = threading.Event()

    @property
    def endereco(self) -> tuple[str, int]:
        return self._endereco

    def rodar(self, parar: threading.Event) -> None:
        """Serve até ``parar`` ser acionado ou a ponte receber ``Encerrar``; depois a fecha."""
        aceite = threading.Thread(target=self._aceitar, name="ponte-aceite", daemon=True)
        aceite.start()
        try:
            while not parar.is_set():
                self._bombear(_PASSO_S)
                self._atender_comandos()
                if self._ponte.encerrando:
                    break
                self._difundir(self._ponte.ciclo())
        finally:
            self._fechar(aceite)
            self._ponte.encerrar()

    def _atender_comandos(self) -> None:
        while not self._ponte.encerrando:
            try:
                comando = self._comandos.get_nowait()
            except queue.Empty:
                return
            self._difundir(self._ponte.tratar(comando))

    def _difundir(self, mensagens: list[Mensagem]) -> None:
        if not mensagens:
            return
        linhas = b"".join(self._codificar(m) for m in mensagens)
        with self._trava:
            clientes = list(self._clientes)
        for cliente in clientes:
            try:
                cliente.sendall(linhas)
            except OSError:  # cliente que caiu ou travou: sai, a ponte segue
                self._derrubar(cliente)

    def _codificar(self, mensagem: Mensagem) -> bytes:
        """Uma mensagem que não codifica é descartada: o laço é dono da sessão COM e não morre."""
        try:
            return codificar(mensagem)
        except Exception as erro:
            _log.warning("mensagem %s descartada: %s", type(mensagem).__name__, erro)
            return b""

    def _derrubar(self, cliente: socket.socket) -> None:
        """Tira o cliente da difusão e acorda a thread dele, que é quem fecha o socket."""
        self._esquecer(cliente)
        with contextlib.suppress(OSError):
            cliente.shutdown(socket.SHUT_RDWR)

    def _esquecer(self, cliente: socket.socket) -> None:
        with self._trava, contextlib.suppress(ValueError):
            self._clientes.remove(cliente)

    def _fechar(self, aceite: threading.Thread) -> None:
        self._fim.set()
        aceite.join()
        self._escuta.close()
        with self._trava:
            clientes = list(self._clientes)
            leitores = list(self._leitores)
        for cliente in clientes:
            self._derrubar(cliente)
        for leitor in leitores:
            leitor.join(timeout=_ESPERA_CLIENTE_S)

    def _aceitar(self) -> None:
        while not self._fim.is_set():
            try:
                cliente, _ = self._escuta.accept()
            except TimeoutError:
                continue
            except OSError as erro:  # ex.: cliente que desistiu antes do accept (Windows e Linux)
                _log.warning("falha ao aceitar conexão: %s", erro)
                self._fim.wait(_ESPERA_ACEITE_S)
                continue
            cliente.settimeout(_ESPERA_CLIENTE_S)
            # linhas pequenas e sem espera por ACK: atraso aqui vira atraso de cotação
            cliente.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            leitor = threading.Thread(
                target=self._ler, args=(cliente,), name="ponte-leitura", daemon=True
            )
            with self._trava:
                self._clientes.append(cliente)
                self._leitores.append(leitor)
            leitor.start()

    def _ler(self, cliente: socket.socket) -> None:
        try:
            with contextlib.suppress(OSError):  # reset do cliente, ou o shutdown de _derrubar
                self._enfileirar_linhas(cliente)
        finally:
            self._esquecer(cliente)
            cliente.close()

    def _enfileirar_linhas(self, cliente: socket.socket) -> None:
        resto = b""
        while not self._fim.is_set():
            try:
                dados = cliente.recv(_BYTES_POR_LEITURA)
            except TimeoutError:
                continue
            if not dados:
                return
            *linhas, resto = (resto + dados).split(b"\n")
            for linha in linhas:
                if linha.strip():
                    self._enfileirar(linha)

    def _enfileirar(self, linha: bytes) -> None:
        try:
            self._comandos.put(decodificar(linha))
        except ErroDeProtocolo as erro:
            _log.warning("linha recusada: %s", erro)

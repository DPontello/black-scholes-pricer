"""Do RTD ao quadro: ``TrydBridgeClient`` com ``ServidorTcp``/``Ponte`` reais (RTD falso).

Mostra o que a Task 10 precisa: o zero inicial do RTD chega ao quadro, mas não o marca como
carregado; só uma atualização de verdade (ou ``TEMPO_CARGA_S``) marca.
"""

import threading
import time
from collections.abc import Iterator

import pytest

from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.client import TrydBridgeClient
from options_engine.adapters.outbound.tryd.settings import TEMPO_CARGA_S
from options_ponte.servidor import Ponte, ServidorTcp
from tests.adapters.tryd._ponte_falsa import esperar

AGORA = "2026-10-28T12:03:00-03:00"
TOPICO = ("PETRK500", "OCP")


class SessaoRtdFalsa:
    """``SessaoRtd`` em memória: o ``ConnectData`` devolve o zero inicial, como o Tryd."""

    def __init__(self) -> None:
        self.conectados: list[tuple[int, tuple[str, str]]] = []
        self._pendentes: list[tuple[int, object]] = []
        self._avisos = 0
        self._trava = threading.Lock()

    def avisar(self, id_: int, valor: object) -> None:
        with self._trava:
            self._pendentes.append((id_, valor))
            self._avisos += 1

    def conectar(self, id_: int, strings: tuple[str, str]) -> object:
        self.conectados.append((id_, strings))
        return 0.0

    def desconectar(self, id_: int) -> None:
        pass

    def atualizar(self) -> list[tuple[int, object]]:
        with self._trava:
            mudancas, self._pendentes = self._pendentes, []
        return mudancas

    def vivo(self) -> bool:
        return True

    def avisos(self) -> int:
        with self._trava:
            return self._avisos

    def encerrar(self) -> None:
        pass


class Montagem:
    def __init__(self) -> None:
        self.sessao = SessaoRtdFalsa()
        ponte = Ponte(self.sessao, time.monotonic, lambda: AGORA, limite=20)
        self.servidor = ServidorTcp(ponte, 0, lambda _passo: time.sleep(0.002))
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self.servidor.rodar, args=(self.parar,), daemon=True)
        self.relogio = [0.0]
        self.quadro = LiveBoard(monotonic=lambda: self.relogio[0])
        self.cliente = TrydBridgeClient(
            self.quadro, "127.0.0.1", self.servidor.endereco[1], reconnect_interval_s=0.05
        )

    def assinar(self) -> None:
        self.cliente.ensure_subscribed(frozenset({TOPICO}))
        self.thread.start()
        self.cliente.start()


@pytest.fixture
def montagem() -> Iterator[Montagem]:
    montagem = Montagem()
    yield montagem
    montagem.cliente.stop()
    montagem.parar.set()
    if montagem.thread.is_alive():
        montagem.thread.join(timeout=5)


def test_logo_apos_assinar_o_zero_inicial_chega_mas_o_ativo_nao_esta_carregado(
    montagem: Montagem,
) -> None:
    montagem.assinar()
    esperar(lambda: "OCP" in montagem.quadro.values("PETRK500"))  # o ConnectData já chegou
    zero = montagem.quadro.values("PETRK500")["OCP"]
    assert (zero.kind, zero.value) == ("float", 0.0)
    assert not montagem.quadro.is_loaded("PETRK500")


def test_a_primeira_atualizacao_de_verdade_carrega(montagem: Montagem) -> None:
    montagem.assinar()
    esperar(lambda: "OCP" in montagem.quadro.values("PETRK500"))
    assert not montagem.quadro.is_loaded("PETRK500")
    montagem.sessao.avisar(montagem.sessao.conectados[0][0], 4.42)  # o Tryd carregou o tópico
    esperar(lambda: montagem.quadro.is_loaded("PETRK500"))
    assert montagem.quadro.values("PETRK500")["OCP"].value == 4.42


def test_sem_atualizacao_o_ativo_carrega_depois_de_tempo_carga_s(montagem: Montagem) -> None:
    montagem.assinar()
    esperar(lambda: "OCP" in montagem.quadro.values("PETRK500"))
    montagem.relogio[0] = TEMPO_CARGA_S - 0.1
    assert not montagem.quadro.is_loaded("PETRK500")
    montagem.relogio[0] = TEMPO_CARGA_S
    assert montagem.quadro.is_loaded("PETRK500")  # sem preço: lado vazio de verdade


def test_app_que_reconecta_recebe_o_reemitido_com_o_inicial_do_que_a_ponte_guardou(
    montagem: Montagem,
) -> None:
    montagem.assinar()
    esperar(lambda: "OCP" in montagem.quadro.values("PETRK500"))
    novos: list[TrydBridgeClient] = []

    def reconectar() -> LiveBoard:
        """Um app novo (quadro novo) assinando o mesmo tópico na ponte que já estava no ar."""
        quadro = LiveBoard(monotonic=lambda: montagem.relogio[0])
        cliente = TrydBridgeClient(
            quadro, "127.0.0.1", montagem.servidor.endereco[1], reconnect_interval_s=0.05
        )
        novos.append(cliente)
        cliente.ensure_subscribed(frozenset({TOPICO}))
        cliente.start()
        esperar(lambda: "OCP" in quadro.values("PETRK500"))
        return quadro

    try:
        antes = reconectar()  # a ponte só tem o zero inicial guardado
        assert antes.values("PETRK500")["OCP"].value == 0.0
        assert not antes.is_loaded("PETRK500")

        montagem.sessao.avisar(montagem.sessao.conectados[0][0], 4.42)
        esperar(lambda: montagem.quadro.is_loaded("PETRK500"))
        depois = reconectar()  # agora a ponte guarda a atualização de verdade
        esperar(lambda: depois.values("PETRK500")["OCP"].value == 4.42)
        assert depois.is_loaded("PETRK500")
        assert len(montagem.sessao.conectados) == 1  # nunca assinou de novo no RTD
    finally:
        for cliente in novos:
            cliente.stop()

"""Do RTD ao quadro: ``TrydBridgeClient`` com ``ServidorTcp``/``Ponte`` reais (RTD falso).

Mostra o que a Task 10 precisa: o zero inicial do RTD chega ao quadro, mas não o marca como
carregado; só uma atualização de verdade (ou ``TEMPO_CARGA_S``) marca.
"""

import threading
import time
from collections.abc import Iterator

import pytest

from options_engine.adapters.outbound.tryd.board import LiveBoard, RawValue
from options_engine.adapters.outbound.tryd.client import BridgeHealth, TrydBridgeClient
from options_engine.adapters.outbound.tryd.settings import TEMPO_CARGA_S
from options_ponte.servidor import ESPERA_TRYD_ABRIR_S, Ponte, ServidorTcp
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
        ponte = Ponte(lambda: self.sessao, time.monotonic, lambda: AGORA, limite=20)
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


class TrydNaMaquina:
    """Os ``tryd.exe`` rodando (o teste fecha e reabre) e o ``CoCreateInstance``."""

    def __init__(self) -> None:
        self.pids = frozenset({100})
        self.sessoes: list[SessaoRtdFalsa] = []
        self.listagens = 0

    def processos(self) -> frozenset[int]:
        self.listagens += 1
        return self.pids

    def abrir(self) -> SessaoRtdFalsa:
        sessao = SessaoRtdFalsa()
        self.sessoes.append(sessao)
        return sessao


def test_tryd_fechado_e_reaberto_com_o_app_aberto_volta_ao_vivo_sozinho() -> None:
    tryd = TrydNaMaquina()
    relogio = [0.0]  # o da ponte; só anda quando o teste quer
    ponte = Ponte(
        tryd.abrir, lambda: relogio[0], lambda: AGORA, limite=20, processos_tryd=tryd.processos
    )
    servidor = ServidorTcp(ponte, 0, lambda _passo: time.sleep(0.002))
    parar = threading.Event()
    laco = threading.Thread(target=servidor.rodar, args=(parar,), daemon=True)
    quadro = LiveBoard(monotonic=lambda: 0.0)  # TEMPO_CARGA_S não passa: só atualização carrega
    cliente = TrydBridgeClient(quadro, "127.0.0.1", servidor.endereco[1], reconnect_interval_s=0.05)
    cliente.ensure_subscribed(frozenset({TOPICO}))
    laco.start()
    cliente.start()
    try:
        esperar(lambda: "OCP" in quadro.values("PETRK500"))
        (antiga,) = tryd.sessoes
        antiga.avisar(antiga.conectados[0][0], 4.42)
        esperar(lambda: quadro.is_loaded("PETRK500"))

        tryd.pids = frozenset()  # o usuário fecha o Tryd
        relogio[0] = 2.0
        esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
        assert quadro.values("PETRK500")["OCP"].value == 4.42

        tryd.pids = frozenset({200})  # e o reabre
        listagens = tryd.listagens
        relogio[0] = 4.0
        esperar(lambda: tryd.listagens > listagens)
        relogio[0] = 4.0 + ESPERA_TRYD_ABRIR_S
        esperar(lambda: quadro.values("PETRK500").get("OCP") == _zero_inicial())
        assert not quadro.is_loaded("PETRK500")  # o 4,42 era do Tryd que fechou
        nova = tryd.sessoes[1]
        assert nova.conectados == antiga.conectados  # o mesmo tópico, com o mesmo id
        nova.avisar(nova.conectados[0][0], 4.5)
        esperar(lambda: quadro.is_loaded("PETRK500"))
        assert quadro.values("PETRK500")["OCP"].value == 4.5
        assert cliente.health() is BridgeHealth.CONECTADA
        assert len(tryd.sessoes) == 2
    finally:
        cliente.stop()
        parar.set()
        laco.join(timeout=5)


def _zero_inicial() -> RawValue:
    return RawValue("float", 0.0, 0.0, initial=True)

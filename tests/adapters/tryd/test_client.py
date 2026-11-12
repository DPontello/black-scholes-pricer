"""``TrydBridgeClient`` contra uma ponte falsa em TCP (porta 0): assinatura, reconexão e saúde."""

import logging
import socket
import threading
import time
from collections.abc import Callable, Iterator
from functools import partial

import pytest

from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.client import BridgeHealth, TrydBridgeClient
from options_engine.adapters.outbound.tryd.settings import TEMPO_CARGA_S
from options_ponte.protocolo import Assinar, Cancelar, Encerrar, Ping, Pong, Status, Valor
from tests.adapters.tryd._ponte_falsa import PonteFalsa, entregar, esperar, porta_sem_ninguem

AGORA = "2026-10-28T12:03:00-03:00"
RECONEXAO_S = 0.05  # o padrão é 2 s; o teste não espera isso

OCP = ("PETRK500", "OCP")
OVD = ("PETRK500", "OVD")
ULT = ("PETR4", "ULT")


class Ambiente:
    """Cria clientes e pontes falsas e os encerra no fim do teste."""

    def __init__(self) -> None:
        self._clientes: list[TrydBridgeClient] = []
        self._pontes: list[PonteFalsa] = []

    def ponte(self, porta: int = 0, **kwargs: bool) -> PonteFalsa:
        ponte = PonteFalsa(porta, **kwargs)
        self._pontes.append(ponte)
        return ponte

    def cliente(
        self,
        quadro: LiveBoard,
        porta: int,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> TrydBridgeClient:
        cliente = TrydBridgeClient(
            quadro, "127.0.0.1", porta, monotonic, reconnect_interval_s=RECONEXAO_S
        )
        self._clientes.append(cliente)
        return cliente

    def encerrar(self) -> None:
        for cliente in self._clientes:
            cliente.stop()
        for ponte in self._pontes:
            ponte.fechar()


@pytest.fixture
def ambiente() -> Iterator[Ambiente]:
    ambiente = Ambiente()
    yield ambiente
    ambiente.encerrar()


def _assinaturas(ponte: PonteFalsa) -> list[frozenset[tuple[str, str]]]:
    return [frozenset(m.topicos) for m in ponte.recebidas() if isinstance(m, Assinar)]


def _cancelamentos(ponte: PonteFalsa) -> list[frozenset[tuple[str, str]]]:
    return [frozenset(m.topicos) for m in ponte.recebidas() if isinstance(m, Cancelar)]


def test_cliente_assina_reconecta_e_reassina(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    ponte.valores = {OCP: Valor("PETRK500", "OCP", "float", 4.42, AGORA)}
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({OCP, OVD}))
    cliente.start()

    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP, OVD})])
    esperar(lambda: "OCP" in quadro.values("PETRK500"))
    assert quadro.values("PETRK500")["OCP"].value == 4.42
    assert quadro.is_loaded("PETRK500")

    porta = ponte.porta
    ponte.fechar()  # a ponte cai...
    nova = ambiente.ponte(porta)  # ...e volta na mesma porta
    esperar(lambda: _assinaturas(nova) == [frozenset({OCP, OVD})])  # reenvia tudo, uma vez


def test_cliente_reconecta_quando_a_ponte_so_derruba_a_conexao(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))
    cliente.start()
    esperar(lambda: _assinaturas(ponte) == [frozenset({ULT})])
    ponte.derrubar_clientes()
    esperar(lambda: _assinaturas(ponte) == [frozenset({ULT}), frozenset({ULT})])


def test_ensure_subscribed_envia_so_a_diferenca(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    cliente.start()
    cliente.ensure_subscribed(frozenset({OCP}))
    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP})])

    cliente.ensure_subscribed(frozenset({OCP, OVD}))  # só o OVD é novo
    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP}), frozenset({OVD})])

    cliente.ensure_subscribed(frozenset({OVD, ULT}))  # sai o OCP, entra o ULT
    esperar(lambda: _cancelamentos(ponte) == [frozenset({OCP})])
    esperar(lambda: _assinaturas(ponte)[-1] == frozenset({ULT}))

    cliente.ensure_subscribed(frozenset({OVD, ULT}))  # nada mudou: nada a enviar
    cliente.ensure_subscribed(frozenset())  # esvazia tudo
    esperar(lambda: _cancelamentos(ponte) == [frozenset({OCP}), frozenset({OVD, ULT})])
    assert _assinaturas(ponte) == [frozenset({OCP}), frozenset({OVD}), frozenset({ULT})]


def test_assinatura_pedida_com_a_ponte_fora_vai_na_primeira_conexao(ambiente: Ambiente) -> None:
    porta = porta_sem_ninguem()
    cliente = ambiente.cliente(LiveBoard(), porta)
    cliente.ensure_subscribed(frozenset({OCP}))
    cliente.start()
    time.sleep(3 * RECONEXAO_S)  # algumas tentativas sem ninguém ouvindo
    ponte = ambiente.ponte(porta)
    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP})])


def _valor_de(quadro: LiveBoard, ticker: str, campo: str) -> float | int | str | None:
    cru = quadro.values(ticker).get(campo)
    return None if cru is None else cru.value


def _valor_de_e(
    quadro: LiveBoard, ticker: str, campo: str, esperado: float | int | str | None
) -> bool:
    return _valor_de(quadro, ticker, campo) == esperado


def _aguardando_carga(quadro: LiveBoard, ticker: str) -> bool:
    return quadro.values(ticker) == {} and not quadro.is_loaded(ticker)


def test_ativo_cancelado_e_assinado_de_novo_nao_herda_valores_nem_carga(
    ambiente: Ambiente,
) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    ponte.valores = {OCP: Valor("PETRK500", "OCP", "float", 4.42, AGORA)}
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({OCP}))
    cliente.start()
    esperar(lambda: "OCP" in quadro.values("PETRK500"))
    assert quadro.is_loaded("PETRK500")

    cliente.ensure_subscribed(frozenset())  # o ativo sai de vez
    assert _aguardando_carga(quadro, "PETRK500")

    ponte.valores = {}  # a ponte "perdeu" o último valor ao receber o Cancelar
    cliente.ensure_subscribed(frozenset({OCP}))
    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP})] * 2)
    assert _aguardando_carga(quadro, "PETRK500")  # sem Valor novo e sem passar TEMPO_CARGA_S

    ponte.enviar(Valor("PETRK500", "OCP", "float", 0.0, AGORA, inicial=True))  # zero do RTD
    esperar(lambda: quadro.values("PETRK500").get("OCP") is not None)
    assert quadro.values("PETRK500")["OCP"].value == 0.0  # e não o 4.42 de antes
    assert not quadro.is_loaded("PETRK500")  # o inicial não carrega
    ponte.enviar(Valor("PETRK500", "OCP", "float", 4.5, AGORA))
    esperar(lambda: quadro.is_loaded("PETRK500"))


def test_ativo_cancelado_e_assinado_de_novo_carrega_com_o_tempo(ambiente: Ambiente) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.start()
    cliente.ensure_subscribed(frozenset({ULT}))
    esperar(lambda: _assinaturas(ponte) == [frozenset({ULT})])
    t[0] = 5.0
    assert quadro.is_loaded("PETR4")  # passou o tempo
    cliente.ensure_subscribed(frozenset())
    cliente.ensure_subscribed(frozenset({ULT}))  # volta em t = 5
    esperar(lambda: _assinaturas(ponte) == [frozenset({ULT})] * 2)
    assert not quadro.is_loaded("PETR4")
    t[0] = 5.0 + TEMPO_CARGA_S
    assert quadro.is_loaded("PETR4")


def test_ensure_subscribed_inicia_a_assinatura_dos_ativos_novos_sem_ajuda_da_composicao(
    ambiente: Ambiente,
) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))  # nenhum mark_subscribed por fora
    assert not quadro.is_loaded("PETR4")
    t[0] = TEMPO_CARGA_S
    assert quadro.is_loaded("PETR4")  # a contagem de carga começou na assinatura


def test_ativo_novo_recomeca_o_quadro_mesmo_com_resto_de_antes(ambiente: Ambiente) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta)
    quadro.mark_subscribed(["PETR4"])  # resto de uma assinatura que o cliente não conhece
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    assert quadro.is_loaded("PETR4")
    t[0] = 50.0
    cliente.ensure_subscribed(frozenset({ULT}))  # para o cliente, o ativo é novo
    assert _aguardando_carga(quadro, "PETR4")


def test_valor_em_transito_depois_do_cancelar_nao_sobra_para_a_proxima_assinatura(
    ambiente: Ambiente,
) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({OCP}))
    cliente.start()
    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP})])
    ponte.enviar(Valor("PETRK500", "OCP", "float", 4.42, AGORA))
    esperar(lambda: quadro.is_loaded("PETRK500"))

    cliente.ensure_subscribed(frozenset())  # o ativo sai: forget + Cancelar
    # um Valor que a ponte emitiu antes de processar o Cancelar chega depois do forget
    ponte.enviar(Valor("PETRK500", "OCP", "float", 4.43, AGORA))
    ponte.enviar(Status("perdido", None, 0))  # marca na fila: o Valor acima já foi tratado
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
    assert _aguardando_carga(quadro, "PETRK500")  # ninguém quer o ativo: nada fica no quadro

    t[0] = 600.0  # minutos depois o usuário volta ao ativo
    cliente.ensure_subscribed(frozenset({OCP}))
    esperar(lambda: _assinaturas(ponte) == [frozenset({OCP})] * 2)
    ponte.enviar(Valor("PETRK500", "OCP", "float", 0.0, AGORA, inicial=True))  # zero do ConnectData
    esperar(lambda: "OCP" in quadro.values("PETRK500"))
    assert quadro.values("PETRK500")["OCP"].value == 0.0  # e não o 4.43 de antes
    assert not quadro.is_loaded("PETRK500")


def test_valor_de_ativo_que_o_cliente_nao_assinou_e_ignorado(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))
    cliente.start()
    esperar(lambda: _assinaturas(ponte) == [frozenset({ULT})])
    # a ponte difunde os tópicos de todos os clientes (espiar, instância antiga do app)
    ponte.enviar(
        Valor("VALE3", "ULT", "float", 61.1, AGORA), Valor("PETR4", "ULT", "float", 38.4, AGORA)
    )
    esperar(lambda: quadro.is_loaded("PETR4"))
    assert quadro.values("VALE3") == {}
    assert not quadro.is_loaded("VALE3")


def test_ativo_com_outro_topico_ainda_desejado_nao_e_esquecido(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.start()
    cliente.ensure_subscribed(frozenset({OCP, OVD}))
    esperar(lambda: _assinaturas(ponte) != [])
    ponte.enviar(Valor("PETRK500", "OVD", "float", 4.47, AGORA))
    esperar(lambda: "OVD" in quadro.values("PETRK500"))
    cliente.ensure_subscribed(frozenset({OVD}))  # só o OCP sai; o ativo continua assinado
    assert quadro.values("PETRK500")["OVD"].value == 4.47
    assert quadro.is_loaded("PETRK500")


def test_reconexao_a_uma_ponte_nova_reinicia_o_quadro_dos_ativos_desejados(
    ambiente: Ambiente,
) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    ponte.valores = {OCP: Valor("PETRK500", "OCP", "float", 4.42, AGORA)}
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({OCP}))
    cliente.start()
    esperar(lambda: "OCP" in quadro.values("PETRK500"))
    assert quadro.is_loaded("PETRK500")

    porta = ponte.porta
    ponte.fechar()
    t[0] = 50.0
    nova = ambiente.ponte(porta)  # ponte relançada: não guarda nada, o RTD recomeça do zero
    esperar(lambda: _assinaturas(nova) == [frozenset({OCP})])
    assert _aguardando_carga(quadro, "PETRK500")  # nada herdado da ponte anterior
    t[0] = 50.0 + TEMPO_CARGA_S
    assert quadro.is_loaded("PETRK500")


def test_reconexao_a_mesma_ponte_recupera_os_valores_que_ela_reemite(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    ponte.valores = {OCP: Valor("PETRK500", "OCP", "float", 4.42, AGORA)}
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({OCP}))
    cliente.start()
    esperar(lambda: "OCP" in quadro.values("PETRK500"))
    ponte.derrubar_clientes()
    esperar(lambda: ponte.total_aceitas == 2)
    esperar(lambda: len(_assinaturas(ponte)) == 2)
    esperar(lambda: "OCP" in quadro.values("PETRK500"))  # reemitido na nova assinatura
    assert quadro.values("PETRK500")["OCP"].value == 4.42
    assert quadro.is_loaded("PETRK500")


def test_sem_assinatura_nao_manda_assinar_vazio(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    cliente.ensure_subscribed(frozenset())
    time.sleep(0.1)  # asserção negativa: dá tempo de a conexão mandar algo, se fosse mandar
    assert ponte.recebidas() == []


def test_saude_por_idade_da_ultima_mensagem(ambiente: Ambiente) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta, monotonic=lambda: t[0])
    assert cliente.health() is BridgeHealth.DESCONECTADA  # nunca ouviu a ponte
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ponte.enviar(Status("conectado", None, 2))
    esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)
    saude = {}
    for instante in (0.0, 9.9, 10.0, 10.1, 29.9, 30.0, 30.1):
        t[0] = instante
        saude[instante] = cliente.health()
    assert saude == {
        0.0: BridgeHealth.CONECTADA,
        9.9: BridgeHealth.CONECTADA,
        10.0: BridgeHealth.ATRASADA,
        10.1: BridgeHealth.ATRASADA,
        29.9: BridgeHealth.ATRASADA,
        30.0: BridgeHealth.DESCONECTADA,
        30.1: BridgeHealth.DESCONECTADA,
    }


def test_valor_e_pong_tambem_contam_como_mensagem_da_ponte(ambiente: Ambiente) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta, monotonic=lambda: t[0])
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    t[0] = 40.0
    assert cliente.health() is BridgeHealth.DESCONECTADA
    ponte.enviar(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)
    t[0] = 55.0
    assert cliente.health() is BridgeHealth.ATRASADA
    ponte.enviar(Pong())
    esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)


def test_status_perdido_recente_deixa_a_saude_atrasada(ambiente: Ambiente) -> None:
    t = [0.0]
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta, monotonic=lambda: t[0])
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ponte.enviar(Status("perdido", "Heartbeat do servidor RTD falhou", 4))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)  # mensagem de agora, mas Tryd caiu
    t[0] = 31.0
    assert cliente.health() is BridgeHealth.DESCONECTADA  # sem notícia há 30 s: perdida
    t[0] = 32.0
    ponte.enviar(Status("conectado", None, 4))
    esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)  # o Tryd voltou


def _cliente_de_pe(
    ambiente: Ambiente, t: list[float]
) -> tuple[PonteFalsa, LiveBoard, TrydBridgeClient]:
    """Ponte falsa de pé e cliente conectado, com PETR4 assinado e o relógio em ``t``."""
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta, monotonic=lambda: t[0])
    cliente.ensure_subscribed(frozenset({("PETR4", "NEG")}))
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    return ponte, quadro, cliente


def test_status_perdido_repetido_por_mais_de_30_s_deixa_a_saude_desconectada(
    ambiente: Ambiente,
) -> None:
    # A ponte de pé com o Tryd fechado repete o Status "perdido" de tempos em tempos: cada um
    # renova a idade da última mensagem, mas não o prazo de 30 s contado da entrada no estado.
    t = [0.0]
    ponte, quadro, cliente = _cliente_de_pe(ambiente, t)
    ponte.enviar(Status("perdido", "Heartbeat do servidor RTD falhou", 4))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)  # entrou em t = 0
    for instante in (9.0, 19.0, 29.0):
        entregar(
            ponte, quadro, t, instante, Status("perdido", "Heartbeat do servidor RTD falhou", 4)
        )
        assert cliente.health() is BridgeHealth.ATRASADA
    t[0] = 29.9
    assert cliente.health() is BridgeHealth.ATRASADA  # última mensagem há 0,9 s; perdido há 29,9 s
    t[0] = 30.1
    assert (
        cliente.health() is BridgeHealth.DESCONECTADA
    )  # perdido há 30,1 s, mesmo com a ponte falando
    entregar(ponte, quadro, t, 31.0, Status("perdido", None, 4))
    assert cliente.health() is BridgeHealth.DESCONECTADA  # o Status seguinte não zera a contagem
    entregar(ponte, quadro, t, 32.0, Status("conectado", None, 4))
    assert cliente.health() is BridgeHealth.CONECTADA  # o Tryd voltou


def test_status_iniciando_e_perdido_contam_como_um_estado_so_para_o_prazo(
    ambiente: Ambiente,
) -> None:
    t = [0.0]
    ponte, quadro, cliente = _cliente_de_pe(ambiente, t)
    ponte.enviar(Status("iniciando", None, 0))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
    entregar(ponte, quadro, t, 20.0, Status("perdido", "RTD caiu", 0))
    entregar(ponte, quadro, t, 29.9, Status("perdido", "RTD caiu", 0))
    assert cliente.health() is BridgeHealth.ATRASADA
    t[0] = 30.1
    assert cliente.health() is BridgeHealth.DESCONECTADA  # contado do "iniciando" de t = 0


def test_status_conectado_zera_a_contagem_do_prazo_de_30_s(ambiente: Ambiente) -> None:
    t = [0.0]
    ponte, quadro, cliente = _cliente_de_pe(ambiente, t)
    ponte.enviar(Status("perdido", None, 1))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
    entregar(ponte, quadro, t, 25.0, Status("conectado", None, 1))
    assert cliente.health() is BridgeHealth.CONECTADA
    entregar(ponte, quadro, t, 26.0, Status("perdido", None, 1))  # recomeça em t = 26
    entregar(ponte, quadro, t, 55.0, Status("perdido", None, 1))
    # 29 s desde t = 26; contado de t = 0 (sem o "conectado" no meio) já seria DESCONECTADA
    assert cliente.health() is BridgeHealth.ATRASADA
    t[0] = 56.1
    assert cliente.health() is BridgeHealth.DESCONECTADA


def test_status_perdido_de_uma_conexao_anterior_nao_conta_para_o_prazo_da_nova(
    ambiente: Ambiente,
) -> None:
    t = [0.0]
    ponte, quadro, cliente = _cliente_de_pe(ambiente, t)
    ponte.enviar(Status("perdido", None, 1))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
    t[0] = 20.0
    ponte.derrubar_clientes()
    esperar(lambda: ponte.total_aceitas == 2)  # a ponte pode ser outra: o estado antigo não vale
    esperar(lambda: ponte.conexoes() == 1)
    entregar(ponte, quadro, t, 40.0)  # sem Status nenhum nesta conexão: só um Valor
    assert cliente.health() is BridgeHealth.CONECTADA


def test_status_iniciando_deixa_a_saude_atrasada_ate_o_tryd_conectar(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ponte.enviar(Status("iniciando", None, 0))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)  # ponte no ar, Tryd ainda não
    ponte.enviar(Status("conectado", None, 2))
    esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)
    ponte.enviar(Status("iniciando", None, 2))  # e se voltar a iniciar, volta a limitar
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)


def test_valor_e_pong_nao_levantam_o_limite_de_um_status_iniciando_ou_perdido(
    ambiente: Ambiente,
) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    for rodada, tryd in enumerate(("iniciando", "perdido")):
        preco = 38.4 + rodada
        ponte.enviar(Status(tryd, None, 1))
        esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
        ponte.enviar(Valor("PETR4", "ULT", "float", preco, AGORA), Pong())
        esperar(partial(_valor_de_e, quadro, "PETR4", "ULT", preco))
        time.sleep(0.05)  # e o Pong que veio junto
        assert cliente.health() is BridgeHealth.ATRASADA
        ponte.enviar(Status("conectado", None, 1))
        esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)


def _petr4_carregado(
    ambiente: Ambiente, t: list[float]
) -> tuple[PonteFalsa, LiveBoard, TrydBridgeClient]:
    """Cliente com ULT e NEG de PETR4 assinados, Tryd conectado e ULT = 38,4 no quadro."""
    ponte = ambiente.ponte()
    quadro = LiveBoard(monotonic=lambda: t[0])
    cliente = ambiente.cliente(quadro, ponte.porta, monotonic=lambda: t[0])
    cliente.ensure_subscribed(frozenset({ULT, ("PETR4", "NEG")}))
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ult = Valor("PETR4", "ULT", "float", 38.4, AGORA)
    entregar(ponte, quadro, t, 1.0, Status("conectado", None, 2), ult)
    return ponte, quadro, cliente


def test_conectado_depois_de_iniciando_recomeca_o_quadro_dos_ativos_desejados(
    ambiente: Ambiente,
) -> None:
    # A ponte só fica em "iniciando" sem sessão RTD: o "conectado" seguinte é o Tryd reaberto, e o
    # que o quadro tinha é do Tryd que fechou.
    t = [0.0]
    ponte, quadro, _ = _petr4_carregado(ambiente, t)
    entregar(ponte, quadro, t, 5.0, Status("iniciando", "Tryd fechado", 2))
    assert _valor_de(quadro, "PETR4", "ULT") == 38.4  # com o Tryd fechado o quadro não muda
    t[0] = 60.0
    ponte.enviar(
        Status("conectado", None, 2), Valor("PETR4", "ULT", "float", 0.0, AGORA, inicial=True)
    )
    esperar(partial(_valor_de_e, quadro, "PETR4", "ULT", 0.0))
    assert set(quadro.values("PETR4")) == {"ULT"}  # o NEG do Tryd que fechou foi esquecido
    assert not quadro.is_loaded("PETR4")  # o zero inicial não carrega; a contagem recomeça
    t[0] = 60.0 + TEMPO_CARGA_S
    assert quadro.is_loaded("PETR4")


def test_conectado_depois_de_perdido_mantem_o_quadro(ambiente: Ambiente) -> None:
    # Do "perdido" a sessão RTD é a mesma, e a ponte não reenvia o que já mandou.
    t = [0.0]
    ponte, quadro, _ = _petr4_carregado(ambiente, t)
    entregar(ponte, quadro, t, 5.0, Status("perdido", "RPC indisponível", 2))
    entregar(ponte, quadro, t, 60.0, Status("conectado", None, 2))
    assert _valor_de(quadro, "PETR4", "ULT") == 38.4
    assert quadro.is_loaded("PETR4")


def test_status_de_uma_conexao_anterior_nao_limita_a_saude_da_nova(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ponte.enviar(Status("perdido", "RTD caiu", 1))
    esperar(lambda: cliente.health() is BridgeHealth.ATRASADA)
    ponte.derrubar_clientes()
    esperar(lambda: ponte.total_aceitas == 2)  # reconectou; ainda não veio Status nenhum
    ponte.enviar(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    esperar(lambda: cliente.health() is BridgeHealth.CONECTADA)


def test_mensagem_invalida_da_ponte_e_logada_e_ignorada(
    ambiente: Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    with caplog.at_level(logging.WARNING):
        ponte.enviar(
            b"isto nao e json\n",
            b'{"tipo":"valor","ticker":"PETR4"}\n',  # campos que faltam
            b'{"tipo":"desconhecido"}\n',
            Valor("PETR4", "ULT", "float", 38.4, AGORA),
        )
        esperar(lambda: "ULT" in quadro.values("PETR4"))  # a thread seguiu e leu o que veio depois
    valor = quadro.values("PETR4")["ULT"]
    assert (valor.kind, valor.value) == ("float", 38.4)
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 3
    assert ponte.total_aceitas == 1  # nenhuma reconexão: a mesma conexão


class QuadroQueFalhaUmaVez(LiveBoard):
    def __init__(self) -> None:
        super().__init__()
        self.falhou = False

    def apply(self, valor: Valor) -> None:
        if not self.falhou:
            self.falhou = True
            raise RuntimeError("defeito no quadro")
        super().apply(valor)


def test_falha_inesperada_ao_tratar_uma_mensagem_e_logada_e_a_thread_reconecta(
    ambiente: Ambiente, caplog: pytest.LogCaptureFixture
) -> None:
    ponte = ambiente.ponte()
    ponte.valores = {OCP: Valor("PETRK500", "OCP", "float", 4.42, AGORA)}
    quadro = QuadroQueFalhaUmaVez()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({OCP}))
    with caplog.at_level(logging.ERROR):
        cliente.start()
        esperar(lambda: "OCP" in quadro.values("PETRK500"))  # o 2º Valor, depois de reconectar
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
    assert ponte.total_aceitas == 2


def test_linha_partida_em_pedacos_e_remontada(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    quadro = LiveBoard()
    cliente = ambiente.cliente(quadro, ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ponte.enviar(b'{"tipo":"valor","ticker":"PETR4","campo":"ULT",')
    time.sleep(0.05)
    ponte.enviar(b'"tipo_valor":"float","valor":38.4,"instante":"x"}\n')
    esperar(lambda: "ULT" in quadro.values("PETR4"))


def test_shutdown_bridge_manda_encerrar_pela_conexao_aberta(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    cliente.ensure_subscribed(frozenset({ULT}))
    cliente.start()
    esperar(lambda: _assinaturas(ponte) == [frozenset({ULT})])  # a conexão está de pé
    cliente.shutdown_bridge()
    esperar(lambda: Encerrar() in ponte.recebidas())
    assert ponte.total_aceitas == 1  # usou a conexão do cliente, não abriu outra


def test_shutdown_bridge_sem_conexao_abre_uma_so_para_encerrar(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)  # nunca iniciado
    cliente.shutdown_bridge()
    esperar(lambda: Encerrar() in ponte.recebidas())


def test_shutdown_bridge_sem_ponte_nao_levanta(ambiente: Ambiente) -> None:
    cliente = ambiente.cliente(LiveBoard(), porta_sem_ninguem())
    cliente.shutdown_bridge()


def test_stop_encerra_a_thread_solta_a_conexao_e_pode_repetir(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    cliente.stop()
    esperar(lambda: ponte.conexoes() == 0)
    cliente.stop()
    time.sleep(3 * RECONEXAO_S)
    assert ponte.total_aceitas == 1  # parado não reconecta


def test_start_duas_vezes_nao_abre_duas_conexoes(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    cliente.start()
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    time.sleep(3 * RECONEXAO_S)
    assert ponte.total_aceitas == 1


def test_bridge_responds_com_pong(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte()
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    assert cliente.bridge_responds()
    assert Ping() in ponte.recebidas()


def test_bridge_responds_ignora_o_que_vem_antes_do_pong(ambiente: Ambiente) -> None:
    ponte = ambiente.ponte(responde_ping=False)
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)

    def responder() -> None:
        esperar(lambda: ponte.conexoes() == 1)
        ponte.enviar(Status("conectado", None, 3), b"lixo\n", Pong())

    thread = threading.Thread(target=responder, daemon=True)
    thread.start()
    assert cliente.bridge_responds(2.0)
    thread.join(timeout=5)


def test_bridge_responds_sem_ninguem_ouvindo_e_falso(ambiente: Ambiente) -> None:
    cliente = ambiente.cliente(LiveBoard(), porta_sem_ninguem())
    assert not cliente.bridge_responds()


def test_bridge_responds_com_porta_aberta_mas_sem_pong_e_falso_no_prazo(
    ambiente: Ambiente,
) -> None:
    ponte = ambiente.ponte(responde_ping=False)  # outro programa na 8766, mudo
    cliente = ambiente.cliente(LiveBoard(), ponte.porta)
    inicio = time.monotonic()
    assert not cliente.bridge_responds(0.2)
    assert time.monotonic() - inicio < 1.5


def test_bridge_responds_com_conexao_fechada_pelo_outro_lado_e_falso() -> None:
    escuta = socket.create_server(("127.0.0.1", 0))
    try:
        porta = int(escuta.getsockname()[1])

        def aceitar_e_fechar() -> None:
            conexao, _ = escuta.accept()
            conexao.close()

        thread = threading.Thread(target=aceitar_e_fechar, daemon=True)
        thread.start()
        assert not TrydBridgeClient(LiveBoard(), "127.0.0.1", porta).bridge_responds(2.0)
        thread.join(timeout=5)
    finally:
        escuta.close()

"""Ponte e servidor TCP — sessão RTD falsa em memória, relógio injetado, porta efêmera."""

import logging
import socket
import struct
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from options_ponte.protocolo import (
    Assinar,
    Cancelar,
    Encerrar,
    Mensagem,
    Ping,
    Pong,
    Status,
    Valor,
    codificar,
    decodificar,
)
from options_ponte.servidor import Ponte, ServidorTcp

AGORA = "2026-10-28T12:03:00-03:00"
PETR4_ULT = ("PETR4", "ULT")
PETR4_OCP = ("PETR4", "OCP")
VALE3_ULT = ("VALE3", "ULT")


class SessaoFalsa:
    """``SessaoRtd`` em memória: guarda as chamadas; o teste controla avisos, valores e vida."""

    def __init__(self) -> None:
        self.iniciais: dict[tuple[str, str], object] = {}
        self.conectados: list[tuple[int, tuple[str, str]]] = []
        self.desconectados: list[int] = []
        self.pendentes: list[tuple[int, object]] = []
        self.n_avisos = 0
        self.esta_vivo = True
        self.chamadas_vivo = 0
        self.chamadas_atualizar = 0
        self.encerramentos = 0
        self.falha_na_conexao: int | None = None  # a N-ésima chamada de conectar levanta
        self.erro_ao_atualizar: Exception | None = None
        self.erro_ao_desconectar: Exception | None = None
        self.erro_no_heartbeat: Exception | None = None
        self.threads: set[int] = set()
        self._trava = threading.Lock()

    def avisar(self, *mudancas: tuple[int, object]) -> None:
        with self._trava:
            self.pendentes.extend(mudancas)
            self.n_avisos += 1

    def conectar(self, id_: int, strings: tuple[str, str]) -> object:
        self.threads.add(threading.get_ident())
        if self.falha_na_conexao == len(self.conectados) + 1:
            raise RuntimeError("ConnectData falhou")
        self.conectados.append((id_, strings))
        return self.iniciais.get(strings, 38.42)

    def desconectar(self, id_: int) -> None:
        self.threads.add(threading.get_ident())
        if self.erro_ao_desconectar is not None:
            raise self.erro_ao_desconectar
        self.desconectados.append(id_)

    def atualizar(self) -> list[tuple[int, object]]:
        self.threads.add(threading.get_ident())
        self.chamadas_atualizar += 1
        if self.erro_ao_atualizar is not None:
            raise self.erro_ao_atualizar
        with self._trava:
            mudancas, self.pendentes = self.pendentes, []
        return mudancas

    def vivo(self) -> bool:
        self.threads.add(threading.get_ident())
        self.chamadas_vivo += 1
        if self.erro_no_heartbeat is not None:
            raise self.erro_no_heartbeat
        return self.esta_vivo

    def avisos(self) -> int:
        return self.n_avisos

    def encerrar(self) -> None:
        self.threads.add(threading.get_ident())
        self.encerramentos += 1


class RelogioFalso:
    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora


def _ponte(limite: int = 10) -> tuple[Ponte, SessaoFalsa, RelogioFalso]:
    sessao = SessaoFalsa()
    relogio = RelogioFalso()
    return Ponte(sessao, relogio, lambda: AGORA, limite), sessao, relogio


def _valores(mensagens: list[Mensagem]) -> list[Valor]:
    return [m for m in mensagens if isinstance(m, Valor)]


def _status(mensagens: list[Mensagem]) -> list[Status]:
    return [m for m in mensagens if isinstance(m, Status)]


# --------------------------------------------------------------------------- Ponte.tratar


def test_assinar_conecta_com_o_topico_rtd_e_emite_o_valor_inicial_como_float() -> None:
    ponte, sessao, _ = _ponte()
    mensagens = ponte.tratar(Assinar((PETR4_ULT,)))
    assert mensagens == [Valor("PETR4", "ULT", "float", 38.42, AGORA, inicial=True)]
    assert [strings for _, strings in sessao.conectados] == [("PETR4_B_0", "ULT")]


@pytest.mark.parametrize(
    ("bruto", "tipo_valor", "valor"),
    [
        (1250, "int", 1250),
        ("12:02:31", "str", "12:02:31"),
        (None, "none", None),
        (True, "outro", "True"),
        (b"x", "outro", "b'x'"),
    ],
)
def test_assinar_classifica_o_tipo_do_valor_inicial(
    bruto: object, tipo_valor: str, valor: float | int | str | None
) -> None:
    ponte, sessao, _ = _ponte()
    sessao.iniciais[("PETR4_B_0", "NEG")] = bruto
    assert ponte.tratar(Assinar((("PETR4", "NEG"),))) == [
        Valor("PETR4", "NEG", tipo_valor, valor, AGORA, inicial=True)
    ]


def test_assinar_duas_vezes_nao_reconecta_e_devolve_o_ultimo_valor() -> None:
    ponte, sessao, _ = _ponte()
    inicial = ponte.tratar(Assinar((PETR4_ULT,)))
    assert ponte.tratar(Assinar((PETR4_ULT,))) == inicial
    assert len(sessao.conectados) == 1


def test_assinar_de_novo_devolve_o_ultimo_valor_atualizado_com_o_carimbo_original() -> None:
    sessao = SessaoFalsa()
    relogio = RelogioFalso()
    carimbo = ["2026-10-28T12:00:00-03:00"]
    ponte = Ponte(sessao, relogio, lambda: carimbo[0], 10)
    ponte.tratar(Assinar((PETR4_ULT,)))
    carimbo[0] = "2026-10-28T12:00:05-03:00"
    sessao.avisar((sessao.conectados[0][0], 38.5))
    relogio.agora = 0.1
    ponte.ciclo()
    carimbo[0] = "2026-10-28T12:09:00-03:00"  # a nova assinatura não reescreve o instante
    assert ponte.tratar(Assinar((PETR4_ULT,))) == [
        Valor("PETR4", "ULT", "float", 38.5, "2026-10-28T12:00:05-03:00")  # não inicial
    ]
    assert len(sessao.conectados) == 1


def test_valor_do_conectar_sai_inicial_e_o_reemitido_sem_atualizar_continua_inicial() -> None:
    ponte, sessao, _ = _ponte()
    sessao.iniciais[("PETR4_B_0", "ULT")] = 0.0  # o zero do RTD antes de o Tryd carregar
    primeiro = _valores(ponte.tratar(Assinar((PETR4_ULT,))))
    assert primeiro == [Valor("PETR4", "ULT", "float", 0.0, AGORA, inicial=True)]
    assert _valores(ponte.tratar(Assinar((PETR4_ULT,)))) == primeiro  # ninguém atualizou


def test_depois_de_atualizar_o_reemitido_deixa_de_ser_inicial() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.avisar((sessao.conectados[0][0], 38.5))
    relogio.agora = 0.1
    chegou = _valores(ponte.ciclo())
    assert chegou == [Valor("PETR4", "ULT", "float", 38.5, AGORA, inicial=False)]  # do atualizar
    assert _valores(ponte.tratar(Assinar((PETR4_ULT,)))) == chegou  # a reassinatura repete isso


def test_a_atualizacao_de_um_topico_nao_tira_o_inicial_dos_outros() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP)))
    ids = {strings: id_ for id_, strings in sessao.conectados}
    sessao.avisar((ids[("PETR4_B_0", "ULT")], 38.5))
    relogio.agora = 0.1
    ponte.ciclo()
    reemitidos = {
        (v.campo, v.inicial) for v in _valores(ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP))))
    }
    assert reemitidos == {("ULT", False), ("OCP", True)}


def test_repeticao_no_mesmo_lote_de_topico_ja_assinado_devolve_o_valor_uma_vez() -> None:
    ponte, sessao, _ = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    assert len(ponte.tratar(Assinar((PETR4_ULT, PETR4_ULT)))) == 1
    assert len(sessao.conectados) == 1


def test_cancelar_descarta_o_valor_guardado_e_assinar_de_novo_reconecta() -> None:
    ponte, sessao, _ = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    ponte.tratar(Cancelar((PETR4_ULT,)))
    assert PETR4_ULT not in ponte._ultimos  # sem isso o valor ficaria guardado para sempre
    sessao.iniciais[("PETR4_B_0", "ULT")] = 39.0  # valor novo no servidor
    assert ponte.tratar(Assinar((PETR4_ULT,))) == [
        Valor("PETR4", "ULT", "float", 39.0, AGORA, inicial=True)  # conectou de novo: inicial
    ]
    assert len(sessao.conectados) == 2


def test_topico_assinado_sem_valor_guardado_nao_emite_nada() -> None:
    ponte, sessao, _ = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    ponte._ultimos.clear()  # estado que a ponte não produz sozinha; só prova o ramo defensivo
    assert ponte.tratar(Assinar((PETR4_ULT,))) == []
    assert len(sessao.conectados) == 1


def test_assinar_lote_misto_conecta_so_o_que_e_novo() -> None:
    ponte, sessao, _ = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    mensagens = ponte.tratar(Assinar((PETR4_ULT, VALE3_ULT)))
    # o já assinado volta do que a ponte guardou; só o novo passa pelo servidor
    assert [(m.ticker, m.campo) for m in _valores(mensagens)] == [PETR4_ULT, VALE3_ULT]
    assert [strings for _, strings in sessao.conectados] == [
        ("PETR4_B_0", "ULT"),
        ("VALE3_B_0", "ULT"),
    ]


def test_lote_acima_do_limite_devolve_status_e_nao_conecta_nada() -> None:
    ponte, sessao, _ = _ponte(limite=2)
    mensagens = ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP, VALE3_ULT)))
    assert len(mensagens) == 1
    assert isinstance(mensagens[0], Status)
    assert mensagens[0].motivo is not None
    assert "limite de tópicos" in mensagens[0].motivo
    assert mensagens[0].topicos == 0
    assert sessao.conectados == []
    # a recusa não deixou a ponte travada: um lote que cabe passa
    assert len(_valores(ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP))))) == 2


def test_cancelar_desconecta_pelo_id_e_ignora_topico_nao_assinado() -> None:
    ponte, sessao, _ = _ponte()
    ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP)))
    id_ocp = sessao.conectados[1][0]
    assert ponte.tratar(Cancelar((PETR4_OCP, VALE3_ULT))) == []
    assert sessao.desconectados == [id_ocp]


def test_falha_do_servidor_ao_desconectar_vira_status_perdido() -> None:
    ponte, sessao, _ = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.erro_ao_desconectar = RuntimeError("DisconnectData falhou")
    (status,) = ponte.tratar(Cancelar((PETR4_ULT,)))
    assert isinstance(status, Status)
    assert (status.tryd, status.topicos) == ("perdido", 0)
    assert status.motivo is not None
    assert "DisconnectData falhou" in status.motivo


def test_ping_devolve_pong() -> None:
    ponte, _, _ = _ponte()
    assert ponte.tratar(Ping()) == [Pong()]


@pytest.mark.parametrize(
    "mensagem",
    [Valor("PETR4", "ULT", "float", 1.0, AGORA), Status("conectado", None, 0), Pong()],
)
def test_mensagem_que_nao_e_comando_e_ignorada(mensagem: Mensagem) -> None:
    ponte, sessao, _ = _ponte()
    assert ponte.tratar(mensagem) == []
    assert sessao.conectados == []


def test_encerrar_marca_a_ponte_e_encerrar_a_sessao_so_uma_vez() -> None:
    ponte, sessao, _ = _ponte()
    assert not ponte.encerrando
    assert ponte.tratar(Encerrar()) == []
    assert ponte.encerrando
    ponte.encerrar()
    ponte.encerrar()
    assert sessao.encerramentos == 1


def test_falha_do_servidor_ao_conectar_vira_status_perdido_e_desfaz_o_que_nao_conectou() -> None:
    ponte, sessao, _ = _ponte()
    sessao.falha_na_conexao = 2
    mensagens = ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP, VALE3_ULT)))
    assert _valores(mensagens) == [Valor("PETR4", "ULT", "float", 38.42, AGORA, inicial=True)]
    (status,) = _status(mensagens)
    assert status.tryd == "perdido"
    assert status.motivo is not None
    assert "ConnectData falhou" in status.motivo
    assert status.topicos == 1  # só o que conectou ficou registrado
    # o que não conectou pode ser pedido de novo; o que conectou volta do guardado
    sessao.falha_na_conexao = None
    refeito = _valores(ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP, VALE3_ULT))))
    assert [(m.ticker, m.campo) for m in refeito] == [PETR4_ULT, PETR4_OCP, VALE3_ULT]
    assert len(sessao.conectados) == 3


# --------------------------------------------------------------------------- Ponte.ciclo


def test_ciclo_sem_aviso_nao_chama_atualizar() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    relogio.agora = 0.1
    assert ponte.ciclo() == []
    assert sessao.chamadas_atualizar == 0


def test_ciclo_depois_de_um_aviso_emite_os_valores_mudados() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP)))
    id_ult, id_ocp = sessao.conectados[0][0], sessao.conectados[1][0]
    sessao.avisar((id_ocp, 38.4), (id_ult, 38.5))
    relogio.agora = 0.1
    assert ponte.ciclo() == [
        Valor("PETR4", "OCP", "float", 38.4, AGORA),
        Valor("PETR4", "ULT", "float", 38.5, AGORA),
    ]
    # o mesmo aviso não é processado duas vezes
    relogio.agora = 0.2
    assert ponte.ciclo() == []
    assert sessao.chamadas_atualizar == 1


def test_ciclo_ignora_id_que_nao_esta_mais_assinado() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.avisar((999, 1.0))
    relogio.agora = 0.1
    assert ponte.ciclo() == []


def test_status_a_cada_dois_segundos() -> None:
    ponte, _, relogio = _ponte()
    esperado = Status("iniciando", None, 0)
    for agora, mensagens in [(0.0, []), (1.9, []), (2.0, [esperado]), (3.9, []), (4.0, [esperado])]:
        relogio.agora = agora
        assert ponte.ciclo() == mensagens, agora


def test_status_vira_conectado_quando_o_servidor_responde_ao_heartbeat() -> None:
    ponte, _, relogio = _ponte()
    relogio.agora = 5.0
    assert ponte.ciclo() == [Status("conectado", None, 0)]


def test_assinatura_bem_sucedida_marca_conectado_e_conta_os_topicos() -> None:
    ponte, _, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT, PETR4_OCP)))
    relogio.agora = 2.0
    assert ponte.ciclo() == [Status("conectado", None, 2)]


def test_cinco_segundos_sem_aviso_chama_vivo_e_falso_emite_status_perdido() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.esta_vivo = False
    relogio.agora = 4.9
    ponte.ciclo()
    assert sessao.chamadas_vivo == 0
    relogio.agora = 5.0
    mensagens = ponte.ciclo()
    assert sessao.chamadas_vivo == 1
    (status,) = mensagens  # o perdido substitui o status periódico, sem duplicar
    assert isinstance(status, Status)
    assert (status.tryd, status.topicos) == ("perdido", 1)
    assert status.motivo is not None
    assert "Heartbeat" in status.motivo


def test_perdido_repete_o_motivo_no_status_periodico_e_reverifica_a_cada_cinco_segundos() -> None:
    ponte, sessao, relogio = _ponte()
    sessao.esta_vivo = False
    relogio.agora = 5.0
    (perdido,) = _status(ponte.ciclo())
    relogio.agora = 7.0
    assert ponte.ciclo() == [perdido]
    relogio.agora = 9.9
    ponte.ciclo()
    assert sessao.chamadas_vivo == 1
    relogio.agora = 10.0
    ponte.ciclo()
    assert sessao.chamadas_vivo == 2


def test_falha_no_heartbeat_vira_status_perdido_com_o_motivo() -> None:
    ponte, sessao, relogio = _ponte()
    sessao.erro_no_heartbeat = RuntimeError("RPC indisponível")
    relogio.agora = 5.0
    (status,) = ponte.ciclo()
    assert isinstance(status, Status)
    assert status.tryd == "perdido"
    assert status.motivo is not None
    assert "RPC indisponível" in status.motivo


def test_servidor_que_volta_a_responder_ao_heartbeat_deixa_de_estar_perdido() -> None:
    ponte, sessao, relogio = _ponte()
    sessao.esta_vivo = False
    relogio.agora = 5.0
    ponte.ciclo()
    sessao.esta_vivo = True
    relogio.agora = 10.0
    assert ponte.ciclo() == [Status("conectado", None, 0)]


def test_aviso_zera_a_contagem_de_silencio_do_heartbeat() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.avisar((sessao.conectados[0][0], 38.5))
    relogio.agora = 4.0
    ponte.ciclo()
    relogio.agora = 8.9
    ponte.ciclo()
    assert sessao.chamadas_vivo == 0
    relogio.agora = 9.0
    ponte.ciclo()
    assert sessao.chamadas_vivo == 1


def test_falha_ao_atualizar_vira_status_perdido_sem_derrubar_o_ciclo() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.erro_ao_atualizar = RuntimeError("RPC indisponível")
    sessao.avisar((sessao.conectados[0][0], 1.0))
    relogio.agora = 0.1
    (status,) = ponte.ciclo()
    assert isinstance(status, Status)
    assert (status.tryd, status.topicos) == ("perdido", 1)
    assert status.motivo is not None
    assert "RPC indisponível" in status.motivo
    relogio.agora = 0.2
    assert ponte.ciclo() == []  # sem repetir o status a cada volta
    assert sessao.chamadas_atualizar == 1  # e sem insistir antes de 1 s
    relogio.agora = 1.2
    assert ponte.ciclo() == []  # passado o espaçamento, tenta de novo (e segue calada)
    assert sessao.chamadas_atualizar == 2


def test_falha_ao_atualizar_nao_consome_o_aviso_e_o_proximo_ciclo_entrega_sem_aviso_novo() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.erro_ao_atualizar = RuntimeError("RPC indisponível")
    sessao.avisar((sessao.conectados[0][0], 38.5))
    relogio.agora = 0.1
    (perdido,) = ponte.ciclo()
    assert isinstance(perdido, Status)
    assert perdido.tryd == "perdido"
    sessao.erro_ao_atualizar = None  # o servidor voltou; nenhum UpdateNotify novo
    relogio.agora = 0.2
    assert ponte.ciclo() == []  # ainda dentro do espaçamento de 1 s
    relogio.agora = 1.2
    assert ponte.ciclo() == [Valor("PETR4", "ULT", "float", 38.5, AGORA)]
    assert sessao.n_avisos == 1
    relogio.agora = 2.1  # 2 s depois do status perdido de 0,1 s
    assert ponte.ciclo() == [Status("conectado", None, 1)]


def test_atualizar_que_segue_falhando_tenta_a_cada_segundo_sem_repetir_o_status() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    sessao.erro_ao_atualizar = RuntimeError("RPC indisponível")
    sessao.avisar((sessao.conectados[0][0], 38.5))
    relogio.agora = 0.1
    assert len(_status(ponte.ciclo())) == 1
    for passo in range(2, 11):  # 0,2 s a 1,0 s: dentro do espaçamento, não chama o servidor
        relogio.agora = passo * 0.1
        assert ponte.ciclo() == []
    assert sessao.chamadas_atualizar == 1
    relogio.agora = 1.2
    assert ponte.ciclo() == []
    assert sessao.chamadas_atualizar == 2
    relogio.agora = 2.0  # 0,8 s depois da segunda tentativa
    assert ponte.ciclo() == []
    assert sessao.chamadas_atualizar == 2
    relogio.agora = 2.3  # o status periódico segue dizendo perdido, com o motivo
    (periodico,) = ponte.ciclo()
    assert isinstance(periodico, Status)
    assert periodico.tryd == "perdido"
    assert periodico.motivo is not None
    assert "RPC indisponível" in periodico.motivo
    assert sessao.chamadas_atualizar == 3


def test_espacamento_so_vale_depois_de_falha_e_acaba_quando_o_atualizar_volta() -> None:
    ponte, sessao, relogio = _ponte()
    ponte.tratar(Assinar((PETR4_ULT,)))
    id_ = sessao.conectados[0][0]
    sessao.erro_ao_atualizar = RuntimeError("RPC indisponível")
    sessao.avisar((id_, 38.5))
    relogio.agora = 0.1
    ponte.ciclo()
    sessao.erro_ao_atualizar = None
    relogio.agora = 1.2
    assert ponte.ciclo() == [Valor("PETR4", "ULT", "float", 38.5, AGORA)]
    sessao.avisar((id_, 38.6))
    relogio.agora = 1.25  # aviso novo logo depois do sucesso: busca na hora
    assert ponte.ciclo() == [Valor("PETR4", "ULT", "float", 38.6, AGORA)]


# --------------------------------------------------------------------------- ServidorTcp


class Cliente:
    """Cliente socket de teste: envia mensagens e lê linhas, com tempo máximo de espera."""

    def __init__(self, endereco: tuple[str, int]) -> None:
        self.sock = socket.create_connection(endereco, timeout=5)
        self._leitor = self.sock.makefile("rb")

    def enviar(self, *mensagens: Mensagem) -> None:
        self.sock.sendall(b"".join(codificar(m) for m in mensagens))

    def receber(self) -> Mensagem:
        linha = self._leitor.readline()
        assert linha, "a ponte fechou a conexão"
        return decodificar(linha)

    def receber_ate[T: Mensagem](self, tipo: type[T]) -> T:
        while True:
            mensagem = self.receber()
            if isinstance(mensagem, tipo):
                return mensagem

    def sincronizar(self) -> None:
        """Ping/Pong: ao voltar, a ponte já registrou este cliente e atendeu seus comandos."""
        self.enviar(Ping())
        self.receber_ate(Pong)

    def fim_da_conexao(self) -> bool:
        return self._leitor.readline() == b""

    def fechar(self) -> None:
        self._leitor.close()
        self.sock.close()


class SocketQuebrado(socket.socket):
    """Cliente já morto que a ponte ainda não percebeu: toda escrita falha."""

    def sendall(self, *args: object) -> None:
        raise BrokenPipeError("cliente caiu")


class PonteNoAr:
    """Ponte + ServidorTcp rodando numa thread própria, que faz o papel da thread do COM."""

    def __init__(self) -> None:
        self.sessao = SessaoFalsa()
        self.relogio = RelogioFalso()
        ponte = Ponte(self.sessao, self.relogio, lambda: AGORA, limite=10)
        self.servidor = ServidorTcp(ponte, 0, self._bombear)
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self._laco, daemon=True)
        self.thread_do_laco = 0
        self.threads_de_bombeamento: set[int] = set()
        self.erro: BaseException | None = None
        self.clientes: list[Cliente] = []

    def _bombear(self, segundos: float) -> None:
        self.threads_de_bombeamento.add(threading.get_ident())
        time.sleep(min(segundos, 0.002))

    def _laco(self) -> None:
        self.thread_do_laco = threading.get_ident()
        try:
            self.servidor.rodar(self.parar)
        except BaseException as erro:  # repassa ao teste, que falha no encerramento
            self.erro = erro

    def cliente(self) -> Cliente:
        cliente = Cliente(self.servidor.endereco)
        self.clientes.append(cliente)
        return cliente

    def esperar_o_fim(self) -> None:
        self.thread.join(timeout=5)
        assert not self.thread.is_alive(), "rodar não voltou"


@pytest.fixture
def no_ar() -> Iterator[PonteNoAr]:
    ponte = PonteNoAr()
    ponte.thread.start()
    yield ponte
    ponte.parar.set()
    ponte.thread.join(timeout=5)
    for cliente in ponte.clientes:
        cliente.fechar()
    assert not ponte.thread.is_alive(), "rodar não voltou"
    assert ponte.erro is None


def test_endereco_e_local_e_a_porta_efemera_e_descoberta(no_ar: PonteNoAr) -> None:
    host, porta = no_ar.servidor.endereco
    assert host == "127.0.0.1"
    assert porta > 0


def test_ponta_a_ponta_assinar_devolve_uma_linha_valor(no_ar: PonteNoAr) -> None:
    cliente = no_ar.cliente()
    cliente.enviar(Assinar((PETR4_ULT,)))
    valor = cliente.receber_ate(Valor)
    assert (valor.ticker, valor.campo, valor.tipo_valor, valor.valor) == (
        "PETR4",
        "ULT",
        "float",
        38.42,
    )
    assert valor.inicial  # o que o ConnectData devolveu, antes de qualquer atualização


def test_encerrar_pela_rede_faz_rodar_voltar_e_fecha_a_sessao(no_ar: PonteNoAr) -> None:
    cliente = no_ar.cliente()
    cliente.sincronizar()
    cliente.enviar(Encerrar())
    no_ar.esperar_o_fim()
    assert no_ar.sessao.encerramentos == 1
    assert cliente.fim_da_conexao()


def test_parar_faz_rodar_voltar_e_fecha_a_sessao(no_ar: PonteNoAr) -> None:
    cliente = no_ar.cliente()
    cliente.sincronizar()
    no_ar.parar.set()
    no_ar.esperar_o_fim()
    assert no_ar.sessao.encerramentos == 1
    assert cliente.fim_da_conexao()


def test_valores_iniciais_e_mudancas_vao_para_todos_os_clientes(no_ar: PonteNoAr) -> None:
    a, b = no_ar.cliente(), no_ar.cliente()
    a.sincronizar()
    b.sincronizar()
    a.enviar(Assinar((PETR4_ULT,)))
    inicial = Valor("PETR4", "ULT", "float", 38.42, AGORA, inicial=True)
    assert a.receber_ate(Valor) == b.receber_ate(Valor) == inicial
    no_ar.sessao.avisar((no_ar.sessao.conectados[0][0], 38.5))
    esperado = Valor("PETR4", "ULT", "float", 38.5, AGORA)
    assert a.receber_ate(Valor) == b.receber_ate(Valor) == esperado


def test_cliente_que_assina_depois_recebe_o_ultimo_valor_sem_mudanca_no_servidor(
    no_ar: PonteNoAr,
) -> None:
    a = no_ar.cliente()
    a.enviar(Assinar((PETR4_ULT,)))
    a.receber_ate(Valor)
    no_ar.sessao.avisar((no_ar.sessao.conectados[0][0], 38.5))
    esperado = Valor("PETR4", "ULT", "float", 38.5, AGORA)
    assert a.receber_ate(Valor) == esperado
    b = no_ar.cliente()  # chega depois e pede o mesmo tópico; nada muda no servidor RTD
    b.enviar(Assinar((PETR4_ULT,)))
    assert b.receber_ate(Valor) == esperado
    assert len(no_ar.sessao.conectados) == 1


def test_status_periodico_vai_para_todos_os_clientes(no_ar: PonteNoAr) -> None:
    a, b = no_ar.cliente(), no_ar.cliente()
    a.sincronizar()
    b.sincronizar()
    no_ar.relogio.agora = 2.0
    assert a.receber_ate(Status) == b.receber_ate(Status) == Status("iniciando", None, 0)


@pytest.mark.parametrize("derrubar_com_rst", [False, True], ids=["fechou", "reset"])
def test_cliente_que_cai_nao_derruba_a_ponte(no_ar: PonteNoAr, derrubar_com_rst: bool) -> None:
    a, b = no_ar.cliente(), no_ar.cliente()
    a.sincronizar()
    b.sincronizar()
    if derrubar_com_rst:
        a.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    a.fechar()
    for rodada in range(1, 6):  # várias difusões para cima do socket morto
        no_ar.relogio.agora = 2.0 * rodada
        b.receber_ate(Status)
    assert no_ar.thread.is_alive()
    b.sincronizar()
    b.enviar(Assinar((PETR4_ULT,)))
    assert b.receber_ate(Valor).ticker == "PETR4"


def test_falha_ao_escrever_para_um_cliente_o_tira_da_difusao_sem_afetar_os_outros(
    no_ar: PonteNoAr,
) -> None:
    b = no_ar.cliente()
    b.sincronizar()
    quebrado = SocketQuebrado()
    with no_ar.servidor._trava:
        no_ar.servidor._clientes.append(quebrado)
    no_ar.relogio.agora = 2.0
    b.receber_ate(Status)
    b.sincronizar()  # o Pong só sai depois da difusão que passou pelo cliente quebrado
    with no_ar.servidor._trava:
        assert quebrado not in no_ar.servidor._clientes
    assert no_ar.thread.is_alive()
    quebrado.close()


def test_leitura_sem_dados_por_um_tempo_nao_derruba_o_cliente(
    no_ar: PonteNoAr, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("options_ponte.servidor._ESPERA_CLIENTE_S", 0.02)
    cliente = no_ar.cliente()
    time.sleep(0.1)  # vários estouros de tempo da leitura, sem dado nenhum
    cliente.sincronizar()


def test_conexao_abortada_no_aceite_nao_faz_a_ponte_parar_de_aceitar(
    no_ar: PonteNoAr, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = socket.socket.accept
    falhas: list[int] = []

    def aceitar_com_uma_falha(self: socket.socket) -> tuple[socket.socket, Any]:
        if not falhas:
            falhas.append(1)
            raise ConnectionAbortedError("o cliente desistiu antes do accept")
        return original(self)

    monkeypatch.setattr(socket.socket, "accept", aceitar_com_uma_falha)
    limite = time.monotonic() + 5
    while not falhas and time.monotonic() < limite:
        time.sleep(0.005)  # a thread de aceite volta ao accept a cada 50 ms
    assert falhas == [1]
    no_ar.cliente().sincronizar()  # só atende se a thread de aceite sobreviveu à falha


def test_valor_com_texto_nao_codificavel_chega_como_outro_e_o_laco_segue(
    no_ar: PonteNoAr,
) -> None:
    no_ar.sessao.iniciais[("PETR4_B_0", "HOR")] = "x\ud800y"
    cliente = no_ar.cliente()
    cliente.enviar(Assinar((("PETR4", "HOR"),)))
    valor = cliente.receber_ate(Valor)
    assert (valor.tipo_valor, valor.valor) == ("outro", repr("x\ud800y"))
    no_ar.sessao.avisar((no_ar.sessao.conectados[0][0], "y\udfffz"))
    assert cliente.receber_ate(Valor).tipo_valor == "outro"
    cliente.sincronizar()
    assert no_ar.thread.is_alive()


def test_mensagem_que_nao_da_para_codificar_e_descartada_e_as_outras_chegam(
    no_ar: PonteNoAr, caplog: pytest.LogCaptureFixture
) -> None:
    cliente = no_ar.cliente()
    # "\ud800" escapado no JSON vira um surrogate solto no ticker, que não vira UTF-8
    cliente.sock.sendall(b'{"tipo":"assinar","topicos":[["A\\ud800","ULT"],["PETR4","ULT"]]}\n')
    assert cliente.receber_ate(Valor).ticker == "PETR4"
    cliente.sincronizar()
    assert no_ar.thread.is_alive()
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("descartada" in r.getMessage() for r in avisos)


def test_linha_invalida_e_ignorada_e_a_conexao_segue(no_ar: PonteNoAr) -> None:
    cliente = no_ar.cliente()
    cliente.sock.sendall(b"\n  \n{lixo\n" + b'{"tipo":"desconhecido"}\n')
    cliente.sincronizar()


def test_comandos_em_pedacos_e_colados_na_mesma_escrita(no_ar: PonteNoAr) -> None:
    cliente = no_ar.cliente()
    linha = codificar(Ping())
    cliente.sock.sendall(linha[:5])
    time.sleep(0.05)  # deixa a ponte ler o pedaço antes do resto
    cliente.sock.sendall(linha[5:] + linha)
    assert cliente.receber() == Pong()
    assert cliente.receber() == Pong()


def test_so_a_thread_do_laco_toca_a_sessao_e_bombeia(no_ar: PonteNoAr) -> None:
    cliente = no_ar.cliente()
    cliente.enviar(Assinar((PETR4_ULT,)))
    cliente.receber_ate(Valor)
    no_ar.sessao.avisar((no_ar.sessao.conectados[0][0], 38.5))
    cliente.receber_ate(Valor)
    cliente.enviar(Cancelar((PETR4_ULT,)))
    cliente.sincronizar()
    no_ar.parar.set()
    no_ar.esperar_o_fim()
    assert no_ar.sessao.desconectados
    assert no_ar.sessao.threads == {no_ar.thread_do_laco}
    assert no_ar.threads_de_bombeamento == {no_ar.thread_do_laco}

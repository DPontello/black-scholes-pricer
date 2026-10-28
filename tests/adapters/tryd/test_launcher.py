"""Lançador da ponte — comando por sistema, adoção de ponte viva, encerramento e relançamento.

Nada aqui lança Wine ou distrobox: o executor de processos é injetado (``Executor``) e a ponte
é um servidor TCP falso em porta 0 (``PonteFalsa``). O tempo vem de um relógio monotônico falso.
"""

import re
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest

from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.client import TrydBridgeClient
from options_engine.adapters.outbound.tryd.launcher import (
    BridgeProcess,
    bridge_kill_command,
    default_bridge_command,
    spawn_process,
)
from options_ponte.protocolo import Encerrar, Ping
from tests.adapters.tryd._ponte_falsa import PonteFalsa, esperar, porta_sem_ninguem

SRC = Path("/repo/src")
HOME = Path("/home/hugo")
COMANDO = ("ponte", "servir", "--porta", "9")
CWD = Path("/repo/src")
KILL_LINUX = ("distrobox", "enter", "tryd", "--", "pkill", "-f", "[o]ptions_ponte servir")


# --------------------------------------------------------------------------- comandos puros


def test_comando_da_ponte_no_linux() -> None:
    comando, cwd = default_bridge_command("Linux", SRC, HOME, 8766)
    assert comando == (
        "distrobox",
        "enter",
        "tryd",
        "--",
        "env",
        "WINEPREFIX=/home/hugo/.local/share/wineprefixes/tryd",
        "WINEDEBUG=-all",
        "wine",
        "C:\\Python312\\python.exe",
        "-m",
        "options_ponte",
        "servir",
        "--porta",
        "8766",
    )
    assert cwd == SRC


def test_comando_da_ponte_no_windows() -> None:
    comando, cwd = default_bridge_command("Windows", SRC, HOME, 9000)
    assert comando == ("python", "-m", "options_ponte", "servir", "--porta", "9000")
    assert cwd == SRC


def test_comando_para_matar_a_ponte_que_sobrou_so_existe_no_linux() -> None:
    assert bridge_kill_command("Linux") == KILL_LINUX
    assert bridge_kill_command("Windows") is None


def test_o_padrao_do_pkill_nao_casa_com_a_propria_linha_de_comando() -> None:
    """``pkill -f`` olha a linha de comando de todo processo, inclusive a do próprio pkill."""
    padrao = KILL_LINUX[-1]
    assert re.search(padrao, "C:\\Python312\\python.exe -m options_ponte servir --porta 8766")
    assert not re.search(padrao, " ".join(KILL_LINUX))


# --------------------------------------------------------------------------- dublês


class ProcessoFalso:
    """O que o ``BridgeProcess`` usa de um ``Popen``: ``poll``, ``wait`` e ``terminate``."""

    def __init__(self, comando: Sequence[str]) -> None:
        self.comando = tuple(comando)
        self.returncode: int | None = None
        self.terminado = False
        self.esperas: list[float | None] = []
        self.ao_esperar: Callable[[ProcessoFalso], None] | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        self.esperas.append(timeout)
        if self.ao_esperar is not None:
            self.ao_esperar(self)
        if self.returncode is None:
            raise subprocess.TimeoutExpired(self.comando, timeout or 0.0)
        return self.returncode

    def terminate(self) -> None:
        self.terminado = True


class Executor:
    """Fábrica injetada no lugar do ``Popen``: guarda os pedidos e devolve processos falsos."""

    def __init__(self) -> None:
        self.pedidos: list[tuple[tuple[str, ...], Path]] = []
        self.processos: list[ProcessoFalso] = []
        self.falha: OSError | None = None

    def __call__(self, comando: Sequence[str], cwd: Path) -> ProcessoFalso:
        self.pedidos.append((tuple(comando), cwd))
        if self.falha is not None:
            raise self.falha
        processo = ProcessoFalso(comando)
        self.processos.append(processo)
        return processo

    @property
    def lancados(self) -> list[tuple[str, ...]]:
        return [comando for comando, _ in self.pedidos]


class Relogio:
    def __init__(self) -> None:
        self.agora = 0.0

    def __call__(self) -> float:
        return self.agora


class Cenario:
    """Uma porta de ponte (livre até o teste subir a ponte falsa), o executor e o relógio."""

    def __init__(self) -> None:
        self.porta = porta_sem_ninguem()
        self.pontes: list[PonteFalsa] = []
        self.executor = Executor()
        self.relogio = Relogio()
        self.cliente = TrydBridgeClient(LiveBoard(), "127.0.0.1", self.porta)

    def sobe_ponte(self, **kwargs: bool) -> PonteFalsa:
        ponte = PonteFalsa(self.porta, **kwargs)
        self.pontes.append(ponte)
        return ponte

    def processo(self, sistema: str = "Linux") -> BridgeProcess:
        return BridgeProcess(
            COMANDO,
            CWD,
            self.cliente,
            spawn=self.executor,
            monotonic=self.relogio,
            system=sistema,
        )


@pytest.fixture
def cenario() -> Iterator[Cenario]:
    cenario = Cenario()
    yield cenario
    for ponte in cenario.pontes:
        ponte.fechar()


def _sai_ao_encerrar(ponte: PonteFalsa) -> Callable[[ProcessoFalso], None]:
    """Como a ponte de verdade: recebe ``Encerrar``, solta a porta e só então o processo sai."""

    def gancho(processo: ProcessoFalso) -> None:
        esperar(lambda: Encerrar() in ponte.recebidas())
        esperar(lambda: ponte.fechada)
        processo.returncode = 0

    return gancho


def _so_ve_o_encerrar(ponte: PonteFalsa) -> Callable[[ProcessoFalso], None]:
    """O processo não sai (o ``distrobox enter`` que não leva o wine junto)."""

    def gancho(_processo: ProcessoFalso) -> None:
        esperar(lambda: Encerrar() in ponte.recebidas())

    return gancho


# --------------------------------------------------------------------------- adoção


def test_start_adota_a_ponte_viva_sem_lancar_outra(cenario: Cenario) -> None:
    ponte = cenario.sobe_ponte()
    cenario.processo().start()
    assert cenario.executor.pedidos == []
    assert Ping() in ponte.recebidas()


def test_stop_nao_encerra_a_ponte_que_so_foi_adotada(cenario: Cenario) -> None:
    ponte = cenario.sobe_ponte()
    processo = cenario.processo()
    processo.start()
    processo.stop()
    assert cenario.cliente.bridge_responds()  # o Ping novo vai atrás do Encerrar, se existisse
    assert Encerrar() not in ponte.recebidas()
    assert cenario.executor.pedidos == []  # nem pkill
    assert ponte.conexoes() <= 1


def test_ensure_running_nao_lanca_nada_enquanto_a_ponte_adotada_responde(cenario: Cenario) -> None:
    cenario.sobe_ponte()
    processo = cenario.processo()
    processo.start()
    cenario.relogio.agora = 1000.0
    processo.ensure_running()
    assert cenario.executor.pedidos == []


def test_ensure_running_lanca_o_comando_quando_a_ponte_adotada_para_de_responder(
    cenario: Cenario,
) -> None:
    ponte = cenario.sobe_ponte()
    processo = cenario.processo()
    processo.start()  # adotou: nada lançado
    assert cenario.executor.pedidos == []

    ponte.fechar()  # a ponte adotada para de responder
    processo.ensure_running()  # adotar não conta como tentativa: não espera os 10 s
    assert cenario.executor.pedidos == [(COMANDO, CWD)]

    cenario.executor.processos[0].returncode = 1  # a nossa também morreu
    cenario.relogio.agora = 9.9
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1  # os 10 s contam do lançamento
    cenario.relogio.agora = 10.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 2


def test_stop_encerra_a_ponte_que_o_app_lancou_depois_de_adotar_uma_que_caiu(
    cenario: Cenario,
) -> None:
    ponte = cenario.sobe_ponte()
    processo = cenario.processo()
    processo.start()
    ponte.fechar()
    processo.ensure_running()  # lançou a nossa
    nova = cenario.sobe_ponte(fecha_ao_encerrar=True)  # e ela subiu na porta
    lancado = cenario.executor.processos[0]
    lancado.ao_esperar = _sai_ao_encerrar(nova)
    processo.stop()
    assert Encerrar() in nova.recebidas()
    assert lancado.esperas == [3.0]
    assert not lancado.terminado


def test_ensure_running_nao_relanca_se_a_ponte_adotada_voltou_sozinha(cenario: Cenario) -> None:
    ponte = cenario.sobe_ponte()
    processo = cenario.processo()
    processo.start()
    ponte.fechar()
    cenario.sobe_ponte()  # alguém subiu outra ponte na mesma porta antes do ensure_running
    cenario.relogio.agora = 50.0
    processo.ensure_running()
    assert cenario.executor.pedidos == []


# --------------------------------------------------------------------------- lançamento


def test_start_lanca_o_comando_quando_nao_ha_ponte(cenario: Cenario) -> None:
    cenario.processo().start()
    assert cenario.executor.pedidos == [(COMANDO, CWD)]


def test_start_sem_o_executavel_nao_levanta_e_o_app_segue_sem_ponte(
    cenario: Cenario, caplog: pytest.LogCaptureFixture
) -> None:
    cenario.executor.falha = FileNotFoundError("distrobox")
    cenario.processo().start()  # Tryd fora do ar não derruba a abertura do app
    assert "distrobox" in caplog.text


def test_spawn_process_lanca_um_processo_de_verdade(tmp_path: Path) -> None:
    processo = spawn_process((sys.executable, "-c", "raise SystemExit(7)"), tmp_path)
    assert processo.wait(timeout=30) == 7
    assert processo.poll() == 7


# --------------------------------------------------------------------------- encerramento


def test_stop_manda_encerrar_espera_3_s_e_nao_termina_quem_saiu(cenario: Cenario) -> None:
    processo = cenario.processo()
    processo.start()  # sem ponte: lançou
    ponte = cenario.sobe_ponte(fecha_ao_encerrar=True)  # o processo lançado subiu a ponte
    lancado = cenario.executor.processos[0]
    lancado.ao_esperar = _sai_ao_encerrar(ponte)
    processo.stop()
    assert lancado.esperas == [3.0]
    assert not lancado.terminado
    assert cenario.executor.lancados == [COMANDO]  # a porta calou: nada de pkill


def test_stop_termina_o_processo_que_nao_sai_em_3_s(cenario: Cenario) -> None:
    processo = cenario.processo("Windows")
    processo.start()
    ponte = cenario.sobe_ponte(fecha_ao_encerrar=True)
    lancado = cenario.executor.processos[0]
    lancado.ao_esperar = _so_ve_o_encerrar(ponte)
    processo.stop()
    assert lancado.esperas == [3.0]
    assert lancado.terminado
    assert cenario.executor.lancados == [COMANDO]


def test_stop_no_linux_mata_a_ponte_que_sobrou_quando_a_porta_ainda_responde(
    cenario: Cenario,
) -> None:
    processo = cenario.processo("Linux")
    processo.start()
    ponte = cenario.sobe_ponte()  # ignora o Encerrar: a porta continua respondendo
    lancado = cenario.executor.processos[0]
    lancado.ao_esperar = _so_ve_o_encerrar(ponte)
    processo.stop()
    assert lancado.terminado
    assert cenario.executor.pedidos == [(COMANDO, CWD), (KILL_LINUX, CWD)]
    assert cenario.executor.processos[1].esperas  # esperou o pkill terminar


def test_stop_no_windows_nao_roda_pkill_mesmo_com_a_porta_respondendo(cenario: Cenario) -> None:
    processo = cenario.processo("Windows")
    processo.start()
    ponte = cenario.sobe_ponte()
    cenario.executor.processos[0].ao_esperar = _so_ve_o_encerrar(ponte)
    processo.stop()
    assert cenario.executor.lancados == [COMANDO]


def test_stop_com_o_processo_que_ja_tinha_saido_e_a_porta_livre_nao_faz_mais_nada(
    cenario: Cenario,
) -> None:
    processo = cenario.processo()
    processo.start()
    lancado = cenario.executor.processos[0]
    lancado.returncode = 0
    processo.stop()  # sem ponte para receber o Encerrar: não levanta
    assert not lancado.terminado
    assert cenario.executor.lancados == [COMANDO]


def test_stop_do_pkill_que_trava_termina_o_pkill(cenario: Cenario) -> None:
    processo = cenario.processo("Linux")
    processo.start()
    cenario.sobe_ponte()
    processo.stop()
    pkill = cenario.executor.processos[1]
    assert pkill.terminado  # o fake nunca sai sozinho: wait estourou o prazo


def test_stop_sem_start_e_stop_repetido_nao_fazem_nada(cenario: Cenario) -> None:
    processo = cenario.processo()
    processo.stop()
    processo.start()
    processo.stop()
    processo.stop()
    assert cenario.executor.lancados == [COMANDO]


def test_stop_depois_de_lancamento_que_falhou_nao_levanta(cenario: Cenario) -> None:
    cenario.executor.falha = PermissionError("negado")
    processo = cenario.processo()
    processo.start()
    processo.stop()


# --------------------------------------------------------------------------- relançamento


def test_ensure_running_relanca_com_10_s_entre_tentativas(cenario: Cenario) -> None:
    processo = cenario.processo()
    processo.start()  # t = 0: primeira tentativa
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1  # processo vivo: nada a fazer

    cenario.executor.processos[0].returncode = 1  # a ponte morreu
    cenario.relogio.agora = 9.9
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1  # ainda não passaram 10 s
    cenario.relogio.agora = 10.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 2

    cenario.executor.processos[1].returncode = 1  # morreu de novo, logo
    cenario.relogio.agora = 19.9
    processo.ensure_running()
    assert len(cenario.executor.processos) == 2  # os 10 s contam da última tentativa
    cenario.relogio.agora = 20.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 3
    assert cenario.executor.lancados == [COMANDO, COMANDO, COMANDO]


def test_ensure_running_nao_relanca_com_o_processo_vivo(cenario: Cenario) -> None:
    processo = cenario.processo()
    processo.start()
    cenario.relogio.agora = 500.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1


def test_ensure_running_nao_relanca_se_a_porta_ainda_responde(cenario: Cenario) -> None:
    processo = cenario.processo()
    processo.start()
    cenario.sobe_ponte()  # o wine segue de pé, só o distrobox enter saiu
    cenario.executor.processos[0].returncode = 0
    cenario.relogio.agora = 50.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1


def test_ensure_running_tenta_de_novo_depois_de_um_lancamento_que_falhou(
    cenario: Cenario,
) -> None:
    cenario.executor.falha = FileNotFoundError("distrobox")
    processo = cenario.processo()
    processo.start()
    cenario.relogio.agora = 5.0
    processo.ensure_running()
    assert len(cenario.executor.pedidos) == 1
    cenario.executor.falha = None  # o distrobox apareceu
    cenario.relogio.agora = 10.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1


def test_ensure_running_nao_faz_nada_antes_do_start_nem_depois_do_stop(cenario: Cenario) -> None:
    processo = cenario.processo()
    cenario.relogio.agora = 100.0
    processo.ensure_running()
    assert cenario.executor.pedidos == []

    processo.start()
    processo.stop()
    cenario.executor.processos[0].returncode = 0
    cenario.relogio.agora = 200.0
    processo.ensure_running()
    assert len(cenario.executor.processos) == 1  # parado de propósito: não relança

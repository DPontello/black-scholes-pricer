"""Seletor de pasta do sistema: comando por plataforma, execução e o seletor pronto da montagem."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from options_engine.adapters.inbound.web import folder_picker as modulo
from options_engine.adapters.inbound.web.folder_picker import (
    PICK_TIMEOUT_S,
    PICK_TITLE,
    WINDOWS_SCRIPT,
    folder_picker,
    folder_picker_command,
    pick_folder,
)

HOME = Path("/home/maria")
COMANDO = ("seletor", "--pasta")


def _which(*disponiveis: str):  # type: ignore[no-untyped-def]  # justificativa: fábrica de teste
    return lambda nome: f"/usr/bin/{nome}" if nome in disponiveis else None


class _Run:
    """``subprocess.run`` falso: grava os argumentos e devolve (ou levanta) o combinado."""

    def __init__(
        self, stdout: str = "", returncode: int = 0, erro: BaseException | None = None
    ) -> None:
        self._resultado = subprocess.CompletedProcess(COMANDO, returncode, stdout, "")
        self._erro = erro
        self.chamadas: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.chamadas.append((args, kwargs))
        if self._erro is not None:
            raise self._erro
        return self._resultado


def test_linux_com_kdialog_usa_o_kdialog() -> None:
    assert folder_picker_command("Linux", _which("kdialog"), HOME) == (
        "/usr/bin/kdialog",
        "--title",
        PICK_TITLE,
        "--getexistingdirectory",
        "/home/maria",
    )


def test_linux_so_com_zenity_usa_o_zenity() -> None:
    assert folder_picker_command("Linux", _which("zenity"), HOME) == (
        "/usr/bin/zenity",
        "--file-selection",
        "--directory",
        f"--title={PICK_TITLE}",
        "--filename=/home/maria/",
    )


def test_linux_com_os_dois_vale_o_kdialog() -> None:
    comando = folder_picker_command("Linux", _which("zenity", "kdialog"), HOME)
    assert comando is not None
    assert comando[0] == "/usr/bin/kdialog"


def test_linux_sem_nenhum_nao_tem_comando() -> None:
    assert folder_picker_command("Linux", _which(), HOME) is None


def test_windows_com_powershell_roda_o_script() -> None:
    assert folder_picker_command("Windows", _which("powershell"), HOME) == (
        "/usr/bin/powershell",
        "-NoProfile",
        "-NonInteractive",
        "-STA",
        "-Command",
        WINDOWS_SCRIPT,
    )


def test_windows_sem_powershell_nao_tem_comando() -> None:
    assert folder_picker_command("Windows", _which("kdialog", "zenity"), HOME) is None


def test_outros_sistemas_nao_tem_comando() -> None:
    assert folder_picker_command("Darwin", _which("kdialog", "zenity", "powershell"), HOME) is None


def test_script_do_windows_abre_a_janela_na_frente_e_devolve_utf8() -> None:
    assert "FolderBrowserDialog" in WINDOWS_SCRIPT
    assert "TopMost = $true" in WINDOWS_SCRIPT
    saida_sem_bom = "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false"
    assert saida_sem_bom in WINDOWS_SCRIPT


def test_pick_folder_devolve_o_caminho_inteiro() -> None:
    run = _Run(stdout="C:\\Users\\Mãe\\OneDrive\\Painel de Opções\r\n")
    assert pick_folder(COMANDO, run) == "C:\\Users\\Mãe\\OneDrive\\Painel de Opções"


def test_pick_folder_ignora_o_bom_no_comeco_da_saida() -> None:
    run = _Run(stdout="\ufeffC:\\Users\\Mãe\\OneDrive\\Painel de Opções\r\n")
    assert pick_folder(COMANDO, run) == "C:\\Users\\Mãe\\OneDrive\\Painel de Opções"


def test_pick_folder_so_com_o_bom_e_cancelamento() -> None:
    assert pick_folder(COMANDO, _Run(stdout="\ufeff\r\n")) is None


def test_pick_folder_com_fim_de_linha_unix() -> None:
    assert pick_folder(COMANDO, _Run(stdout="/home/maria/nuvem\n")) == "/home/maria/nuvem"


@pytest.mark.parametrize("saida", ["", "/home/maria/nuvem\n"])
def test_pick_folder_com_codigo_diferente_de_zero_e_cancelamento(saida: str) -> None:
    assert pick_folder(COMANDO, _Run(stdout=saida, returncode=1)) is None


@pytest.mark.parametrize("saida", ["", "\n", "\r\n"])
def test_pick_folder_sem_saida_e_cancelamento(saida: str) -> None:
    assert pick_folder(COMANDO, _Run(stdout=saida)) is None


@pytest.mark.parametrize(
    "erro", [subprocess.TimeoutExpired(COMANDO, PICK_TIMEOUT_S), FileNotFoundError("seletor")]
)
def test_pick_folder_que_estoura_o_tempo_ou_falha_ao_abrir_da_none(erro: BaseException) -> None:
    assert pick_folder(COMANDO, _Run(erro=erro)) is None


def test_pick_folder_com_saida_que_nao_e_utf8_da_none() -> None:
    erro = UnicodeDecodeError("utf-8", b"\xe3", 0, 1, "invalid continuation byte")
    assert pick_folder(COMANDO, _Run(erro=erro)) is None


def test_pick_folder_roda_sem_console_sem_teclado_e_com_tempo_limite() -> None:
    run = _Run(stdout="/p\n")
    pick_folder(COMANDO, run)

    [(args, kwargs)] = run.chamadas
    assert args == (list(COMANDO),)
    assert kwargs["timeout"] == 600.0
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["check"] is False
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


def test_pick_folder_aceita_o_tempo_limite_de_quem_chama() -> None:
    run = _Run(stdout="/p\n")
    pick_folder(COMANDO, run, timeout_s=5.0)
    assert run.chamadas[0][1]["timeout"] == 5.0


def test_folder_picker_sem_comando_nao_tem_seletor() -> None:
    assert folder_picker("Linux", _which(), HOME) is None


def test_folder_picker_com_comando_devolve_uma_funcao_que_escolhe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recebidos: list[tuple[str, ...]] = []

    def falso(command: tuple[str, ...]) -> str | None:
        recebidos.append(command)
        return "/home/maria/nuvem"

    monkeypatch.setattr(modulo, "pick_folder", falso)
    escolher: Callable[[], str | None] | None = folder_picker("Linux", _which("kdialog"), HOME)

    assert escolher is not None
    assert escolher() == "/home/maria/nuvem"
    assert recebidos == [folder_picker_command("Linux", _which("kdialog"), HOME)]

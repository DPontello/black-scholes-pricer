"""Janela do sistema para escolher uma pasta, ao lado do ``launch.py``.

O servidor é local (o mesmo PC de quem usa), por isso é ele quem abre a janela: o navegador
não entrega o caminho completo de uma pasta. No Linux vale o ``kdialog`` ou o ``zenity``; no
Windows, o ``FolderBrowserDialog`` pelo PowerShell. A janela do Windows ainda precisa ser
conferida no PC do autor (abrir na frente e devolver o caminho com acento inteiro)."""

import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

__all__ = [
    "PICK_TIMEOUT_S",
    "PICK_TITLE",
    "WINDOWS_SCRIPT",
    "FolderPicker",
    "folder_picker",
    "folder_picker_command",
    "pick_folder",
]

FolderPicker = Callable[[], str | None]

# Quem escolhe a pasta pode demorar, mas não para sempre: o pedido não fica pendurado.
PICK_TIMEOUT_S: Final = 600.0
PICK_TITLE: Final = "Escolha a pasta do perfil"

# ``TopMost`` num ``Form`` dono: sem ele a janela abre atrás do Edge. A saída em UTF-8 (sem BOM)
# é para os acentos do caminho (``Mãe``) chegarem inteiros.
WINDOWS_SCRIPT: Final = "; ".join(
    (
        "Add-Type -AssemblyName System.Windows.Forms",
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false",
        "$dono = New-Object System.Windows.Forms.Form"
        " -Property @{ TopMost = $true; ShowInTaskbar = $false }",
        "$janela = New-Object System.Windows.Forms.FolderBrowserDialog",
        "$janela.Description = 'Escolha a pasta do perfil"
        " (pode ser uma pasta da nuvem ou de um pendrive)'",
        "$janela.ShowNewFolderButton = $true",
        "if ($janela.ShowDialog($dono) -eq [System.Windows.Forms.DialogResult]::OK)"
        " { [Console]::Out.Write($janela.SelectedPath) }",
    )
)


def folder_picker_command(
    system: str, which: Callable[[str], str | None], home: Path
) -> tuple[str, ...] | None:
    if system == "Windows":
        powershell = which("powershell")
        if powershell is None:
            return None
        return (powershell, "-NoProfile", "-NonInteractive", "-STA", "-Command", WINDOWS_SCRIPT)
    if system == "Linux":
        kdialog = which("kdialog")
        if kdialog:
            return (kdialog, "--title", PICK_TITLE, "--getexistingdirectory", str(home))
        zenity = which("zenity")
        if zenity:
            return (
                zenity,
                "--file-selection",
                "--directory",
                f"--title={PICK_TITLE}",
                f"--filename={home}/",
            )
    return None


def pick_folder(
    command: Sequence[str],
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    timeout_s: float = PICK_TIMEOUT_S,
) -> str | None:
    """O caminho escolhido, ou ``None`` se a pessoa cancelou ou a janela não chegou a abrir."""
    try:
        resultado = run(
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            timeout=timeout_s,
            check=False,
            # Sem isso o Windows abre um console preto junto da janela.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired, UnicodeDecodeError):
        return None
    if resultado.returncode != 0:
        return None
    # O PowerShell pode pôr um BOM no começo da saída em UTF-8; sem tirar, o caminho não existiria.
    # Do fim, só o fim de linha: espaços no fim do nome da pasta são do nome.
    return resultado.stdout.removeprefix("\ufeff").rstrip("\r\n") or None


def folder_picker(
    system: str, which: Callable[[str], str | None], home: Path
) -> FolderPicker | None:
    command = folder_picker_command(system, which, home)
    if command is None:
        return None
    return lambda: pick_folder(command)

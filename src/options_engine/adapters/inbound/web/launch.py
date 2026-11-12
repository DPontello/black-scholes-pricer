"""Ponto de partida do app local: pasta de configuração, porta, janela de app e servidor.

Só stdlib no topo: o uvicorn (extra ``app``) entra só quando o servidor sobe."""

import json
import logging
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from logging.handlers import RotatingFileHandler
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final, Protocol, TextIO

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "APP_ID",
    "DEFAULT_PORT",
    "ESPERA_JANELA_ANTIGA_S",
    "HOST",
    "Encerramento",
    "already_running",
    "app_window_command",
    "console_log",
    "default_static_dir",
    "downloads_dir",
    "find_free_port",
    "has_flatpak_app",
    "log_handler",
    "open_window",
    "platform_config_dir",
    "serve",
    "windows_edge_paths",
]

DEFAULT_PORT: Final = 8765
# O GET /api/saude diz este nome: é como um segundo processo reconhece o app já aberto na porta.
APP_ID: Final = "painel-de-opcoes"
HOST: Final = "127.0.0.1"
_PORT_ATTEMPTS: Final = 20
_READY_TIMEOUT_S: Final = 30.0
# Depois de uma atualização, quanto o app novo espera a janela antiga do navegador voltar a falar
# com ele antes de abrir uma janela própria (o navegador refaz a conexão sozinho, em segundos).
ESPERA_JANELA_ANTIGA_S: Final = 15.0
_LINUX_BROWSERS: Final = ("google-chrome", "chromium", "brave-browser")
_FLATPAK_BROWSERS: Final = ("com.google.Chrome", "com.brave.Browser")
LOG_MAX_BYTES: Final = 5 * 1024 * 1024
LOG_BACKUPS: Final = 3


def platform_config_dir(system: str, env: Mapping[str, str], home: Path) -> Path:
    if system == "Windows":
        appdata = env.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / "PainelOpcoes"
    xdg = env.get("XDG_CONFIG_HOME")
    # XDG relativo é ignorado (especificação XDG).
    base = Path(xdg) if xdg and PurePosixPath(xdg).is_absolute() else home / ".config"
    return base / "painel-opcoes"


_ID_DOWNLOADS: Final = "{374DE290-123F-4565-9164-39C4925E467B}"
_XDG_DOWNLOAD: Final = re.compile(r'^XDG_DOWNLOAD_DIR="(.*)"\s*$', re.M)


def _downloads_do_registro() -> str | None:
    try:
        import winreg

        chave = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, chave) as k:  # type: ignore[attr-defined,unused-ignore]
            return str(winreg.QueryValueEx(k, _ID_DOWNLOADS)[0])  # type: ignore[attr-defined,unused-ignore]
    except (ImportError, OSError):
        return None


def downloads_dir(
    system: str,
    env: Mapping[str, str],
    home: Path,
    registry: Callable[[], str | None] = _downloads_do_registro,
) -> Path:
    """A pasta Downloads do usuário, mesmo movida (Windows) ou traduzida (Linux)."""
    if system == "Windows":
        valor = registry()
        return Path(os.path.expandvars(valor)) if valor else home / "Downloads"
    config = env.get("XDG_CONFIG_HOME") or str(home / ".config")
    try:
        texto = (Path(config) / "user-dirs.dirs").read_text(encoding="utf-8")
    except OSError:
        texto = ""
    achado = _XDG_DOWNLOAD.search(texto)
    return Path(achado.group(1).replace("$HOME", str(home))) if achado else home / "Downloads"


def find_free_port(preferred: int, *, attempts: int = _PORT_ATTEMPTS) -> int:
    for port in range(preferred, preferred + attempts):
        if _is_free(port):
            return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((HOST, port))
        except OSError:
            return False
    return True


def windows_edge_paths(env: Mapping[str, str]) -> tuple[Path, ...]:
    # O Edge em geral não está no PATH.
    bases = [env.get(var) for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    return tuple(
        Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe" for base in bases if base
    )


def app_window_command(
    system: str,
    url: str,
    which: Callable[[str], str | None],
    has_flatpak: Callable[[str], bool],
    windows_paths: Sequence[Path] = (),
) -> tuple[str, ...] | None:
    app_flag = f"--app={url}"
    if system == "Windows":
        edge = which("msedge") or next((str(p) for p in windows_paths if p.is_file()), None)
        return None if edge is None else (edge, app_flag)
    for browser in _LINUX_BROWSERS:
        if which(browser):
            return (browser, app_flag)
    for app_id in _FLATPAK_BROWSERS:
        if has_flatpak(app_id):
            return ("flatpak", "run", app_id, app_flag)
    return None


def has_flatpak_app(app_id: str) -> bool:
    try:
        resultado = subprocess.run(
            ["flatpak", "info", app_id], capture_output=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return resultado.returncode == 0


def default_static_dir(meipass: Path | None = None) -> Path:
    """A tela compilada; no app instalado, dentro do executável (``meipass``)."""
    if meipass is not None:
        return meipass / "static"
    return Path(__file__).resolve().parent / "static"


def _pasta_de_logs(config_dir: Path) -> Path:
    pasta = config_dir / "logs"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def log_handler(config_dir: Path) -> logging.Handler:
    """O log do app instalado, que não tem console: ``logs/app.log`` rotativo."""
    handler = RotatingFileHandler(
        _pasta_de_logs(config_dir) / "app.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    return handler


def console_log(config_dir: Path) -> TextIO:
    """Para onde vão a saída e os erros sem tratamento do app instalado: sem console, o Python
    os perderia. Só a última execução (``logs/console.log``)."""
    return (_pasta_de_logs(config_dir) / "console.log").open("w", encoding="utf-8", buffering=1)


def open_window(command: tuple[str, ...] | None, url: str) -> None:
    if command is None:
        webbrowser.open(url)
        return
    try:
        subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        webbrowser.open(url)


def _saude(url: str) -> object:
    with urllib.request.urlopen(f"{url}api/saude", timeout=1.0) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def already_running(port: int, fetch: Callable[[str], object] = _saude) -> bool:
    """Se o Painel de Opções já responde nesta porta (outro serviço na porta não conta)."""
    try:
        corpo = fetch(f"http://{HOST}:{port}/")
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return isinstance(corpo, dict) and corpo.get("app") == APP_ID


def wait_until_up(url: str, timeout_s: float = _READY_TIMEOUT_S) -> bool:
    fim = time.monotonic() + timeout_s
    while time.monotonic() < fim:
        try:
            with urllib.request.urlopen(f"{url}api/saude", timeout=1.0) as resposta:
                if resposta.status == 200:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(0.1)
    return False


class _ComSaida(Protocol):
    should_exit: bool


class Encerramento:
    """Pedido de encerramento do servidor vindo de dentro do app (a atualização). ``pedir`` liga o
    ``should_exit`` do uvicorn, o caminho normal, que roda o ``lifespan``: solta a trava do perfil
    e para a ponte. Um ``pedir`` antes de ``ligar`` fica guardado e vale ao ligar."""

    def __init__(self) -> None:
        self._servidor: _ComSaida | None = None
        self._pedido = False

    def ligar(self, servidor: _ComSaida) -> None:
        self._servidor = servidor
        if self._pedido:
            servidor.should_exit = True

    def pedir(self) -> None:
        self._pedido = True
        if self._servidor is not None:
            self._servidor.should_exit = True


def serve(
    app: "FastAPI",
    port: int,
    on_ready: Callable[[], None] | None = None,
    encerramento: Encerramento | None = None,
) -> None:
    import threading

    import uvicorn

    if on_ready is not None:
        url = f"http://{HOST}:{port}/"

        def quando_subir() -> None:
            if wait_until_up(url):
                on_ready()

        threading.Thread(target=quando_subir, name="abrir-janela", daemon=True).start()
    servidor = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="info"))
    if encerramento is not None:
        encerramento.ligar(servidor)
    servidor.run()

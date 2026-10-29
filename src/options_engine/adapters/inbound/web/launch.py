"""Ponto de partida do app local: pasta de configuração, porta, janela de app e servidor.

Só stdlib no topo: o uvicorn (extra ``app``) entra só quando o servidor sobe."""

import socket
import subprocess
import time
import urllib.error
import urllib.request
import webbrowser
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "DEFAULT_PORT",
    "HOST",
    "app_window_command",
    "default_static_dir",
    "find_free_port",
    "has_flatpak_app",
    "open_window",
    "platform_config_dir",
    "serve",
    "windows_edge_paths",
]

DEFAULT_PORT: Final = 8765
HOST: Final = "127.0.0.1"
_PORT_ATTEMPTS: Final = 20
_READY_TIMEOUT_S: Final = 30.0
_LINUX_BROWSERS: Final = ("google-chrome", "chromium", "brave-browser")
_FLATPAK_BROWSERS: Final = ("com.google.Chrome", "com.brave.Browser")


def platform_config_dir(system: str, env: Mapping[str, str], home: Path) -> Path:
    if system == "Windows":
        appdata = env.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / "PainelOpcoes"
    xdg = env.get("XDG_CONFIG_HOME")
    # XDG relativo é ignorado (especificação XDG).
    base = Path(xdg) if xdg and PurePosixPath(xdg).is_absolute() else home / ".config"
    return base / "painel-opcoes"


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


def default_static_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


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


def serve(app: "FastAPI", port: int, on_ready: Callable[[], None] | None = None) -> None:
    import threading

    import uvicorn

    if on_ready is not None:
        url = f"http://{HOST}:{port}/"

        def quando_subir() -> None:
            if wait_until_up(url):
                on_ready()

        threading.Thread(target=quando_subir, name="abrir-janela", daemon=True).start()
    uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="info")).run()

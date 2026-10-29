"""Ponto de partida do app local: pasta de configuração, porta, janela de app e servidor.

Só stdlib no topo: o ``__main__`` importa este módulo, e o uvicorn (extra ``app``) só entra
quando o servidor sobe de fato. Quem monta o app (``config.web_app``) é o ``__main__``: um
adapter não importa o composition root (camadas do import-linter).

A "janela de app" é o navegador em modo aplicativo (``--app=URL``: sem abas nem barra de
endereço), para o app parecer um programa e não um site: Edge no Windows; Chrome, Chromium
ou Brave no Linux (nativos ou flatpak). Sem nenhum deles, abre a aba no navegador padrão.
"""

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
HOST: Final = "127.0.0.1"  # só a própria máquina: o app nunca fica exposto na rede
_PORT_ATTEMPTS: Final = 20
_READY_TIMEOUT_S: Final = 30.0
_LINUX_BROWSERS: Final = ("google-chrome", "chromium", "brave-browser")
_FLATPAK_BROWSERS: Final = ("com.google.Chrome", "com.brave.Browser")


def platform_config_dir(system: str, env: Mapping[str, str], home: Path) -> Path:
    """Pasta de configuração do app: ``%APPDATA%/PainelOpcoes`` no Windows,
    ``$XDG_CONFIG_HOME/painel-opcoes`` (ou ``~/.config``) nos outros."""
    if system == "Windows":
        appdata = env.get("APPDATA")
        return (Path(appdata) if appdata else home / "AppData" / "Roaming") / "PainelOpcoes"
    xdg = env.get("XDG_CONFIG_HOME")
    # A especificação XDG manda ignorar caminho relativo (e o XDG é de caminho POSIX).
    base = Path(xdg) if xdg and PurePosixPath(xdg).is_absolute() else home / ".config"
    return base / "painel-opcoes"


def find_free_port(preferred: int, *, attempts: int = _PORT_ATTEMPTS) -> int:
    """A porta preferida se estiver livre; senão a próxima livre; senão uma qualquer do SO."""
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
    """Onde o Edge costuma estar instalado: em geral ele NÃO está no ``PATH``."""
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
    """Comando que abre ``url`` numa janela de app; ``None`` se não houver navegador para isso."""
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
    """Verdadeiro se o flatpak ``app_id`` está instalado (e o próprio flatpak existe)."""
    try:
        resultado = subprocess.run(
            ["flatpak", "info", app_id], capture_output=True, check=False, timeout=10
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return resultado.returncode == 0


def default_static_dir() -> Path:
    """Onde o ``npm --prefix frontend run build`` deixa o frontend compilado."""
    return Path(__file__).resolve().parent / "static"


def open_window(command: tuple[str, ...] | None, url: str) -> None:
    """Abre a janela de app, ou a aba do navegador padrão sem ``command``."""
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
    except OSError:  # navegador sumiu entre a busca e agora: a aba comum serve
        webbrowser.open(url)


def wait_until_up(url: str, timeout_s: float = _READY_TIMEOUT_S) -> bool:
    """Espera ``GET {url}api/saude`` responder 200; falso se o prazo acabar."""
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
    """Sobe o uvicorn em ``127.0.0.1:port`` até Ctrl+C; ``on_ready`` roda quando ele responde."""
    import threading

    import uvicorn

    if on_ready is not None:
        url = f"http://{HOST}:{port}/"

        def quando_subir() -> None:
            if wait_until_up(url):
                on_ready()

        threading.Thread(target=quando_subir, name="abrir-janela", daemon=True).start()
    uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="info")).run()

"""``BridgeProcess`` — lança, adota, relança e encerra a ponte do Tryd.

A ponte é um processo separado (Python do Windows; no Linux, dentro do Wine num distrobox).
O app não depende dela para abrir: se ela não sobe, o status diz "desconectado" e as
cotações vêm do fim de dia.
"""

import logging
import platform
import subprocess
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from options_engine.adapters.outbound.tryd.client import TrydBridgeClient

__all__ = [
    "RELAUNCH_INTERVAL_S",
    "STOP_WAIT_S",
    "BridgeProcess",
    "ProcessHandle",
    "ProcessSpawner",
    "bridge_kill_command",
    "default_bridge_command",
    "spawn_process",
]

_log = logging.getLogger(__name__)

RELAUNCH_INTERVAL_S = 10.0
STOP_WAIT_S = 3.0
_KILL_WAIT_S = 10.0


class ProcessHandle(Protocol):
    """O que o lançador usa de um ``subprocess.Popen``."""

    def poll(self) -> int | None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def terminate(self) -> None: ...


ProcessSpawner = Callable[[Sequence[str], Path], ProcessHandle]


def spawn_process(command: Sequence[str], cwd: Path) -> ProcessHandle:
    """Executor real: ``Popen`` sem stdin (a ponte não lê do terminal do app)."""
    return subprocess.Popen(list(command), cwd=cwd, stdin=subprocess.DEVNULL)


def default_bridge_command(
    system: str, src_dir: Path, home: Path, port: int
) -> tuple[tuple[str, ...], Path]:
    """Comando que sobe a ponte e o diretório de trabalho dele (``src_dir``, onde mora
    ``options_ponte``). ``system`` é o de ``platform.system()``; o que não é Windows usa o Wine.
    """
    if system == "Windows":  # desenvolvimento: Python do Windows no PATH
        return ("python", "-m", "options_ponte", "servir", "--porta", str(port)), src_dir
    return (
        "distrobox",
        "enter",
        "tryd",
        "--",
        "env",
        f"WINEPREFIX={home}/.local/share/wineprefixes/tryd",
        "WINEDEBUG=-all",
        "wine",
        "C:\\Python312\\python.exe",
        "-m",
        "options_ponte",
        "servir",
        "--porta",
        str(port),
    ), src_dir


def bridge_kill_command(system: str) -> tuple[str, ...] | None:
    """Comando que mata a ponte que sobrou dentro do distrobox; ``None`` onde não se aplica.

    Encerrar o ``distrobox enter`` (``terminate``) não leva o ``wine python`` junto. O padrão
    ``[o]ptions_ponte`` casa com a ponte mas não com a linha de comando deste próprio
    ``pkill`` (que o ``pkill -f`` também varre, e o distrobox compartilha os processos do host).
    """
    if system == "Windows":
        return None
    return ("distrobox", "enter", "tryd", "--", "pkill", "-f", "[o]ptions_ponte servir")


class BridgeProcess:
    """Garante uma ponte no ar: adota a que já responde, senão lança a sua e a cuida.

    A ponte adotada não é nossa: ``stop`` não a encerra enquanto ela está viva. Se ela cai,
    ``ensure_running`` lança a nossa, e daí em diante é nossa e o ``stop`` a encerra.
    ``ensure_running`` é chamado de tempos em tempos por quem compõe o app.
    """

    def __init__(
        self,
        command: tuple[str, ...],
        cwd: Path,
        client: TrydBridgeClient,
        *,
        spawn: ProcessSpawner = spawn_process,
        monotonic: Callable[[], float] = time.monotonic,
        system: str | None = None,
    ) -> None:
        self._command = command
        self._cwd = cwd
        self._client = client
        self._spawn = spawn
        self._monotonic = monotonic
        self._system = platform.system() if system is None else system
        self._lock = threading.Lock()
        self._process: ProcessHandle | None = None
        self._adopted = False
        self._launched_by_us = False  # já tentamos lançar: a ponte é nossa para cuidar
        self._stopped = False
        self._last_attempt_at: float | None = None  # adotar não conta como tentativa de lançar

    def start(self) -> None:
        """Adota a ponte que já responde ``Pong``; se não há, lança o comando. Não espera subir."""
        with self._lock:
            self._stopped = False
            if self._client.bridge_responds():
                self._adopted = True
                _log.info("ponte do Tryd já está no ar; adotada")
                return
            self._launch()

    def stop(self) -> None:
        """``Encerrar`` -> espera ``STOP_WAIT_S`` -> ``terminate``; no Linux, mata o que sobrou."""
        with self._lock:
            self._stopped = True
            process = self._process
            self._process = None
            if self._adopted or process is None:
                return
            self._client.shutdown_bridge()
            try:
                process.wait(timeout=STOP_WAIT_S)
            except subprocess.TimeoutExpired:
                process.terminate()
            kill_command = bridge_kill_command(self._system)
            if kill_command is not None and self._client.bridge_responds():
                _log.warning("a ponte ainda responde depois de encerrada; matando no distrobox")
                self._run_to_the_end(kill_command)

    def ensure_running(self) -> None:
        """Lança de novo se nenhuma ponte responde na porta, a cada 10 s no máximo.

        Vale para a ponte que lançamos (o processo saiu) e para a adotada (parou de responder).
        """
        with self._lock:
            if self._stopped or not (self._adopted or self._launched_by_us):
                return
            if self._process is not None and self._process.poll() is None:
                return
            if (
                self._last_attempt_at is not None
                and self._monotonic() - self._last_attempt_at < RELAUNCH_INTERVAL_S
            ):
                return
            if self._client.bridge_responds():  # o processo saiu, mas a ponte segue de pé
                return
            _log.warning("a ponte do Tryd não responde; lançando de novo")
            self._launch()

    def _launch(self) -> None:
        self._adopted = False  # a ponte que sobe agora é nossa
        self._launched_by_us = True
        self._last_attempt_at = self._monotonic()
        try:
            self._process = self._spawn(self._command, self._cwd)
        except OSError as erro:  # sem distrobox/python: o app segue, sem ponte
            self._process = None
            _log.error("não foi possível lançar a ponte (%s): %s", self._command[0], erro)

    def _run_to_the_end(self, command: tuple[str, ...]) -> None:
        try:
            handle = self._spawn(command, self._cwd)
        except OSError as erro:
            _log.error("não foi possível rodar %s: %s", command[0], erro)
            return
        try:
            handle.wait(timeout=_KILL_WAIT_S)
        except subprocess.TimeoutExpired:
            handle.terminate()

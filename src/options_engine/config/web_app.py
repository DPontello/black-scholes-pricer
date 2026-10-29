"""Composition root do app web. Fora do ``composition`` para o núcleo e o CLI
seguirem sem o FastAPI (extra ``app``)."""

import asyncio
import contextlib
import logging
import platform
import threading
from collections.abc import AsyncIterator, Sequence
from datetime import date
from pathlib import Path
from typing import Final, Protocol

from fastapi import FastAPI

import options_ponte
from options_engine.adapters.inbound.web.app import Lifespan, create_app
from options_engine.adapters.inbound.web.b3files import router_arquivos_b3
from options_engine.adapters.inbound.web.market import router_mercado
from options_engine.adapters.inbound.web.profiles import router_perfis
from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET, StaticHolidayCalendar
from options_engine.adapters.outbound.b3files import (
    B3FileKind,
    B3FileLibrary,
    cadastro_freshness,
)
from options_engine.adapters.outbound.b3files.downloads import (
    DownloadsImporter,
    ImportacaoAutomatica,
)
from options_engine.adapters.outbound.b3files.end_of_day import EndOfDayMarket
from options_engine.adapters.outbound.clock import SystemClock
from options_engine.adapters.outbound.fallback_market import FallbackMarket
from options_engine.adapters.outbound.storage import JsonProfileRepository
from options_engine.adapters.outbound.tryd import (
    BridgeProcess,
    LiveBoard,
    TrydBridgeClient,
    default_bridge_command,
)
from options_engine.adapters.outbound.tryd.feed import TrydMarketFeed
from options_engine.adapters.outbound.tryd.settings import PORTA_PONTE
from options_engine.application.ports.inbound import ProfileUseCase
from options_engine.application.ports.outbound import CadastroFreshness, Clock, TradingCalendar
from options_engine.application.use_cases.market_view import MarketViewService
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.domain.model.errors import DomainError

__all__ = ["MACHINE_CONFIG_NAME", "MARKET_DIR_NAME", "build_web_app"]

_log = logging.getLogger(__name__)

MACHINE_CONFIG_NAME: Final = "config.json"
MARKET_DIR_NAME: Final = "mercado"
_ENSURE_INTERVAL_S: Final = 2.0
_SCAN_INTERVAL_S: Final = 5.0


class _Bridge(Protocol):
    def start(self) -> None: ...

    def ensure_running(self) -> None: ...

    def stop(self) -> None: ...


class _Scanner(Protocol):
    def scan(self) -> Sequence[ImportacaoAutomatica]: ...


class _Client(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


def build_web_app(
    *,
    config_dir: Path,
    static_dir: Path | None,
    bridge: bool,
    machine_name: str,
    clock: Clock | None = None,
    downloads_dir: Path | None = None,
) -> FastAPI:
    clock = SystemClock() if clock is None else clock
    calendar = StaticHolidayCalendar.from_packaged_data()
    profiles = ProfileService(
        JsonProfileRepository(config_dir / MACHINE_CONFIG_NAME), clock, machine_name
    )
    library = B3FileLibrary(config_dir / MARKET_DIR_NAME, clock)

    def cdi_annual() -> float:
        return profiles.active().cdi_annual

    board = LiveBoard()
    client = TrydBridgeClient(board)
    market = FallbackMarket(
        TrydMarketFeed(client, board, library, calendar, clock, cdi_annual),
        EndOfDayMarket(library, cdi_annual),
    )
    market_view = MarketViewService(
        market,
        calendar,
        B3_UTC_OFFSET,
        freshness=lambda: _freshness(library, calendar, clock),
        cotahist_range=lambda: _cotahist_range(library),
    )
    process = None
    if bridge:
        command, cwd = default_bridge_command(
            platform.system(), _ponte_src_dir(), Path.home(), PORTA_PONTE
        )
        process = BridgeProcess(command, cwd, client)
    importer = None if downloads_dir is None else DownloadsImporter(library, downloads_dir, clock)
    routers = [
        router_perfis(profiles),
        router_arquivos_b3(library, importer),
        router_mercado(market_view, profiles),
    ]
    lifespan = _lifespan(profiles, client, process, importer)
    return create_app(routers, static_dir, lifespan=lifespan)


def _ponte_src_dir() -> Path:
    return Path(options_ponte.__file__).resolve().parent.parent


def _lifespan(
    profiles: ProfileUseCase,
    client: _Client,
    process: _Bridge | None,
    importer: _Scanner | None = None,
    *,
    ensure_interval_s: float = _ENSURE_INTERVAL_S,
    scan_interval_s: float = _SCAN_INTERVAL_S,
) -> Lifespan:

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        stop = threading.Event()
        supervisor = None
        if process is not None:
            client.start()
            supervisor = threading.Thread(
                target=_supervise,
                args=(process, stop, ensure_interval_s),
                name="tryd-bridge-supervisor",
                daemon=True,
            )
            supervisor.start()
        varredor = None
        if importer is not None:
            varredor = threading.Thread(
                target=_varrer,
                args=(importer, stop, scan_interval_s),
                name="b3-downloads",
                daemon=True,
            )
            varredor.start()
        try:
            yield
        finally:
            stop.set()
            await asyncio.to_thread(_shutdown, profiles, client, process, supervisor, varredor)

    return lifespan


def _supervise(process: _Bridge, stop: threading.Event, interval_s: float) -> None:
    try:
        process.start()
    except Exception:  # sem ponte o app segue no fim de dia
        _log.exception("não foi possível subir a ponte do Tryd")
    while not stop.wait(interval_s):
        try:
            process.ensure_running()
        except Exception:
            _log.exception("falha ao conferir a ponte do Tryd")


def _varrer(importer: _Scanner, stop: threading.Event, interval_s: float) -> None:
    while True:
        try:
            for evento in importer.scan():
                _log.info("Downloads: %s %s", evento.nome, evento.detalhe)
        except Exception:
            _log.exception("falha ao ler a pasta Downloads")
        if stop.wait(interval_s):
            return


def _shutdown(
    profiles: ProfileUseCase,
    client: _Client,
    process: _Bridge | None,
    supervisor: threading.Thread | None,
    varredor: threading.Thread | None = None,
) -> None:
    # Cada passo isolado: a trava do perfil tem de sair mesmo se o resto falhar.
    for thread in (supervisor, varredor):
        if thread is not None:
            thread.join(timeout=5.0)
    if process is not None:
        for passo in (process.stop, client.stop):
            try:
                passo()
            except Exception:
                _log.exception("falha ao encerrar a ponte do Tryd")
    try:
        profiles.close()
    except Exception:
        _log.exception("falha ao soltar a trava do perfil")


def _freshness(
    library: B3FileLibrary, calendar: TradingCalendar, clock: Clock
) -> CadastroFreshness | str:
    try:
        latest = library.latest_cadastro()
    except (DomainError, OSError) as erro:
        return f"biblioteca de arquivos da B3 ilegível: {erro}"
    if latest is None:
        return "nenhum Cadastro de Instrumentos importado"
    if latest.reference_date is None:
        return f"o nome do cadastro '{latest.name}' não traz a data (_AAAAMMDD)"
    today = clock.now().astimezone(B3_UTC_OFFSET).date()
    try:
        freshness = cadastro_freshness(library, calendar, today)
    except DomainError as erro:  # data fora do calendário de feriados
        return f"não deu para contar a idade do cadastro: {erro}"
    except OSError as erro:
        return f"biblioteca de arquivos da B3 ilegível: {erro}"
    return "nenhum Cadastro de Instrumentos importado" if freshness is None else freshness


def _cotahist_range(library: B3FileLibrary) -> tuple[date, date] | None:
    try:
        files = library.files()
    except (DomainError, OSError):
        return None
    starts = [f.first_date for f in files if f.kind is B3FileKind.COTAHIST and f.first_date]
    ends = [f.reference_date for f in files if f.kind is B3FileKind.COTAHIST and f.reference_date]
    if not starts or not ends:
        return None
    return min(starts), max(ends)

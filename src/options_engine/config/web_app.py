"""Composition root do app web — perfis, arquivos da B3, mercado com recuo e a ponte do Tryd.

Mesma disciplina do ``composition``: wiring manual, linha a linha. Fica num módulo à parte
porque importa o FastAPI (extra ``app``): o ``composition`` e o painel de linha de comando
seguem funcionando sem ele.

O que o app monta:

- perfis em JSON, com a configuração da máquina em ``config_dir/config.json``;
- a biblioteca de arquivos da B3 em ``config_dir/mercado`` (local: arquivo da B3 não viaja
  com o perfil);
- o mercado: Tryd ao vivo pela ponte, com recuo para o fim de dia dos arquivos quando a ponte
  cai (``FallbackMarket``); o CDI é o do perfil aberto, lido a cada consulta;
- o ciclo de vida: com ``bridge``, o cliente da ponte sobe com o servidor, e uma thread
  própria adota ou lança a ponte e a relança quando ela some (as chamadas dela podem
  bloquear por segundos e não podem rodar no laço de eventos). Ao desligar, a ponte é
  encerrada e o perfil fechado; a trava do perfil é solta mesmo se o resto falhar.
"""

import asyncio
import contextlib
import logging
import platform
import threading
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Final, Protocol

from fastapi import FastAPI

import options_ponte
from options_engine.adapters.inbound.web.app import Lifespan, create_app
from options_engine.adapters.inbound.web.b3files import router_arquivos_b3
from options_engine.adapters.inbound.web.profiles import router_perfis
from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET, StaticHolidayCalendar
from options_engine.adapters.outbound.b3files import (
    B3FileKind,
    B3FileLibrary,
    cadastro_freshness,
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
# De quanto em quanto tempo a thread da ponte confere se ela ainda está no ar. O lançador
# já espaça os relançamentos (10 s); isto só define com que atraso a queda é notada.
_ENSURE_INTERVAL_S: Final = 2.0


class _Bridge(Protocol):
    """O que o ciclo de vida usa do lançador da ponte (``BridgeProcess``)."""

    def start(self) -> None: ...

    def ensure_running(self) -> None: ...

    def stop(self) -> None: ...


class _Client(Protocol):
    """O que o ciclo de vida usa do cliente da ponte (``TrydBridgeClient``)."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


def build_web_app(
    *,
    config_dir: Path,
    static_dir: Path | None,
    bridge: bool,
    machine_name: str,
    clock: Clock | None = None,
) -> FastAPI:
    """O app inteiro; ``bridge=False`` não sobe a ponte, e o mercado fica no fim de dia."""
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
    routers = [router_perfis(profiles), router_arquivos_b3(library)]
    app = create_app(routers, static_dir, lifespan=_lifespan(profiles, client, process))
    app.state.market_view = market_view  # a Task 13 liga o router de mercado
    return app


def _ponte_src_dir() -> Path:
    """A pasta que contém o pacote ``options_ponte``: é de lá que a ponte é lançada."""
    return Path(options_ponte.__file__).resolve().parent.parent


def _lifespan(
    profiles: ProfileUseCase,
    client: _Client,
    process: _Bridge | None,
    *,
    ensure_interval_s: float = _ENSURE_INTERVAL_S,
) -> Lifespan:
    """Sobe a ponte (se houver) com o servidor; ao desligar, encerra a ponte e fecha o perfil."""

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
        try:
            yield
        finally:
            stop.set()
            await asyncio.to_thread(_shutdown, profiles, client, process, supervisor)

    return lifespan


def _supervise(process: _Bridge, stop: threading.Event, interval_s: float) -> None:
    """Thread da ponte: adota ou lança, e relança quando ela some, até ``stop``."""
    try:
        process.start()
    except Exception:  # a ponte é opcional: sem ela o app segue no fim de dia
        _log.exception("não foi possível subir a ponte do Tryd")
    while not stop.wait(interval_s):
        try:
            process.ensure_running()
        except Exception:
            _log.exception("falha ao conferir a ponte do Tryd")


def _shutdown(
    profiles: ProfileUseCase,
    client: _Client,
    process: _Bridge | None,
    supervisor: threading.Thread | None,
) -> None:
    """Cada passo isolado: a falha de um não impede os outros, e a trava sai sempre."""
    if supervisor is not None:
        supervisor.join(timeout=5.0)
    if process is not None:
        for passo in (process.stop, client.stop):
            try:
                passo()
            except Exception:
                _log.exception("falha ao encerrar a ponte do Tryd")
    try:
        profiles.close()
    except Exception:  # pasta do perfil fora do ar, config.json ilegível: o app tem de fechar
        _log.exception("falha ao soltar a trava do perfil")


def _freshness(
    library: B3FileLibrary, calendar: TradingCalendar, clock: Clock
) -> CadastroFreshness | str:
    """Idade do cadastro mais recente, ou o motivo de não haver (texto para a tela)."""
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
    except DomainError as erro:  # data fora da cobertura do calendário de feriados
        return f"não deu para contar a idade do cadastro: {erro}"
    except OSError as erro:
        return f"biblioteca de arquivos da B3 ilegível: {erro}"
    return "nenhum Cadastro de Instrumentos importado" if freshness is None else freshness


def _cotahist_range(library: B3FileLibrary) -> tuple[date, date] | None:
    """Do menor ao maior pregão dos COTAHIST importados; ``None`` sem nenhum."""
    try:
        files = library.files()
    except (DomainError, OSError):
        return None
    starts = [f.first_date for f in files if f.kind is B3FileKind.COTAHIST and f.first_date]
    ends = [f.reference_date for f in files if f.kind is B3FileKind.COTAHIST and f.reference_date]
    if not starts or not ends:
        return None
    return min(starts), max(ends)

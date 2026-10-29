"""Os arquivos da biblioteca lidos para consulta: o último pregão e o cadastro mais recente.

O fim de dia (``EndOfDayMarket``) e o ao vivo (``TrydMarketFeed``) precisam do mesmo
recorte da biblioteca: o último pregão dos COTAHIST (fechamentos, tickers conhecidos) e o
cadastro de instrumentos mais recente. Aqui mora a regra única de qual é esse recorte e de
quando relê-lo: ``library.files()`` é comparada a cada consulta (a tupla inteira, que muda a
cada importação) e só então os arquivos são relidos.

Sem cadastro ou sem COTAHIST não há o que consultar, e arquivo que não abre na leitura não
derruba a consulta: ``load`` devolve o MOTIVO (``str``) em vez de levantar. Tanto o sucesso
quanto a falha ficam guardados até a biblioteca mudar, para um arquivo estragado não ser
relido a cada consulta.

O cache sqlite do pregão fica em ``<raiz da biblioteca>/cache.sqlite`` (a raiz sai do caminho
dos arquivos: ``<raiz>/<tipo>/<nome>``), compartilhado por quem usa a mesma biblioteca.
"""

import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.b3files.library import B3FileKind, B3FileLibrary, ImportedFile
from options_engine.adapters.outbound.cotahist.errors import SourceFileError
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo, load_instruments
from options_engine.adapters.outbound.cotahist.parser import MARKET_SPOT, CotahistRecord
from options_engine.adapters.outbound.cotahist.session import SessionData, load_session_data
from options_engine.domain.model.errors import DomainError

__all__ = ["NO_FILES_REASON", "LibraryLoader", "LoadedLibrary"]

NO_FILES_REASON: Final = "sem arquivos da B3 importados"
_CACHE_NAME: Final = "cache.sqlite"


@dataclass(frozen=True, slots=True)
class LoadedLibrary:
    """O que a biblioteca tinha quando foi lida.

    ``files``: a foto de ``library.files()`` que originou a leitura. ``session``: o maior
    pregão dos COTAHIST. ``cotahist_paths``: do pregão mais antigo ao mais novo, como a
    biblioteca os ordena. ``data``: os registros desse pregão e os fechamentos até ele.
    """

    files: tuple[ImportedFile, ...]
    session: date
    cotahist_paths: tuple[Path, ...]
    instruments_path: Path
    cache_path: Path
    instruments: Mapping[str, InstrumentInfo]
    data: SessionData
    spot_records: Mapping[str, CotahistRecord]

    def knows(self, symbol: str) -> bool:
        """Ticker do cadastro ou ticker à vista visto em algum pregão dos COTAHIST."""
        return symbol in self.instruments or symbol in self.data.known_spot_symbols


class LibraryLoader:
    """Lê a biblioteca sob demanda e relê quando ela muda; seguro para várias threads."""

    def __init__(self, library: B3FileLibrary) -> None:
        self._library = library
        self._lock = threading.Lock()
        self._cached: tuple[tuple[ImportedFile, ...], LoadedLibrary | str] | None = None

    def load(self) -> LoadedLibrary | str:
        """Biblioteca lida, ou o motivo de não haver o que consultar."""
        try:
            files = self._library.files()
        except (DomainError, OSError) as erro:  # índice ilegível: pasta fora do ar, arquivo em uso
            return f"biblioteca de arquivos da B3 ilegível: {erro}"
        with self._lock:
            if self._cached is None or self._cached[0] != files:
                self._cached = (files, self._read(files))
            return self._cached[1]

    def _read(self, files: tuple[ImportedFile, ...]) -> LoadedLibrary | str:
        sessions = [
            f.reference_date
            for f in files
            if f.kind is B3FileKind.COTAHIST and f.reference_date is not None
        ]
        try:
            cadastro = self._library.latest_cadastro()
            if cadastro is None or not sessions:
                return NO_FILES_REASON
            session = max(sessions)
            paths = self._library.cotahist_paths()
            cache_path = cadastro.path.parent.parent / _CACHE_NAME
            instruments = load_instruments(cadastro.path)
            data, _ = load_session_data(paths, session, cache_path)
        except (DomainError, OSError, SourceFileError) as erro:
            return f"arquivos da B3 ilegíveis: {erro}"
        spot_records = {r.symbol: r for r in data.records if r.market == MARKET_SPOT}
        return LoadedLibrary(
            files, session, paths, cadastro.path, cache_path, instruments, data, spot_records
        )

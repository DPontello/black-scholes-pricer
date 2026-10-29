"""Importa sozinho os arquivos da B3 que o usuário baixa para a pasta Downloads.

O download continua manual (termos da B3 e CAPTCHA, ADR-0006); só o arrastar some.
"""

import re
import threading
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.b3files.library import B3FileLibrary, B3FileRejectedError
from options_engine.application.ports.outbound import Clock
from options_engine.domain.model.errors import DomainError

__all__ = ["DownloadsImporter", "ImportacaoAutomatica"]

_NOME_B3: Final = re.compile(r"^(COTAHIST.*\.(zip|txt)|InstrumentsConsolidated.*\.csv)$", re.I)
_HISTORICO: Final = 20
_TIPOS: Final = {"cotahist": "COTAHIST", "cadastro": "Cadastro de Instrumentos"}


@dataclass(frozen=True, slots=True)
class ImportacaoAutomatica:
    nome: str
    quando: datetime
    importado: bool
    detalhe: str


class DownloadsImporter:
    def __init__(self, library: B3FileLibrary, folder: Path, clock: Clock) -> None:
        self._library = library
        self._folder = folder
        self._clock = clock
        self._lock = threading.Lock()
        # (tamanho, mtime) por nome: visto na passada anterior e já tratado.
        self._vistos: dict[str, tuple[int, float]] = {}
        self._tratados: dict[str, tuple[int, float]] = {}
        self._eventos: deque[ImportacaoAutomatica] = deque(maxlen=_HISTORICO)

    @property
    def folder(self) -> Path:
        return self._folder

    def eventos(self) -> tuple[ImportacaoAutomatica, ...]:
        with self._lock:
            return tuple(reversed(self._eventos))

    def scan(self) -> tuple[ImportacaoAutomatica, ...]:
        """Uma passada pela pasta; devolve o que importou ou recusou nesta passada."""
        with self._lock:
            try:
                arquivos = [p for p in self._folder.iterdir() if _NOME_B3.match(p.name)]
                na_biblioteca = {f.name: f.imported_at for f in self._library.files()}
            except (OSError, DomainError):
                return ()
            novos = [e for p in arquivos if (e := self._tratar(p, na_biblioteca)) is not None]
            self._eventos.extend(novos)
            return tuple(novos)

    def _tratar(
        self, path: Path, na_biblioteca: dict[str, datetime]
    ) -> ImportacaoAutomatica | None:
        try:
            info = path.stat()
        except OSError:
            return None
        assinatura = (info.st_size, info.st_mtime)
        nome = path.name
        if self._tratados.get(nome) == assinatura:
            return None
        # Só importa o que não mudou desde a passada anterior: o download pode estar em curso.
        if self._vistos.get(nome) != assinatura:
            self._vistos[nome] = assinatura
            return None
        modificado = datetime.fromtimestamp(info.st_mtime, tz=UTC)
        importado_em = na_biblioteca.get(nome)
        if importado_em is not None and importado_em >= modificado:
            self._tratados[nome] = assinatura
            return None
        try:
            guardado = self._library.import_file(nome, path.read_bytes())
        except B3FileRejectedError as erro:
            self._tratados[nome] = assinatura
            return ImportacaoAutomatica(nome, self._clock.now(), False, str(erro))
        except (OSError, DomainError):
            return None  # em uso ou sumiu: tenta na próxima passada
        self._tratados[nome] = assinatura
        data = f", pregão de {guardado.reference_date:%d/%m/%Y}" if guardado.reference_date else ""
        detalhe = f"{_TIPOS[guardado.kind.value]}{data}"
        return ImportacaoAutomatica(nome, self._clock.now(), True, detalhe)

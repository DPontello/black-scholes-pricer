"""Biblioteca de arquivos da B3 — importa, valida, guarda e avisa quando o cadastro envelhece.

Layout em ``root``: ``cotahist/``, ``cadastro/`` e ``biblioteca.json`` (o
índice: tipo, data de referência e instante de importação de cada arquivo —
o COTAHIST anual é grande demais para reler a cada consulta). Reimportar o
mesmo nome substitui o arquivo. O que está na pasta mas não no índice é
ignorado, e o arquivo apagado à mão some da biblioteca.

O tipo vem do CONTEÚDO, nunca do nome nem da extensão: o usuário (pouco
técnico) arrasta o que baixou, e a recusa de arquivo errado tem que ser clara.
O arquivo é validado por inteiro (``parse_cotahist`` / ``load_instruments``)
num diretório temporário ANTES de tocar em ``root``: o que é recusado não
deixa arquivo, pasta de tipo nem entrada no índice.

O nome do arquivo é dado externo (vem da requisição): só entra como nome-base
dentro de ``root/<tipo>/``; separadores, ``:`` (letra de unidade no Windows),
``..`` e nome vazio são recusados, para nunca gravar fora de ``root``.
"""

import contextlib
import csv
import io
import json
import os
import re
import tempfile
import threading
import zipfile
import zlib
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.cotahist.errors import SourceFileError
from options_engine.adapters.outbound.cotahist.instruments import load_instruments
from options_engine.adapters.outbound.cotahist.parser import parse_cotahist
from options_engine.adapters.outbound.storage.json_files import write_json_atomic
from options_engine.application.ports.outbound import CadastroFreshness, Clock, TradingCalendar
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "STALE_CADASTRO_BUSINESS_DAYS",
    "B3FileKind",
    "B3FileLibrary",
    "B3FileRejectedError",
    "CadastroFreshness",
    "ImportedFile",
    "cadastro_freshness",
]

# Cadastro com mais dias úteis que isto, desde a data de referência, está velho.
STALE_CADASTRO_BUSINESS_DAYS: Final = 5

_INDEX_FILE: Final = "biblioteca.json"
_SCHEMA_VERSION: Final = 1
_MAX_NAME_LENGTH: Final = 200
_COTAHIST_SIGNATURE: Final = b"00COTAHIST"
_CADASTRO_COLUMNS: Final = ("TckrSymb", "OptnStyle")
# O cabeçalho do cadastro vem depois de poucas linhas de preâmbulo.
_CADASTRO_HEAD_BYTES: Final = 16 * 1024
_DATE_IN_NAME: Final = re.compile(r"_(\d{8})(?!\d)")


class B3FileKind(Enum):
    COTAHIST = "cotahist"
    CADASTRO = "cadastro"


@dataclass(frozen=True, slots=True)
class ImportedFile:
    """Arquivo guardado na biblioteca.

    COTAHIST: ``reference_date`` é o maior pregão do arquivo e ``first_date``
    o menor (a faixa que a biblioteca cobre). CADASTRO: ``reference_date`` é
    o ``_AAAAMMDD`` do nome (``None`` se não houver) e ``first_date`` é ``None``.
    """

    kind: B3FileKind
    name: str
    reference_date: date | None
    first_date: date | None
    imported_at: datetime
    path: Path


class B3FileRejectedError(Exception):
    """Arquivo arrastado que a biblioteca recusou — a mensagem diz o motivo ao usuário.

    Erro de ARQUIVO do adapter, fora do catálogo de domínio (como os
    ``SourceFileError``): nasce de um download manual errado, não de regra
    de negócio. A mensagem já vem em português e sem caminho temporário.
    """


class B3FileLibrary:
    """Biblioteca de arquivos da B3 sob ``root``; o ``clock`` carimba a importação."""

    def __init__(self, root: Path, clock: Clock) -> None:
        self._root = root
        self._clock = clock
        # Os endpoints rodam no threadpool e o usuário pode arrastar o COTAHIST e o
        # cadastro juntos: ler-alterar-gravar o índice sem trava perderia uma entrada.
        self._lock = threading.Lock()

    def import_file(self, name: str, content: bytes) -> ImportedFile:
        """Identifica pelo conteúdo, valida por inteiro e só então guarda; senão recusa."""
        nome = _safe_name(name)
        if not content:
            raise B3FileRejectedError(
                f"O arquivo '{nome}' está vazio. Baixe-o de novo no site da B3. Nada foi guardado."
            )
        kind = _identify(content)
        if kind is None:
            raise B3FileRejectedError(
                f"O arquivo '{nome}' foi recusado: tipo de arquivo não reconhecido. "
                "Arraste o COTAHIST (.zip ou .txt) ou o Cadastro de Instrumentos (.csv) "
                "baixados do site da B3. Nada foi guardado."
            )
        reference_date, first_date = _validate(kind, nome, content)
        with self._lock:
            entries = self._read_entries()  # índice ilegível falha ANTES de gravar qualquer coisa
            path = self._store(kind, nome, content)
            imported = ImportedFile(kind, nome, reference_date, first_date, self._clock.now(), path)
            kept = tuple(e for e in entries if (e.kind, e.name) != (kind, nome))
            self._write_entries((*kept, imported))
        return imported

    def files(self) -> tuple[ImportedFile, ...]:
        """Arquivos da biblioteca que ainda existem em disco, por tipo e depois por nome."""
        presentes = (e for e in self._read_entries() if e.path.is_file())
        return tuple(sorted(presentes, key=lambda e: (e.kind.value, e.name)))

    def latest_cadastro(self) -> ImportedFile | None:
        """Cadastro de data de referência mais recente; sem data no nome, só se não houver outro."""
        cadastros = [f for f in self.files() if f.kind is B3FileKind.CADASTRO]
        return max(cadastros, key=_recency, default=None)

    def cotahist_paths(self) -> tuple[Path, ...]:
        """Caminhos dos COTAHIST, do pregão mais antigo para o mais novo."""
        cotahists = [f for f in self.files() if f.kind is B3FileKind.COTAHIST]
        cotahists.sort(key=lambda f: (f.reference_date or date.min, f.name))
        return tuple(f.path for f in cotahists)

    # --- armazenamento ------------------------------------------------------------------------

    def _store(self, kind: B3FileKind, nome: str, content: bytes) -> Path:
        pasta = self._root / kind.value
        pasta.mkdir(parents=True, exist_ok=True)
        destino = pasta / nome
        temporario = destino.with_name(destino.name + ".tmp")
        try:
            temporario.write_bytes(content)
            os.replace(temporario, destino)
        except BaseException:
            with contextlib.suppress(OSError):
                temporario.unlink(missing_ok=True)
            raise
        return destino

    def _read_entries(self) -> tuple[ImportedFile, ...]:
        index_path = self._root / _INDEX_FILE
        try:
            data = _read_index(index_path)
        except FileNotFoundError:
            return ()
        itens = data.get("arquivos")
        if data.get("versao") != _SCHEMA_VERSION or not isinstance(itens, list):
            raise _invalid_index(index_path, "versão desconhecida ou campo 'arquivos' ausente")
        try:
            return tuple(self._entry_from_json(item) for item in itens)
        except (KeyError, TypeError, ValueError) as erro:
            raise _invalid_index(index_path, f"entrada malformada ({erro!r})") from erro

    def _entry_from_json(self, item: dict[str, object]) -> ImportedFile:
        kind = B3FileKind(item["tipo"])
        nome = item["nome"]
        imported_at = datetime.fromisoformat(str(item["importado_em"]))
        if not isinstance(nome, str) or imported_at.tzinfo is None:
            raise ValueError(f"nome ou instante inválido em {item!r}")
        return ImportedFile(
            kind,
            nome,
            _optional_date(item["data"]),
            _optional_date(item["primeira_data"]),
            imported_at,
            self._root / kind.value / nome,
        )

    def _write_entries(self, entries: tuple[ImportedFile, ...]) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            self._root / _INDEX_FILE,
            {
                "versao": _SCHEMA_VERSION,
                "arquivos": [
                    {
                        "tipo": e.kind.value,
                        "nome": e.name,
                        "data": _iso_or_none(e.reference_date),
                        "primeira_data": _iso_or_none(e.first_date),
                        "importado_em": e.imported_at.isoformat(),
                    }
                    for e in entries
                ],
            },
        )


def cadastro_freshness(
    library: B3FileLibrary, calendar: TradingCalendar, today: date
) -> CadastroFreshness | None:
    """Idade do cadastro mais recente em dias úteis; ``None`` sem cadastro ou sem data nele.

    Sem data de referência não há idade a medir (e chutar "novo" esconderia um
    cadastro velho). Referência no futuro conta 0 dia.
    """
    latest = library.latest_cadastro()
    if latest is None or latest.reference_date is None:
        return None
    reference = latest.reference_date
    business_days = calendar.business_days_between(reference, today) if reference < today else 0
    return CadastroFreshness(reference, business_days, business_days > STALE_CADASTRO_BUSINESS_DAYS)


# --- nome e identificação -----------------------------------------------------------------------


def _safe_name(name: str) -> str:
    """Nome-base seguro para gravar dentro de ``root/<tipo>/``; recusa o que poderia escapar."""
    nome = name.strip()
    if not nome.strip("."):  # vazio, "." ou ".."
        raise B3FileRejectedError("O nome do arquivo está vazio ou é inválido. Nada foi guardado.")
    if len(nome) > _MAX_NAME_LENGTH:
        raise B3FileRejectedError(
            f"O nome do arquivo passa de {_MAX_NAME_LENGTH} caracteres. Nada foi guardado."
        )
    if any(c in "/\\:" or not c.isprintable() for c in nome):
        raise B3FileRejectedError(
            f"O nome do arquivo '{nome}' tem caractere não permitido "
            "(pasta, barra, dois-pontos ou caractere de controle). Nada foi guardado."
        )
    return nome


def _identify(content: bytes) -> B3FileKind | None:
    if zipfile.is_zipfile(io.BytesIO(content)):
        return B3FileKind.COTAHIST if _zip_holds_cotahist(content) else None
    if content.startswith(_COTAHIST_SIGNATURE):
        return B3FileKind.COTAHIST
    if _has_cadastro_header(content):
        return B3FileKind.CADASTRO
    return None


def _zip_holds_cotahist(content: bytes) -> bool:
    """ZIP com um único ``.TXT`` que começa com ``00COTAHIST`` (o que o parser exige)."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zip_file:
            membros = [m for m in zip_file.namelist() if m.upper().endswith(".TXT")]
            if len(membros) != 1:
                return False
            with zip_file.open(membros[0]) as membro:
                return membro.read(len(_COTAHIST_SIGNATURE)) == _COTAHIST_SIGNATURE
    except (zipfile.BadZipFile, NotImplementedError, RuntimeError, zlib.error, EOFError):
        # Corrompido, compressão que o Python não lê ou protegido por senha.
        return False


def _has_cadastro_header(content: bytes) -> bool:
    # ``replace``: o corte pode cair no meio de um caractere; as colunas são ASCII.
    head = content[:_CADASTRO_HEAD_BYTES].decode("utf-8", errors="replace")
    return any(all(c in linha for c in _CADASTRO_COLUMNS) for linha in head.splitlines())


# --- validação ----------------------------------------------------------------------------------

_LABEL: Final[dict[B3FileKind, str]] = {
    B3FileKind.COTAHIST: "um COTAHIST",
    B3FileKind.CADASTRO: "um Cadastro de Instrumentos",
}


def _validate(kind: B3FileKind, nome: str, content: bytes) -> tuple[date | None, date | None]:
    """``(reference_date, first_date)`` do arquivo, validado por inteiro fora de ``root``."""
    rotulo = _LABEL[kind]
    validar = _validate_cotahist if kind is B3FileKind.COTAHIST else _validate_cadastro
    with tempfile.TemporaryDirectory(prefix="painel-opcoes-") as temporario:
        caminho = Path(temporario) / nome
        caminho.write_bytes(content)
        try:
            return validar(caminho, nome)
        except (SourceFileError, csv.Error, zlib.error, EOFError) as erro:
            raise B3FileRejectedError(
                f"O arquivo '{nome}' parece {rotulo}, mas está incompleto, danificado ou "
                f"fora do formato ({_detail(erro, caminho, nome)}). "
                "Baixe-o de novo no site da B3. Nada foi guardado."
            ) from erro


def _detail(erro: Exception, caminho: Path, nome: str) -> str:
    """Motivo do parser com o caminho temporário trocado pelo nome que o usuário arrastou."""
    return (
        nome + str(erro).removeprefix(str(caminho))
        if isinstance(erro, SourceFileError)
        else str(erro)
    )


def _validate_cotahist(caminho: Path, nome: str) -> tuple[date | None, date | None]:
    registros = parse_cotahist(caminho)
    if not registros:
        raise B3FileRejectedError(
            f"O arquivo '{nome}' é um COTAHIST, mas não traz nenhum registro de ação ou de "
            "opção (mercados à vista, de compra e de venda). Nada foi guardado."
        )
    pregoes = [r.session for r in registros]
    return max(pregoes), min(pregoes)


def _validate_cadastro(caminho: Path, nome: str) -> tuple[date | None, date | None]:
    if not load_instruments(caminho):
        raise B3FileRejectedError(
            f"O arquivo '{nome}' é um Cadastro de Instrumentos, mas não traz nenhum instrumento. "
            "Nada foi guardado."
        )
    return _date_in_name(nome), None


def _date_in_name(nome: str) -> date | None:
    achado = _DATE_IN_NAME.search(nome)
    if achado is None:
        return None
    texto = achado.group(1)
    try:
        return date(int(texto[0:4]), int(texto[4:6]), int(texto[6:8]))
    except ValueError:
        return None


# --- índice -------------------------------------------------------------------------------------


def _recency(arquivo: ImportedFile) -> tuple[bool, date, datetime]:
    data = arquivo.reference_date
    return data is not None, data or date.min, arquivo.imported_at


def _iso_or_none(valor: date | None) -> str | None:
    return None if valor is None else valor.isoformat()


def _optional_date(valor: object) -> date | None:
    return None if valor is None else date.fromisoformat(str(valor))


def _invalid_index(path: Path, reason: str) -> InvalidDomainValueError:
    return InvalidDomainValueError(f"arquivo {path} inválido: {reason}")


def _read_index(path: Path) -> dict[str, object]:
    """Objeto JSON do índice; ``FileNotFoundError`` sobe para o chamador decidir."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as erro:  # JSONDecodeError e UnicodeDecodeError
        raise _invalid_index(path, f"JSON ilegível ({erro})") from erro
    if not isinstance(data, dict):
        raise _invalid_index(path, "esperava um objeto JSON")
    return data

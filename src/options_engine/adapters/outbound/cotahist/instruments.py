"""Cadastro de Instrumentos da B3 — fonte OBRIGATÓRIA do estilo de exercício (ADR-0006).

CSV ``InstrumentsConsolidatedFile_*.csv``, baixado manualmente com o COTAHIST
do mesmo pregão. Leitura tolerante ao que o arquivo real costuma trazer:
linhas de preâmbulo antes do cabeçalho, delimitador ``;`` ou ``,`` e
encoding ``utf-8-sig`` ou ``cp1252``. O cabeçalho é a primeira linha que,
partida por um dos delimitadores, contém as colunas ``TckrSymb`` e
``OptnStyle``.

``OptnStyle`` é mapeado por prefixo, sem distinguir maiúsculas: ``AMER*`` ->
AMERICAN, ``EURO*`` -> EUROPEAN; vazio ou outro valor -> estilo
desconhecido (``None``), e a série fica fora do painel com motivo. O domínio
exato do campo não está no glossário da B3 — premissa a conferir com um
arquivo real. Nunca se assume EUROPEAN por omissão.

``UndrlygTckrSymb1`` (opcional): quando preenchido, é o ativo-objeto da série
e prevalece sobre a regra de raiz do ticker na montagem da cadeia.
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.cotahist.errors import InstrumentsFileError
from options_engine.domain.model.enums import ExerciseStyle

__all__ = ["InstrumentInfo", "load_instruments"]

_ENCODINGS: Final = ("utf-8-sig", "cp1252")
_DELIMITERS: Final = (";", ",")
_SYMBOL: Final = "TckrSymb"
_STYLE: Final = "OptnStyle"
_UNDERLYING: Final = "UndrlygTckrSymb1"


@dataclass(frozen=True, slots=True)
class InstrumentInfo:
    """O que o painel usa do cadastro: estilo (``None`` = desconhecido) e ativo-objeto."""

    symbol: str
    exercise_style: ExerciseStyle | None
    underlying_symbol: str | None


def _estilo(bruto: str) -> ExerciseStyle | None:
    valor = bruto.strip().upper()
    if valor.startswith("AMER"):
        return ExerciseStyle.AMERICAN
    if valor.startswith("EURO"):
        return ExerciseStyle.EUROPEAN
    return None


def _decodificar(path: Path) -> str:
    try:
        bruto = path.read_bytes()
    except OSError as excecao:
        raise InstrumentsFileError(
            path, None, f"não foi possível ler o arquivo: {excecao}"
        ) from excecao
    for encoding in _ENCODINGS:
        try:
            return bruto.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InstrumentsFileError(path, None, f"encoding fora de {_ENCODINGS!r}")


def _cabecalho(path: Path, linhas: list[str]) -> tuple[int, str, list[str]]:
    """(índice da linha, delimitador, colunas) do primeiro cabeçalho reconhecível."""
    for indice, linha in enumerate(linhas):
        for delimitador in _DELIMITERS:
            colunas = [c.strip() for c in next(csv.reader([linha], delimiter=delimitador), [])]
            if _SYMBOL in colunas and _STYLE in colunas:
                return indice, delimitador, colunas
    raise InstrumentsFileError(
        path, None, f"cabeçalho com as colunas {_SYMBOL!r} e {_STYLE!r} não encontrado"
    )


def load_instruments(path: Path) -> dict[str, InstrumentInfo]:
    """Instrumentos do cadastro indexados pelo ticker.

    Ticker repetido com estilos divergentes vira estilo desconhecido: entre
    dois valores contraditórios da fonte, nenhum é escolhido em silêncio.
    """
    linhas = _decodificar(path).splitlines()
    indice, delimitador, colunas = _cabecalho(path, linhas)
    i_simbolo = colunas.index(_SYMBOL)
    i_estilo = colunas.index(_STYLE)
    i_objeto = colunas.index(_UNDERLYING) if _UNDERLYING in colunas else None
    instrumentos: dict[str, InstrumentInfo] = {}
    for celulas in csv.reader(linhas[indice + 1 :], delimiter=delimitador):
        if len(celulas) <= max(i_simbolo, i_estilo):
            continue
        simbolo = celulas[i_simbolo].strip()
        if not simbolo:
            continue
        objeto = None
        if i_objeto is not None and i_objeto < len(celulas):
            objeto = celulas[i_objeto].strip() or None
        info = InstrumentInfo(simbolo, _estilo(celulas[i_estilo]), objeto)
        anterior = instrumentos.get(simbolo)
        if anterior is not None and anterior != info:
            info = InstrumentInfo(simbolo, None, None)
        instrumentos[simbolo] = info
    return instrumentos

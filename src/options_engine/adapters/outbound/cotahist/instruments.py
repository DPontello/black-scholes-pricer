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
e prevalece sobre a regra de raiz do ticker na montagem da cadeia. Vazio numa
opção, vale o ``Asst`` quando ele é um ticker: no Cadastro real de 28/10/2026 a
coluna própria vem vazia em todas as opções, e o ``Asst`` traz ``PETR4`` na
opção e só a raiz ``PETR`` no à vista.

``OptnTp``, ``ExrcPric`` e ``XprtnDt`` (opcionais): tipo, strike e vencimento
da série, para quem monta o universo de séries a partir do cadastro. Leitura
tolerante: ``OptnTp`` por prefixo, sem distinguir maiúsculas (``CALL*`` ->
CALL, ``PUT*`` -> PUT); ``ExrcPric`` com ``.`` ou ``,`` decimal, só valores
finitos e > 0; ``XprtnDt`` em ``AAAA-MM-DD`` ou ``DD/MM/AAAA``. Coluna
ausente, vazia ou ilegível -> ``None``, nunca um valor presumido. Os nomes
das colunas e o domínio de ``OptnTp`` são premissas a conferir com um arquivo
real.
"""

import csv
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.cotahist.errors import InstrumentsFileError
from options_engine.domain.model.enums import ExerciseStyle, OptionType

__all__ = ["InstrumentInfo", "load_instruments", "raw_rows"]

_ENCODINGS: Final = ("utf-8-sig", "cp1252")
_DELIMITERS: Final = (";", ",")
_SYMBOL: Final = "TckrSymb"
_STYLE: Final = "OptnStyle"
_UNDERLYING: Final = "UndrlygTckrSymb1"
_ASSET: Final = "Asst"
_TICKER: Final = re.compile(r"[A-Z0-9]{4}\d{1,2}")  # B3SA3 e BDR (M1TA34) têm dígito na raiz
_OPTION_TYPE: Final = "OptnTp"
_STRIKE: Final = "ExrcPric"
_EXPIRY: Final = "XprtnDt"
_DATE_FORMATS: Final = ("%Y-%m-%d", "%d/%m/%Y")


@dataclass(frozen=True, slots=True)
class InstrumentInfo:
    """O que o painel usa do cadastro: estilo (``None`` = desconhecido), ativo-objeto e termos.

    ``option_type``, ``strike`` e ``expiry`` (os termos da série) são ``None``
    quando a coluna falta ou o valor é ilegível.
    """

    symbol: str
    exercise_style: ExerciseStyle | None
    underlying_symbol: str | None
    option_type: OptionType | None = None
    strike: float | None = None
    expiry: date | None = None


def _estilo(bruto: str) -> ExerciseStyle | None:
    valor = bruto.strip().upper()
    if valor.startswith("AMER"):
        return ExerciseStyle.AMERICAN
    if valor.startswith("EURO"):
        return ExerciseStyle.EUROPEAN
    return None


def _tipo(bruto: str) -> OptionType | None:
    valor = bruto.strip().upper()
    if valor.startswith("CALL"):
        return OptionType.CALL
    if valor.startswith("PUT"):
        return OptionType.PUT
    return None


def _strike(bruto: str) -> float | None:
    try:
        valor = float(bruto.strip().replace(",", "."))
    except ValueError:
        return None
    # `not (x > 0)` em vez de `x <= 0`: NaN compara False com tudo e também cai fora.
    if not math.isfinite(valor) or not valor > 0.0:
        return None
    return valor


def _vencimento(bruto: str) -> date | None:
    for formato in _DATE_FORMATS:
        try:
            return datetime.strptime(bruto.strip(), formato).date()
        except ValueError:
            continue
    return None


def _celula(celulas: list[str], indice: int | None) -> str:
    """Texto da coluna opcional; vazio quando a coluna não existe ou a linha é curta."""
    if indice is None or indice >= len(celulas):
        return ""
    return celulas[indice]


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


def raw_rows(path: Path) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    """Cabeçalho e células sem interpretação (para diagnóstico)."""
    linhas = _decodificar(path).splitlines()
    indice, delimitador, colunas = _cabecalho(path, linhas)
    corpo = csv.reader(linhas[indice + 1 :], delimiter=delimitador)
    return tuple(colunas), tuple(tuple(c.strip() for c in celulas) for celulas in corpo if celulas)


def load_instruments(path: Path) -> dict[str, InstrumentInfo]:
    """Instrumentos do cadastro indexados pelo ticker.

    Ticker repetido com estilos divergentes vira estilo desconhecido: entre
    dois valores contraditórios da fonte, nenhum é escolhido em silêncio. O
    mesmo vale para tipo, strike e vencimento: duplicata contraditória zera
    todos os campos opcionais.
    """
    linhas = _decodificar(path).splitlines()
    indice, delimitador, colunas = _cabecalho(path, linhas)
    i_simbolo = colunas.index(_SYMBOL)
    i_estilo = colunas.index(_STYLE)
    i_objeto = colunas.index(_UNDERLYING) if _UNDERLYING in colunas else None
    i_ativo = colunas.index(_ASSET) if _ASSET in colunas else None
    i_tipo = colunas.index(_OPTION_TYPE) if _OPTION_TYPE in colunas else None
    i_strike = colunas.index(_STRIKE) if _STRIKE in colunas else None
    i_vencimento = colunas.index(_EXPIRY) if _EXPIRY in colunas else None
    instrumentos: dict[str, InstrumentInfo] = {}
    for celulas in csv.reader(linhas[indice + 1 :], delimiter=delimitador):
        if len(celulas) <= max(i_simbolo, i_estilo):
            continue
        simbolo = celulas[i_simbolo].strip()
        if not simbolo:
            continue
        tipo = _tipo(_celula(celulas, i_tipo))
        objeto = _celula(celulas, i_objeto).strip() or None
        if objeto is None and tipo is not None:
            ativo = _celula(celulas, i_ativo).strip()
            objeto = ativo if _TICKER.fullmatch(ativo) else None
        info = InstrumentInfo(
            simbolo,
            _estilo(celulas[i_estilo]),
            objeto,
            option_type=tipo,
            strike=_strike(_celula(celulas, i_strike)),
            expiry=_vencimento(_celula(celulas, i_vencimento)),
        )
        anterior = instrumentos.get(simbolo)
        if anterior is not None and anterior != info:
            info = InstrumentInfo(simbolo, None, None)
        instrumentos[simbolo] = info
    return instrumentos

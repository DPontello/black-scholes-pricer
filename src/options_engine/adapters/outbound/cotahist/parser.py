"""Parser do COTAHIST da B3 — séries históricas em largura fixa (ADR-0006).

Layout (documento "SeriesHistoricas_Layout" da B3; posições 1-based
inclusivas, registros de 245 caracteres, encoding cp1252):

- header ``00``, registros de cotação ``01`` e trailer ``99``; o trailer
  traz em TOTREG (32-42) o total de registros do arquivo, CONTANDO header e
  trailer — premissa a conferir no primeiro arquivo real;
- campos usados: DATPRE 3-10, CODBDI 11-12, CODNEG 13-24, TPMERC 25-27,
  NOMRES 28-39, ESPECI 40-49, PREULT 109-121, PREOFC 122-134,
  PREOFV 135-147, TOTNEG 148-152, QUATOT 153-170, VOLTOT 171-188,
  PREEXE 189-201, INDOPC 202, DATVEN 203-210, FATCOT 211-217;
- preços (11)V99 com 2 decimais implícitas e cotados por FATCOT unidades:
  TODO campo de preço, inclusive PREEXE, é dividido por FATCOT; VOLTOT
  (16)V99 é volume financeiro em reais e NÃO é dividido.

Só os mercados que o painel usa saem do parser: TPMERC 010 (à vista, o
ativo-objeto), 070 (call) e 080 (put). Os demais registros têm o tamanho e o
tipo validados e são descartados. Zero da fonte segue zero aqui: a tradução
"zero → ``None``" (ADR-0003) é da montagem da cadeia.
"""

import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.cotahist.errors import CotahistFormatError

__all__ = [
    "MARKET_CALL",
    "MARKET_PUT",
    "MARKET_SPOT",
    "RECORD_LENGTH",
    "CotahistRecord",
    "parse_cotahist",
]

RECORD_LENGTH: Final = 245
ENCODING: Final = "cp1252"
MARKET_SPOT: Final = 10
MARKET_CALL: Final = 70
MARKET_PUT: Final = 80
_MARKETS: Final = frozenset({MARKET_SPOT, MARKET_CALL, MARKET_PUT})


@dataclass(frozen=True, slots=True)
class CotahistRecord:
    """Um registro ``01`` de mercado à vista, call ou put, já em unidades finais.

    Preços em reais por unidade (divididos por ``quote_factor``); ``volume``
    é o financeiro do pregão em reais; zero da fonte permanece ``0.0``.
    ``expiry`` é DATVEN (9999-12-31 no à vista).
    """

    session: date
    bdi_code: str
    symbol: str
    market: int
    short_name: str
    specification: str
    last: float
    best_bid: float
    best_ask: float
    trades: int
    quantity: int
    volume: float
    strike: float
    strike_correction: int
    expiry: date
    quote_factor: int


def _campo(linha: str, inicio: int, fim: int) -> str:
    """Fatia 1-based inclusiva, como no documento de layout."""
    return linha[inicio - 1 : fim]


def _inteiro(path: Path, numero: int, linha: str, nome: str, inicio: int, fim: int) -> int:
    bruto = _campo(linha, inicio, fim)
    # isascii: str.isdigit aceita dígitos Unicode como "²" (cp1252 0xB2), que int() recusa.
    if not (bruto.isascii() and bruto.strip().isdigit()):
        raise CotahistFormatError(
            path, numero, f"campo {nome} ({inicio}-{fim}) não numérico: {bruto!r}"
        )
    return int(bruto)


def _data(path: Path, numero: int, linha: str, nome: str, inicio: int) -> date:
    bruto = _campo(linha, inicio, inicio + 7)
    try:
        return date(int(bruto[0:4]), int(bruto[4:6]), int(bruto[6:8]))
    except ValueError as excecao:
        raise CotahistFormatError(
            path, numero, f"campo {nome} ({inicio}-{inicio + 7}) não é data AAAAMMDD: {bruto!r}"
        ) from excecao


def _registro(path: Path, numero: int, linha: str) -> CotahistRecord | None:
    mercado = _inteiro(path, numero, linha, "TPMERC", 25, 27)
    if mercado not in _MARKETS:
        return None
    fator = _inteiro(path, numero, linha, "FATCOT", 211, 217)
    if fator == 0:
        raise CotahistFormatError(path, numero, "FATCOT zero: preços sem fator de cotação")

    def preco(nome: str, inicio: int, fim: int) -> float:
        return _inteiro(path, numero, linha, nome, inicio, fim) / 100.0 / fator

    return CotahistRecord(
        session=_data(path, numero, linha, "DATPRE", 3),
        bdi_code=_campo(linha, 11, 12).strip(),
        symbol=_campo(linha, 13, 24).strip(),
        market=mercado,
        short_name=_campo(linha, 28, 39).strip(),
        specification=_campo(linha, 40, 49).strip(),
        last=preco("PREULT", 109, 121),
        best_bid=preco("PREOFC", 122, 134),
        best_ask=preco("PREOFV", 135, 147),
        trades=_inteiro(path, numero, linha, "TOTNEG", 148, 152),
        quantity=_inteiro(path, numero, linha, "QUATOT", 153, 170),
        volume=_inteiro(path, numero, linha, "VOLTOT", 171, 188) / 100.0,
        strike=preco("PREEXE", 189, 201),
        strike_correction=_inteiro(path, numero, linha, "INDOPC", 202, 202),
        expiry=_data(path, numero, linha, "DATVEN", 203),
        quote_factor=fator,
    )


def _texto(path: Path) -> str:
    """Conteúdo do .TXT, ou do único membro .TXT de um .ZIP, decodificado em cp1252."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as arquivo:
                membros = [m for m in arquivo.namelist() if m.upper().endswith(".TXT")]
                if len(membros) != 1:
                    raise CotahistFormatError(
                        path, None, f"ZIP deve ter exatamente um membro .TXT; tem {membros!r}"
                    )
                bruto = arquivo.read(membros[0])
        else:
            bruto = path.read_bytes()
    except zipfile.BadZipFile as excecao:
        raise CotahistFormatError(path, None, f"ZIP corrompido: {excecao}") from excecao
    try:
        return bruto.decode(ENCODING)
    except UnicodeDecodeError as excecao:
        raise CotahistFormatError(path, None, f"bytes fora do {ENCODING}: {excecao}") from excecao


def _linhas(texto: str) -> Iterator[tuple[int, str]]:
    """Linhas numeradas a partir de 1, aceitando ``\\r\\n`` ou ``\\n``."""
    for numero, linha in enumerate(texto.split("\n"), start=1):
        sem_cr = linha.removesuffix("\r")
        if sem_cr:
            yield numero, sem_cr


def parse_cotahist(path: Path) -> tuple[CotahistRecord, ...]:
    """Registros de à vista, call e put de um COTAHIST (.TXT ou .ZIP).

    Qualquer desvio de layout — linha com tamanho diferente de 245, campo
    numérico ou data inválidos, header ausente, arquivo truncado (sem
    trailer) ou trailer com total divergente — levanta
    ``CotahistFormatError`` com o caminho e o número da linha.
    """
    linhas = list(_linhas(_texto(path)))
    if not linhas:
        raise CotahistFormatError(path, None, "arquivo vazio")
    for numero, linha in linhas:
        if len(linha) != RECORD_LENGTH:
            raise CotahistFormatError(
                path,
                numero,
                f"registro com {len(linha)} caracteres; o layout exige {RECORD_LENGTH}",
            )
    numero_header, header = linhas[0]
    if header[:2] != "00":
        raise CotahistFormatError(path, numero_header, f"header ausente: tipo {header[:2]!r}")
    numero_trailer, trailer = linhas[-1]
    if trailer[:2] != "99":
        raise CotahistFormatError(
            path,
            numero_trailer,
            f"arquivo truncado: último registro é {trailer[:2]!r}, não o trailer 99",
        )
    declarados = _inteiro(path, numero_trailer, trailer, "TOTREG", 32, 42)
    if declarados != len(linhas):
        raise CotahistFormatError(
            path,
            numero_trailer,
            f"trailer declara {declarados} registros; o arquivo tem {len(linhas)}",
        )
    registros: list[CotahistRecord] = []
    for numero, linha in linhas[1:-1]:
        if linha[:2] != "01":
            raise CotahistFormatError(path, numero, f"tipo de registro inesperado {linha[:2]!r}")
        registro = _registro(path, numero, linha)
        if registro is not None:
            registros.append(registro)
    return tuple(registros)

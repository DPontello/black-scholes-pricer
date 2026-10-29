"""Parser do COTAHIST da B3 — séries históricas em largura fixa (ADR-0006).

Layout (documento "SeriesHistoricas_Layout" da B3; posições 1-based
inclusivas, registros de 245 caracteres, encoding cp1252):

- header ``00``, registros de cotação ``01`` e trailer ``99``; o trailer
  traz em TOTREG (32-42) o total de registros ``01``, SEM header e trailer.
  O layout diz que conta os dois, mas o anual e o diário reais de 28/10/2026
  não contam;
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
import zlib
from collections.abc import Callable, Iterator
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
    "cotahist_sessions",
    "iter_cotahist",
    "parse_cotahist",
    "raw_lines",
]

RECORD_LENGTH: Final = 245
ENCODING: Final = "cp1252"
MARKET_SPOT: Final = 10
MARKET_CALL: Final = 70
MARKET_PUT: Final = 80
_MARKETS: Final = frozenset({MARKET_SPOT, MARKET_CALL, MARKET_PUT})
_MERCADO_DE: Final = {b"010": MARKET_SPOT, b"070": MARKET_CALL, b"080": MARKET_PUT}
_BLOCO: Final = 1 << 22

Escolha = Callable[[date, int], bool]


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


def _data_nova(datas: dict[bytes, date], bruto: bytes) -> date | None:
    try:
        data = date(int(bruto[0:4]), int(bruto[4:6]), int(bruto[6:8]))
    except ValueError:
        return None
    datas[bruto] = data
    return data


def _lento(path: Path, numero: int, linha: bytes, keep: Escolha | None) -> CotahistRecord | None:
    registro = _registro(path, numero, linha.decode(ENCODING))
    if registro is None or (keep is not None and not keep(registro.session, registro.market)):
        return None
    return registro


def _registro_rapido(
    path: Path, numero: int, linha: bytes, keep: Escolha | None, datas: dict[bytes, date]
) -> CotahistRecord | None:
    """O caso comum, com todos os campos numéricos usados preenchidos com dígitos.

    Qualquer outro vai para o caminho lento, que diz qual campo está errado. Os campos de
    PREULT a FATCOT (109-217) são contíguos: um ``isdigit`` valida todos.
    """
    if linha[:2] != b"01":
        tipo = linha[:2].decode(ENCODING)
        raise CotahistFormatError(path, numero, f"tipo de registro inesperado {tipo!r}")
    if not (linha[2:10].isdigit() and linha[24:27].isdigit() and linha[108:217].isdigit()):
        return _lento(path, numero, linha, keep)
    mercado = _MERCADO_DE.get(linha[24:27])
    if mercado is None:
        return None
    pregao = datas.get(linha[2:10]) or _data_nova(datas, linha[2:10])
    vencimento = datas.get(linha[202:210]) or _data_nova(datas, linha[202:210])
    if pregao is None or vencimento is None or linha[210:217] == b"0000000":
        return _lento(path, numero, linha, keep)
    if keep is not None and not keep(pregao, mercado):
        return None
    fator = int(linha[210:217])
    return CotahistRecord(
        session=pregao,
        bdi_code=linha[10:12].decode(ENCODING).strip(),
        symbol=linha[12:24].decode(ENCODING).strip(),
        market=mercado,
        short_name=linha[27:39].decode(ENCODING).strip(),
        specification=linha[39:49].decode(ENCODING).strip(),
        last=int(linha[108:121]) / 100.0 / fator,
        best_bid=int(linha[121:134]) / 100.0 / fator,
        best_ask=int(linha[134:147]) / 100.0 / fator,
        trades=int(linha[147:152]),
        quantity=int(linha[152:170]),
        volume=int(linha[170:188]) / 100.0,
        strike=int(linha[188:201]) / 100.0 / fator,
        strike_correction=int(linha[201:202]),
        expiry=vencimento,
        quote_factor=fator,
    )


def _blocos(path: Path) -> Iterator[bytes]:
    """O .TXT, ou o único membro .TXT de um .ZIP, em blocos, sem carregar o arquivo inteiro."""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as arquivo:
                membros = [m for m in arquivo.namelist() if m.upper().endswith(".TXT")]
                if len(membros) != 1:
                    raise CotahistFormatError(
                        path, None, f"ZIP deve ter exatamente um membro .TXT; tem {membros!r}"
                    )
                with arquivo.open(membros[0]) as fluxo:
                    while bloco := fluxo.read(_BLOCO):
                        yield bloco
        else:
            with path.open("rb") as fluxo:
                while bloco := fluxo.read(_BLOCO):
                    yield bloco
    except (zipfile.BadZipFile, zlib.error, EOFError) as excecao:
        raise CotahistFormatError(path, None, f"ZIP corrompido: {excecao}") from excecao


def _normalizada(path: Path, numero: int, linha: bytes, exigir_tamanho: bool) -> bytes:
    """A linha em cp1252; a que só fecha o layout lida como UTF-8 é relida assim.

    O anual de 2026 real traz um nome em UTF-8 no meio do cp1252 (FR0T5L, "FROTA OCEÂNI").
    """
    if not linha.isascii():
        try:
            utf8: str | None = linha.decode("utf-8")
        except UnicodeDecodeError:
            utf8 = None
        if utf8 is not None and len(linha) != RECORD_LENGTH and len(utf8) == RECORD_LENGTH:
            return utf8.encode(ENCODING, errors="replace")
        try:
            linha.decode(ENCODING)
        except UnicodeDecodeError:
            raise CotahistFormatError(path, numero, f"bytes fora do {ENCODING}") from None
    if exigir_tamanho and len(linha) != RECORD_LENGTH:
        raise CotahistFormatError(
            path, numero, f"registro com {len(linha)} caracteres; o layout exige {RECORD_LENGTH}"
        )
    return linha


def _linhas(path: Path, *, exigir_tamanho: bool = True) -> Iterator[tuple[int, bytes]]:
    """Linhas não vazias, numeradas a partir de 1, aceitando ``\\r\\n`` ou ``\\n``."""
    numero = 0
    resto = b""
    for bloco in _blocos(path):
        partes = (resto + bloco).split(b"\n")
        resto = partes.pop()
        for parte in partes:
            numero += 1
            sem_cr = parte.removesuffix(b"\r")
            if len(sem_cr) == RECORD_LENGTH and sem_cr.isascii():
                yield numero, sem_cr
            elif sem_cr:
                yield numero, _normalizada(path, numero, sem_cr, exigir_tamanho)
    if sem_cr := resto.removesuffix(b"\r"):
        yield numero + 1, _normalizada(path, numero + 1, sem_cr, exigir_tamanho)


def raw_lines(path: Path) -> Iterator[tuple[int, str]]:
    """Linhas numeradas, em fluxo, sem validar o layout (para diagnóstico)."""
    for numero, linha in _linhas(path, exigir_tamanho=False):
        yield numero, linha.decode(ENCODING)


def iter_cotahist(path: Path, keep: Escolha | None = None) -> Iterator[CotahistRecord]:
    """Registros de à vista, call e put de um COTAHIST (.TXT ou .ZIP), lidos em fluxo.

    ``keep(pregão, mercado)`` escolhe quais viram registro; toda linha é validada do mesmo
    jeito. Qualquer desvio de layout (linha fora de 245 caracteres, campo numérico ou data
    inválidos, header ausente, arquivo truncado, trailer com total divergente) levanta
    ``CotahistFormatError`` com o caminho e o número da linha. Os erros do trailer só saem
    no fim: quem para de iterar no meio não validou o arquivo.
    """
    linhas = _linhas(path)
    primeira = next(linhas, None)
    if primeira is None:
        raise CotahistFormatError(path, None, "arquivo vazio")
    numero, header = primeira
    if header[:2] != b"00":
        tipo = header[:2].decode(ENCODING)
        raise CotahistFormatError(path, numero, f"header ausente: tipo {tipo!r}")
    anterior, contados = primeira, 0
    datas: dict[bytes, date] = {}
    for atual in linhas:
        if anterior is not primeira:
            contados += 1
            registro = _registro_rapido(path, *anterior, keep, datas)
            if registro is not None:
                yield registro
        anterior = atual
    numero, trailer = anterior
    if trailer[:2] != b"99":
        tipo = trailer[:2].decode(ENCODING)
        raise CotahistFormatError(
            path, numero, f"arquivo truncado: último registro é {tipo!r}, não o trailer 99"
        )
    declarados = _inteiro(path, numero, trailer.decode(ENCODING), "TOTREG", 32, 42)
    if declarados != contados:
        raise CotahistFormatError(
            path,
            numero,
            f"trailer declara {declarados} registros; o arquivo tem {contados} "
            "(sem header e trailer)",
        )


def parse_cotahist(path: Path) -> tuple[CotahistRecord, ...]:
    """Todos os registros de ``iter_cotahist``; para arquivos pequenos e testes."""
    return tuple(iter_cotahist(path))


def cotahist_sessions(path: Path) -> frozenset[date]:
    """Pregões dos registros de à vista, call e put, validando o arquivo sem guardá-los."""
    pregoes: set[date] = set()

    def anotar(pregao: date, _mercado: int) -> bool:
        pregoes.add(pregao)
        return False

    for _ in iter_cotahist(path, anotar):
        pass
    return frozenset(pregoes)

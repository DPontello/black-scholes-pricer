"""Peças de teste do mercado ao vivo, do fim de dia e do recuo: biblioteca, quadro e cliente falso.

A biblioteca é montada em ``tmp_path`` com a fixture sintética (``tests/data/cotahist``); o
cliente da ponte é uma subclasse que só registra ``ensure_subscribed`` e tem a saúde à mão —
nenhum socket, nenhuma thread, nada de Tryd.
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.client import BridgeHealth, TrydBridgeClient
from options_engine.adapters.outbound.tryd.feed import TrydMarketFeed
from options_engine.adapters.outbound.tryd.settings import LIMITE_TOPICOS
from options_ponte.protocolo import Valor
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME

__all__ = [
    "AGORA",
    "CDI",
    "FIXTURE",
    "SERIES_DE_PETR3",
    "ClienteFalso",
    "Montagem",
    "alimentar",
    "alimentar_assinados",
    "biblioteca",
    "cadastro_com_objetos",
    "cadastro_sem_objetos",
    "montar",
    "relogio",
]

FIXTURE: Final = Path(__file__).resolve().parents[1] / "data" / "cotahist"
CDI: Final = 0.15
# 28/10/2026, 12:00 no fuso da B3 (UTC-3): dentro do pregão, depois do último COTAHIST (23/10).
AGORA: Final = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
# Séries de PETR3 da fixture: o cadastro sintético não traz o ativo-objeto delas.
SERIES_DE_PETR3: Final = frozenset({"PETRK312", "PETRK322", "PETRK332"})
_JANEIRO: Final = date(2027, 1, 15)


def relogio() -> FixedClock:
    return FixedClock(AGORA)


def cadastro_com_objetos() -> bytes:
    """Cadastro da fixture com ``UndrlygTckrSymb1`` preenchido, e uma série de janeiro a mais.

    O cadastro sintético deixa o ativo-objeto em branco (para testar o desempate do COTAHIST
    entre PETR3 e PETR4, que compartilham a raiz). O cadastro real traz o ativo-objeto; aqui
    ele é preenchido para a cadeia ao vivo ter séries de PETR4 para mostrar. Janeiro de 2027 é
    o terceiro vencimento de PETR4: fora dos dois assinados por padrão.
    """
    texto = (FIXTURE / INSTRUMENTS_NAME).read_bytes().decode("utf-8-sig")
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    for linha in csv.reader(io.StringIO(texto), delimiter=";"):
        ticker = linha[0]
        if len(linha) == 7 and linha[5] and not linha[6]:  # série (OptnTp) sem ativo-objeto
            linha[6] = _objeto_da_serie(ticker)
        escritor.writerow(linha)
    for ticker, strike in (("PETRA300", "30.00"), ("PETRA350", "35.00")):
        escritor.writerow([ticker, "PETR", _JANEIRO.isoformat(), strike, "EURO", "CALL", "PETR4"])
    return saida.getvalue().encode("utf-8-sig")


def cadastro_sem_objetos() -> bytes:
    """Cadastro da fixture com ``UndrlygTckrSymb1`` em branco em TODAS as séries.

    Nenhuma série diz de quem é: com PETR3 e PETR4 dividindo a raiz, todas as de PETR são
    ambíguas para os dois ativos.
    """
    texto = (FIXTURE / INSTRUMENTS_NAME).read_bytes().decode("utf-8-sig")
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    for linha in csv.reader(io.StringIO(texto), delimiter=";"):
        if len(linha) == 7 and linha[5]:
            linha[6] = ""
        escritor.writerow(linha)
    return saida.getvalue().encode("utf-8-sig")


def _objeto_da_serie(ticker: str) -> str:
    if ticker in SERIES_DE_PETR3:
        return "PETR3"
    return "VALE3" if ticker.startswith("VALE") else "PETR4"


def biblioteca(
    raiz: Path,
    *,
    cadastro: bytes | None = None,
    com_cotahist: bool = True,
    com_cadastro: bool = True,
) -> B3FileLibrary:
    """Biblioteca em ``raiz`` com o COTAHIST e o cadastro da fixture (ou o cadastro dado)."""
    lib = B3FileLibrary(raiz, relogio())
    if com_cotahist:
        lib.import_file(COTAHIST_NAME, (FIXTURE / COTAHIST_NAME).read_bytes())
    if com_cadastro:
        lib.import_file(
            INSTRUMENTS_NAME,
            cadastro if cadastro is not None else (FIXTURE / INSTRUMENTS_NAME).read_bytes(),
        )
    return lib


class ClienteFalso(TrydBridgeClient):
    """Cliente da ponte sem rede: registra as assinaturas e deixa a saúde ao teste.

    ``ensure_subscribed`` ainda faz o que o cliente real faz no quadro (esquece e marca os
    ativos); só não há socket para enviar.
    """

    def __init__(self, board: LiveBoard, saude: BridgeHealth = BridgeHealth.CONECTADA) -> None:
        super().__init__(board)
        self.saude = saude
        self.assinaturas: list[frozenset[tuple[str, str]]] = []

    def ensure_subscribed(self, topics: frozenset[tuple[str, str]]) -> None:
        self.assinaturas.append(topics)
        super().ensure_subscribed(topics)

    def health(self) -> BridgeHealth:
        return self.saude

    @property
    def topicos(self) -> frozenset[tuple[str, str]]:
        """Os tópicos da assinatura mais recente (vazio se ninguém assinou)."""
        return self.assinaturas[-1] if self.assinaturas else frozenset()


def _tipo(valor: float | int | str | None) -> str:
    if valor is None:
        return "none"
    if isinstance(valor, str):
        return "str"
    return "int" if isinstance(valor, int) else "float"


def alimentar(board: LiveBoard, ticker: str, **campos: float | int | str | None) -> None:
    """Entrega ao quadro um ``Valor`` de verdade (não inicial) por campo; assina o ticker antes."""
    board.mark_subscribed([ticker])  # idempotente: quem já foi assinado segue como está
    for campo, valor in campos.items():
        board.apply(Valor(ticker, campo, _tipo(valor), valor, "2026-10-28T12:00:00-03:00"))


def alimentar_assinados(
    board: LiveBoard,
    topicos: frozenset[tuple[str, str]],
    valores: Callable[[str], dict[str, float | int | str | None]],
) -> None:
    """Alimenta cada ticker assinado com o que ``valores(ticker)`` devolver."""
    for ticker in sorted({ticker for ticker, _ in topicos}):
        alimentar(board, ticker, **valores(ticker))


@dataclass
class Montagem:
    """O feed e as peças que o teste mexe: quadro, cliente, CDI, relógio monotônico e biblioteca."""

    feed: TrydMarketFeed
    board: LiveBoard
    cliente: ClienteFalso
    biblioteca: B3FileLibrary
    cdi: list[float]
    tempo: list[float]


def montar(
    raiz: Path,
    *,
    cadastro: bytes | None = None,
    lib: B3FileLibrary | None = None,
    saude: BridgeHealth = BridgeHealth.CONECTADA,
    topic_limit: int = LIMITE_TOPICOS,
) -> Montagem:
    """Feed sobre quadro real e cliente falso; sem ``lib``, a biblioteca é a da fixture em ``raiz``.

    O cadastro padrão é ``cadastro_com_objetos`` (a cadeia ao vivo precisa do ativo-objeto).
    ``cdi`` e ``tempo`` são celas que o teste altera: o CDI do perfil e o relógio monotônico.
    """
    lib = lib or biblioteca(raiz / "mercado", cadastro=cadastro or cadastro_com_objetos())
    board = LiveBoard(lambda: 0.0)  # relógio parado: ``TEMPO_CARGA_S`` nunca vence sozinho
    cliente = ClienteFalso(board, saude)
    cdi = [CDI]
    tempo = [0.0]
    feed = TrydMarketFeed(
        cliente,
        board,
        lib,
        StaticHolidayCalendar.from_packaged_data(),
        relogio(),
        lambda: cdi[0],
        topic_limit=topic_limit,
        monotonic=lambda: tempo[0],
    )
    return Montagem(feed, board, cliente, lib, cdi, tempo)

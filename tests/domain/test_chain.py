"""Cadeia de opções (ADR-0003) — invariantes dos VOs da cotação e da cadeia."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, tzinfo

import pytest

from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.contracts import OptionContract
from options_engine.domain.model.errors import InvalidDomainValueError
from tests.domain._builders import make_contract

INSTANTE = datetime(2026, 10, 23, 18, 0, tzinfo=UTC)


def make_quote(
    contract: OptionContract | None = None,
    bid: float | None = 1.20,
    ask: float | None = 1.25,
    last: float | None = 1.22,
    trades: int = 37,
    volume: float = 52_800.0,
    timestamp: datetime = INSTANTE,
) -> OptionQuote:
    """Cotação VÁLIDA por default (book completo, com negócio no pregão)."""
    return OptionQuote(
        contract=contract if contract is not None else make_contract(),
        bid=bid,
        ask=ask,
        last=last,
        trades=trades,
        volume=volume,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# OptionQuote — lado ausente é None, nunca 0 (ADR-0003)
# ---------------------------------------------------------------------------


def _quote_com_um_lado(campo: str, valor: float) -> OptionQuote:
    """Só ``campo`` presente: isola o valor sob exame da checagem bid <= ask."""
    lados: dict[str, float | None] = {"bid": None, "ask": None, "last": None}
    lados[campo] = valor
    return make_quote(bid=lados["bid"], ask=lados["ask"], last=lados["last"])


def test_cotacao_valida_com_book_completo() -> None:
    quote = make_quote()
    assert (quote.bid, quote.ask, quote.last) == (1.20, 1.25, 1.22)


def test_todos_os_lados_ausentes_sao_legais() -> None:
    """Livro vazio e sem negócio é dado real (série ilíquida), não erro."""
    quote = make_quote(bid=None, ask=None, last=None, trades=0, volume=0.0)
    assert (quote.bid, quote.ask, quote.last) == (None, None, None)


@pytest.mark.parametrize("campo", ["bid", "ask", "last"])
def test_zero_de_sem_oferta_e_irrepresentavel(campo: str) -> None:
    """O zero da fonte vira None no adapter; se vazar, falha alto aqui."""
    with pytest.raises(InvalidDomainValueError, match="ADR-0003"):
        _quote_com_um_lado(campo, 0.0)


@pytest.mark.parametrize("campo", ["bid", "ask", "last"])
@pytest.mark.parametrize("valor", [-0.01, float("nan"), float("inf"), float("-inf")])
def test_lado_negativo_ou_nao_finito_e_irrepresentavel(campo: str, valor: float) -> None:
    with pytest.raises(InvalidDomainValueError, match=campo):
        _quote_com_um_lado(campo, valor)


def test_book_cruzado_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError, match="cruzado"):
        make_quote(bid=1.30, ask=1.25)


def test_book_travado_e_legal() -> None:
    """bid == ask é spread zero — coerente, como no MarketSnapshot."""
    quote = make_quote(bid=1.25, ask=1.25)
    assert quote.bid == quote.ask


@pytest.mark.parametrize(("bid", "ask"), [(1.30, None), (None, 0.90)])
def test_book_de_um_lado_so_nao_compara_com_o_lado_ausente(
    bid: float | None, ask: float | None
) -> None:
    """Sem o outro lado não há spread: qualquer valor positivo é legal."""
    quote = make_quote(bid=bid, ask=ask)
    assert (quote.bid, quote.ask) == (bid, ask)


def test_trades_negativo_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError, match="trades"):
        make_quote(trades=-1)


@pytest.mark.parametrize("volume", [-1.0, float("nan"), float("inf")])
def test_volume_negativo_ou_nao_finito_e_irrepresentavel(volume: float) -> None:
    with pytest.raises(InvalidDomainValueError, match="volume"):
        make_quote(volume=volume)


def test_last_sem_negocio_no_pregao_e_legal() -> None:
    """Fontes trazem o último preço de pregão anterior com trades == 0:
    não é incoerência da cotação — a regra de preço é quem o descarta."""
    quote = make_quote(bid=None, ask=None, last=1.10, trades=0, volume=0.0)
    assert quote.last == 1.10


class _FusoSemOffset(tzinfo):
    """tzinfo presente que ainda é naive na prática (utcoffset None)."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


@pytest.mark.parametrize(
    "timestamp",
    [datetime(2026, 10, 23, 18, 0), datetime(2026, 10, 23, 18, 0, tzinfo=_FusoSemOffset())],
    ids=["naive", "tzinfo-sem-offset"],
)
def test_timestamp_naive_e_irrepresentavel(timestamp: datetime) -> None:
    with pytest.raises(InvalidDomainValueError, match="tz-aware"):
        make_quote(timestamp=timestamp)


def test_cotacao_e_imutavel() -> None:
    quote = make_quote()
    with pytest.raises(FrozenInstanceError):
        quote.bid = 0.0  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste

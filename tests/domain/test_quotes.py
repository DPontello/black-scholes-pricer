"""UnderlyingQuote e DataSource — invariantes da cotação do ativo."""

import math
from dataclasses import FrozenInstanceError
from datetime import datetime
from typing import Any

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from tests._tolerances import REL_SELF

_T = datetime(2026, 10, 28, 12, 2, 31, tzinfo=B3_UTC_OFFSET)


def _cotacao(
    last: float | None = 52.51,
    bid: float | None = 52.50,
    ask: float | None = 52.53,
    previous_close: float | None = 52.79,
    trades: int = 22704,
    volume: float = 679557741.0,
    timestamp: datetime = _T,
) -> UnderlyingQuote:
    return UnderlyingQuote(
        "PETR4", last, bid, ask, previous_close, trades, volume, timestamp, DataSource.AO_VIVO
    )


def test_cotacao_do_ativo_lado_ausente_e_variacao() -> None:
    t = datetime(2026, 10, 28, 12, 2, 31, tzinfo=B3_UTC_OFFSET)
    q = UnderlyingQuote(
        "PETR4", 52.51, None, 52.53, 52.79, 22704, 679557741.0, t, DataSource.AO_VIVO
    )
    assert q.bid is None
    assert q.change_pct == pytest.approx(52.51 / 52.79 - 1, rel=REL_SELF)
    with pytest.raises(InvalidDomainValueError):
        UnderlyingQuote("PETR4", 0.0, None, None, None, 0, 0.0, t, DataSource.AO_VIVO)
    with pytest.raises(InvalidDomainValueError):
        UnderlyingQuote("PETR4", 52.5, 52.6, 52.5, None, 0, 0.0, t, DataSource.AO_VIVO)


def test_fontes_de_dado_tem_valor_estavel() -> None:
    assert [(f.name, f.value) for f in DataSource] == [
        ("AO_VIVO", "ao_vivo"),
        ("ATRASADO", "atrasado"),
        ("FIM_DE_DIA", "fim_de_dia"),
    ]


def test_cotacao_valida_guarda_os_campos_e_e_imutavel() -> None:
    q = _cotacao()
    assert (q.symbol, q.last, q.bid, q.ask, q.previous_close) == (
        "PETR4",
        52.51,
        52.50,
        52.53,
        52.79,
    )
    assert (q.trades, q.volume, q.timestamp, q.source) == (
        22704,
        679557741.0,
        _T,
        DataSource.AO_VIVO,
    )
    with pytest.raises(FrozenInstanceError):
        q.last = 1.0  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste


def test_todos_os_precos_ausentes_e_legal() -> None:
    q = _cotacao(last=None, bid=None, ask=None, previous_close=None, trades=0, volume=0.0)
    assert (q.last, q.bid, q.ask, q.previous_close) == (None, None, None, None)


@pytest.mark.parametrize("campo", ["last", "bid", "ask", "previous_close"])
@pytest.mark.parametrize("preco", [0.0, -1.0, math.nan, math.inf, -math.inf])
def test_preco_presente_deve_ser_finito_e_positivo(campo: str, preco: float) -> None:
    campos: dict[str, Any] = {campo: preco}
    with pytest.raises(InvalidDomainValueError, match=campo):
        _cotacao(**campos)


def test_book_travado_e_legal_e_cruzado_nao() -> None:
    assert _cotacao(bid=52.5, ask=52.5).ask == 52.5
    with pytest.raises(InvalidDomainValueError, match="book cruzado"):
        _cotacao(bid=52.54, ask=52.53)


def test_book_de_um_lado_so_nao_e_cruzado() -> None:
    assert _cotacao(bid=52.5, ask=None).ask is None
    assert _cotacao(bid=None, ask=52.5).bid is None


def test_negocios_negativos_sao_rejeitados() -> None:
    with pytest.raises(InvalidDomainValueError, match="trades"):
        _cotacao(trades=-1)


@pytest.mark.parametrize("volume", [-1.0, math.nan, math.inf])
def test_volume_deve_ser_finito_e_nao_negativo(volume: float) -> None:
    with pytest.raises(InvalidDomainValueError, match="volume"):
        _cotacao(volume=volume)


def test_timestamp_naive_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError, match="tz-aware"):
        _cotacao(timestamp=datetime(2026, 10, 28, 12, 2, 31))


def test_variacao_e_none_sem_ultimo_ou_sem_fechamento_anterior() -> None:
    assert _cotacao(last=None).change_pct is None
    assert _cotacao(previous_close=None).change_pct is None


def test_variacao_negativa_e_positiva() -> None:
    assert _cotacao(last=55.0, previous_close=50.0).change_pct == pytest.approx(0.1, rel=REL_SELF)
    assert _cotacao(last=45.0, previous_close=50.0).change_pct == pytest.approx(-0.1, rel=REL_SELF)

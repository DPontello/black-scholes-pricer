"""MarketSnapshot — invariantes da foto atômica de mercado."""

from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from options_engine.domain.model.errors import InvalidDomainValueError
from tests.domain._builders import make_snapshot


def test_snapshot_valido_carrega_convencoes_explicitas() -> None:
    snap = make_snapshot()
    # Taxa e vol nunca são float nu: chegam com a convenção a tiracolo.
    assert snap.risk_free_rate.compounding is not None
    assert snap.volatility.annualization_base is not None


@pytest.mark.parametrize("spot", [0.0, -30.0, float("nan"), float("inf")])
def test_spot_ilegal_e_irrepresentavel(spot: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_snapshot(spot=spot)


@pytest.mark.parametrize(
    ("bid", "mid", "ask"),
    [
        (30.05, 30.0, 30.10),  # bid > mid
        (29.95, 30.10, 30.05),  # mid > ask
        (-0.01, 30.0, 30.05),  # bid negativo
        (float("nan"), 30.0, 30.05),  # nan escondido numa ponta
    ],
)
def test_book_incoerente_e_irrepresentavel(bid: float, mid: float, ask: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_snapshot(bid=bid, mid=mid, ask=ask)


def test_book_de_ponta_unica_e_legal() -> None:
    """bid == mid == ask (book travado) é coerente — spread zero é >= 0."""
    snap = make_snapshot(bid=30.0, mid=30.0, ask=30.0)
    assert snap.bid == snap.ask


def test_timestamp_naive_e_irrepresentavel() -> None:
    """Contrato do MarketDataPort (ARCH §8): timestamps SEMPRE tz-aware."""
    with pytest.raises(InvalidDomainValueError):
        make_snapshot(timestamp=datetime(2026, 7, 3, 14, 0))


def test_underlying_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        make_snapshot(underlying_symbol="")


def test_snapshot_e_imutavel() -> None:
    snap = make_snapshot()
    with pytest.raises(FrozenInstanceError):
        snap.spot = 31.0  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste

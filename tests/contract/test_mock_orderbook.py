"""Mock plugado na suíte de contrato + promessas EXCLUSIVAS do mock (seed).

Determinismo por seed é testado AQUI, na subclasse — adapters reais não
prometem isso, e colocá-lo no contrato quebraria todo feed legítimo
(ARCH §8).
"""

from datetime import UTC, datetime

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.mock_orderbook import MockOrderBookAdapter
from options_engine.adapters.outbound.seeded_random import SeededRandomSource
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    Volatility,
)
from tests.contract.market_data_contract import MarketDataPortContract

INSTANTE = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)


def make_mock(seed: int = 42) -> MockOrderBookAdapter:
    return MockOrderBookAdapter(
        underlying_symbol="PETR4",
        initial_spot=30.0,
        drift=0.10,
        volatility=Volatility(0.25, DayCountConvention.BUSINESS_252),
        risk_free_rate=RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252),
        random_source=SeededRandomSource(seed),
        clock=FixedClock(INSTANTE),
    )


class TestMockOrderBookContract(MarketDataPortContract):
    def make_port(self) -> MockOrderBookAdapter:
        return make_mock()

    def known_symbol(self) -> str:
        return "PETR4"


# ---------------------------------------------------------------------------
# Promessas do mock: determinismo por seed (CONVENTIONS §7)
# ---------------------------------------------------------------------------


def _spots(seed: int, n: int = 10) -> tuple[float, ...]:
    mock = make_mock(seed)
    return tuple(mock.get_snapshot("PETR4").spot for _ in range(n))


def test_mesma_seed_produz_sequencias_identicas_bit_a_bit() -> None:
    # Igualdade exata deliberada: determinismo por seed é bit a bit,
    # não "aproximadamente igual" (CONVENTIONS §7).
    assert _spots(seed=42) == _spots(seed=42)


def test_seeds_distintas_produzem_sequencias_distintas() -> None:
    assert _spots(seed=42) != _spots(seed=43)


def test_fontes_com_mesma_seed_sao_fluxos_independentes() -> None:
    """Duas instâncias não compartilham estado: consumir uma não desloca a outra."""
    mock_a = make_mock(seed=42)
    mock_b = make_mock(seed=42)
    primeiro_de_a = mock_a.get_snapshot("PETR4").spot
    for _ in range(5):
        mock_b.get_snapshot("PETR4")
    assert make_mock(seed=42).get_snapshot("PETR4").spot == primeiro_de_a

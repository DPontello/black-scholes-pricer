"""``MockOrderBookAdapter`` — GBM, book coerente e teste estatístico com seed fixa.

A conformidade com o contrato do ``MarketDataPort`` vive em
``tests/contract/test_mock_orderbook.py`` (suíte herdável); aqui ficam as
propriedades ESPECÍFICAS do mock: fórmula do book, semântica
advance-then-return, validação de configuração e a estatística do GBM.
"""

from datetime import UTC, datetime
from itertools import pairwise
from math import log, sqrt

import pytest

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.mock_orderbook import MockOrderBookAdapter
from options_engine.adapters.outbound.seeded_random import SeededRandomSource
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    Volatility,
)
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import GBM_STAT_Z

INSTANTE = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)

SPOT_INICIAL = 30.0
DRIFT = 0.10
SIGMA = 0.25
DT = 1.0 / 252.0
SPREAD = 0.002


def make_mock(
    seed: int = 42,
    *,
    underlying_symbol: str = "PETR4",
    initial_spot: float = SPOT_INICIAL,
    drift: float = DRIFT,
    spread: float = SPREAD,
    dt_years: float = DT,
) -> MockOrderBookAdapter:
    """Mock válido por default; os testes sobrescrevem só o campo sob exame."""
    return MockOrderBookAdapter(
        underlying_symbol=underlying_symbol,
        initial_spot=initial_spot,
        drift=drift,
        volatility=Volatility(SIGMA, DayCountConvention.BUSINESS_252),
        risk_free_rate=RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252),
        random_source=SeededRandomSource(seed),
        clock=FixedClock(INSTANTE),
        spread=spread,
        dt_years=dt_years,
    )


# ---------------------------------------------------------------------------
# Book e semântica de avanço
# ---------------------------------------------------------------------------


def test_book_deriva_do_mid_pela_formula_do_spread() -> None:
    snapshot = make_mock().get_snapshot("PETR4")
    # Mesmo caminho aritmético da implementação — igualdade exata permitida.
    assert snapshot.mid == snapshot.spot
    assert snapshot.bid == snapshot.mid * (1.0 - SPREAD / 2.0)
    assert snapshot.ask == snapshot.mid * (1.0 + SPREAD / 2.0)


def test_spread_zero_colapsa_o_book_no_mid() -> None:
    snapshot = make_mock(spread=0.0).get_snapshot("PETR4")
    assert snapshot.bid == snapshot.mid == snapshot.ask


def test_advance_then_return_cada_consulta_e_um_tick_novo() -> None:
    """O passeio avança ANTES de fotografar: o spot de configuração é o
    estado anterior ao primeiro snapshot, e consultas seguidas diferem."""
    mock = make_mock()
    primeiro = mock.get_snapshot("PETR4").spot
    segundo = mock.get_snapshot("PETR4").spot
    assert primeiro != SPOT_INICIAL
    assert segundo != primeiro


def test_primeiro_passo_reproduz_a_formula_do_gbm() -> None:
    """Golden de fórmula: S1 = S0·exp((mu - sigma²/2)·dt + sigma·√dt·Z) com o MESMO
    primeiro gaussiano da seed — pega drift sem -sigma²/2 e √dt esquecido."""
    from math import exp

    (z,) = SeededRandomSource(42).gaussians(1)
    esperado = SPOT_INICIAL * exp((DRIFT - 0.5 * SIGMA * SIGMA) * DT + SIGMA * sqrt(DT) * z)
    assert make_mock(seed=42).get_snapshot("PETR4").spot == esperado


# ---------------------------------------------------------------------------
# Configuração ilegal falha na construção, nunca no uso
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("underlying_symbol", ""),
        ("initial_spot", 0.0),
        ("initial_spot", -30.0),
        ("initial_spot", float("nan")),
        ("drift", float("inf")),
        ("spread", -0.01),
        ("spread", 2.0),  # bid = mid·(1 - 2/2) = 0... e além viola bid >= 0
        ("spread", float("nan")),
        ("dt_years", 0.0),
        ("dt_years", -DT),
    ],
)
def test_configuracao_ilegal_e_rejeitada(campo: str, valor: float | str) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_mock(**{campo: valor})  # type: ignore[arg-type]  # kwarg dinâmico é detalhe do parametrize


# ---------------------------------------------------------------------------
# Estatística do GBM — seed FIXA: determinístico, não flaky
# ---------------------------------------------------------------------------

# GUARDA: NÃO remova a seed fixa deste teste. Sem ela o teste vira loteria
# (risco documentado no ROADMAP S3); com ela, a margem GBM_STAT_Z só precisa
# acomodar o sorteio DESTA seed, e o resultado é bit a bit reprodutível.
_SEED_ESTATISTICA = 20260704
_N_PASSOS = 4000


def test_log_retornos_tem_media_e_desvio_do_gbm() -> None:
    """Momentos amostrais dos log-retornos vs teóricos do GBM exato:
    média (mu - sigma²/2)·dt e desvio sigma·√dt, com margem de GBM_STAT_Z
    erros-padrão. Um √dt esquecido infla o desvio ~16x (√252): dezenas de
    erros-padrão — impossível passar por acaso."""
    mock = make_mock(seed=_SEED_ESTATISTICA)
    spots = [SPOT_INICIAL] + [mock.get_snapshot("PETR4").spot for _ in range(_N_PASSOS)]
    retornos = [log(b / a) for a, b in pairwise(spots)]

    n = len(retornos)
    media_amostral = sum(retornos) / n
    variancia_amostral = sum((r - media_amostral) ** 2 for r in retornos) / (n - 1)
    desvio_amostral = sqrt(variancia_amostral)

    media_teorica = (DRIFT - 0.5 * SIGMA * SIGMA) * DT
    desvio_teorico = SIGMA * sqrt(DT)

    erro_padrao_da_media = desvio_teorico / sqrt(n)
    assert abs(media_amostral - media_teorica) <= GBM_STAT_Z * erro_padrao_da_media

    # Erro-padrão assintótico do desvio amostral sob normalidade: sigma/√(2(n-1)).
    erro_padrao_do_desvio = desvio_teorico / sqrt(2.0 * (n - 1))
    assert abs(desvio_amostral - desvio_teorico) <= GBM_STAT_Z * erro_padrao_do_desvio

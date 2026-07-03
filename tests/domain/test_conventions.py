"""VOs de convenção — day count, capitalização e bases de anualização.

O oráculo aqui é a definição matemática: ``r_cont = ln(1 + r_efetiva)``
(CONVENTIONS §3) e a conversão dias -> fração de ano por base explícita
(CONVENTIONS §2). Tolerâncias de ``tests/_tolerances.py``, nunca inline.
"""

import math
from dataclasses import FrozenInstanceError

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
    TimeToExpiry,
    Volatility,
)
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close

# ---------------------------------------------------------------------------
# DayCountConvention
# ---------------------------------------------------------------------------


def test_bases_de_contagem_ratificadas() -> None:
    assert DayCountConvention.BUSINESS_252.days_per_year == 252
    assert DayCountConvention.CALENDAR_365.days_per_year == 365


# ---------------------------------------------------------------------------
# RiskFreeRate — CDI vs contínua
# ---------------------------------------------------------------------------


def test_taxa_continua_passa_direto() -> None:
    # Ramo de forma fechada com caminho aritmético idêntico: == permitido.
    assert RiskFreeRate(0.10, Compounding.CONTINUOUS).as_continuous() == 0.10


def test_cdi_convertido_por_ln_um_mais_taxa() -> None:
    """CDI 13.65% efetiva anual base 252 -> contínua = ln(1.1365).

    Oráculo por caminho aritmético independente (log em vez de log1p).
    """
    cdi = RiskFreeRate(0.1365, Compounding.BUSINESS_DAILY_252)
    assert_close(
        cdi.as_continuous(),
        math.log(1.0 + 0.1365),
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR,
        label="cdi->continua",
    )


@given(rate=st.floats(min_value=-0.5, max_value=1.0, allow_nan=False))
def test_round_trip_efetiva_continua_efetiva(rate: float) -> None:
    """exp(as_continuous()) - 1 devolve a taxa efetiva original."""
    r = RiskFreeRate(rate, Compounding.BUSINESS_DAILY_252)
    assert_close(
        math.expm1(r.as_continuous()),
        rate,
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR,
        label="round-trip taxa",
    )


@pytest.mark.parametrize("rate", [float("nan"), float("inf"), -1.0, -2.0])
def test_taxa_ilegal_e_irrepresentavel(rate: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        RiskFreeRate(rate, Compounding.CONTINUOUS)


def test_taxa_negativa_moderada_e_legal() -> None:
    """CDI não é negativo, mas o core não pode quebrar com r < 0 (VV-PLAN §3)."""
    assert RiskFreeRate(-0.05, Compounding.CONTINUOUS).as_continuous() == -0.05


# ---------------------------------------------------------------------------
# Volatility
# ---------------------------------------------------------------------------


def test_vol_zero_e_legal_limite_do_kernel() -> None:
    vol = Volatility(0.0, DayCountConvention.BUSINESS_252)
    assert vol.value == 0.0
    assert vol.annualization_base is DayCountConvention.BUSINESS_252


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.2])
def test_vol_ilegal_e_irrepresentavel(value: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        Volatility(value, DayCountConvention.BUSINESS_252)


# ---------------------------------------------------------------------------
# TimeToExpiry
# ---------------------------------------------------------------------------


def test_from_days_business_252() -> None:
    ttx = TimeToExpiry.from_days(126)
    # 126/252 é exatamente 0.5 em float64 (divisão por potência da mesma
    # mantissa): ramo de forma fechada, == permitido.
    assert ttx.year_fraction == 0.5
    assert ttx.convention is DayCountConvention.BUSINESS_252  # default ratificado


def test_from_days_calendar_365() -> None:
    ttx = TimeToExpiry.from_days(365, DayCountConvention.CALENDAR_365)
    assert ttx.year_fraction == 1.0
    assert ttx.convention is DayCountConvention.CALENDAR_365


def test_vencimento_hoje_e_legal() -> None:
    """tau = 0 é limite legal (tabela normativa de fronteiras)."""
    assert TimeToExpiry.from_days(0).year_fraction == 0.0


@pytest.mark.parametrize("year_fraction", [float("nan"), float("inf"), -0.1])
def test_fracao_ilegal_e_irrepresentavel(year_fraction: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        TimeToExpiry(year_fraction, DayCountConvention.BUSINESS_252)


def test_contagem_negativa_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        TimeToExpiry.from_days(-1)


# ---------------------------------------------------------------------------
# Imutabilidade (VOs frozen)
# ---------------------------------------------------------------------------


def test_vos_de_convencao_sao_imutaveis() -> None:
    rate = RiskFreeRate(0.10, Compounding.CONTINUOUS)
    with pytest.raises(FrozenInstanceError):
        rate.rate = 0.20  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste

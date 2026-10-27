"""Anualização composta em dias úteis e excesso sobre o CDI (ADR-0005 §2-3).

Oráculos: potências exatas calculáveis à mão (expoentes inteiros 252/du ou
raiz quadrada exata) e, nas propriedades, a fórmula ingênua
``(1 + r) ** (252 / du) - 1`` — caminho aritmético DIFERENTE do
``expm1/log1p`` da implementação (tolerância de identidade matemática).
"""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.income import annualize_yield_252, excess_over_cdi_annual_252
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import (
    ABS_INCOME,
    ABS_MATH_IDENTITY_FLOOR,
    INEQ_SLACK,
    REL_INCOME,
    REL_MATH_IDENTITY,
    assert_close,
)
from tests.income._builders import make_cdi

# ---------------------------------------------------------------------------
# annualize_yield_252 — golden cases atravessando valores típicos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("yield_period", "business_days", "esperado"),
    [
        # 1 mês (21 du): 1,02^12 - 1
        (0.02, 21, 0.2682417945625453183),
        # 2 meses (42 du): 1,025^6 - 1 = 1,159693418212890625 - 1 (exato)
        (0.025, 42, 0.159693418212890625),
        # 1 trimestre (63 du): 1,25^4 - 1 = 2,44140625 - 1 (exato)
        (0.25, 63, 1.44140625),
        # 1 semestre (126 du): 1,6^2 - 1 = 2,56 - 1
        (0.60, 126, 1.56),
        # 1 ano (252 du): identidade
        (0.10, 252, 0.10),
        # 2 anos (504 du): raiz exata, sqrt(1,21) - 1 = 0,1
        (0.21, 504, 0.10),
        # 1 pregão (1 du): 1,01^252 - 1
        (0.01, 1, 11.27400209924021670),
        # rendimento negativo (líquido de custos): 0,81^2 - 1 = -0,3439
        (-0.19, 126, -0.3439),
        # rendimento nulo é nulo em qualquer prazo
        (0.0, 7, 0.0),
    ],
)
def test_anualizacao_golden(yield_period: float, business_days: int, esperado: float) -> None:
    resultado = annualize_yield_252(yield_period, business_days)
    assert resultado is not None
    assert_close(
        resultado,
        esperado,
        rel=REL_INCOME,
        abs_=ABS_INCOME,
        label=f"anual(r={yield_period}, du={business_days})",
    )


@pytest.mark.parametrize("yield_period", [0.0, 0.02, -0.5, 3.0])
def test_zero_dia_util_nao_anualiza(yield_period: float) -> None:
    """Vencimento hoje (0 du): sem período a anualizar -> None, nunca divisão por zero."""
    assert annualize_yield_252(yield_period, 0) is None


def test_dias_uteis_negativos_sao_rejeitados() -> None:
    with pytest.raises(InvalidDomainValueError):
        annualize_yield_252(0.02, -1)


@pytest.mark.parametrize("yield_period", [-1.0, -1.5, float("nan"), float("inf")])
def test_rendimento_sem_anualizacao_real_e_rejeitado(yield_period: float) -> None:
    """r <= -1 deixa 1 + r <= 0 (sem potência real); não-finito não é rendimento."""
    with pytest.raises(InvalidDomainValueError):
        annualize_yield_252(yield_period, 21)


def test_rendimento_invalido_e_rejeitado_mesmo_com_zero_du() -> None:
    """Validação antes do ramo du = 0: entrada inválida nunca vira None silencioso."""
    with pytest.raises(InvalidDomainValueError):
        annualize_yield_252(float("nan"), 0)


def test_anualizado_fora_do_float64_e_erro_explicito() -> None:
    """Retorno sobre risco de 9.900% em 1 du: 100^252 estoura o float64 -> erro, nunca inf."""
    with pytest.raises(InvalidDomainValueError):
        annualize_yield_252(99.0, 1)


# ---------------------------------------------------------------------------
# Propriedades
# ---------------------------------------------------------------------------

_rendimento = st.floats(min_value=-0.5, max_value=2.0, allow_nan=False)
_du = st.integers(min_value=1, max_value=756)


@given(r=_rendimento, du=_du)
def test_igual_a_formula_composta_ingenua(r: float, du: int) -> None:
    """Mesma grandeza por outro caminho aritmético: (1 + r) ** (252 / du) - 1."""
    resultado = annualize_yield_252(r, du)
    assert resultado is not None
    assert_close(
        resultado,
        (1.0 + r) ** (252 / du) - 1.0,
        rel=REL_MATH_IDENTITY,
        abs_=ABS_MATH_IDENTITY_FLOOR,
        label="expm1/log1p vs pow",
    )


@given(r=st.floats(min_value=0.0, max_value=2.0), du=_du)
def test_ida_e_volta_anual_para_periodo(r: float, du: int) -> None:
    """Desanualizar o anualizado devolve o rendimento do período.

    Só r >= 0: com r negativo e poucos du, ``1 + anual`` encosta em 0 e a
    volta perde dígitos por condicionamento (não por erro da fórmula).
    """
    anual = annualize_yield_252(r, du)
    assert anual is not None
    assert_close(
        math.expm1(du / 252 * math.log1p(anual)),
        r,
        rel=REL_MATH_IDENTITY,
        abs_=ABS_MATH_IDENTITY_FLOOR,
        label="round-trip",
    )


@given(r1=_rendimento, r2=_rendimento, du=_du)
def test_mais_rendimento_no_periodo_mais_rendimento_anual(r1: float, r2: float, du: int) -> None:
    baixo, alto = sorted((r1, r2))
    anual_baixo = annualize_yield_252(baixo, du)
    anual_alto = annualize_yield_252(alto, du)
    assert anual_baixo is not None
    assert anual_alto is not None
    assert anual_alto >= anual_baixo - INEQ_SLACK * max(1.0, abs(anual_baixo))


@given(r=st.floats(min_value=1e-6, max_value=2.0), du=_du)
def test_prazo_curto_compoe_para_cima_e_longo_para_baixo(r: float, du: int) -> None:
    """r > 0: menos de 1 ano (du < 252) anualiza acima de r; mais de 1 ano, abaixo."""
    anual = annualize_yield_252(r, du)
    assert anual is not None
    folga = INEQ_SLACK * max(1.0, anual)
    if du <= 252:
        assert anual >= r - folga
    else:
        assert anual <= r + folga


# ---------------------------------------------------------------------------
# excess_over_cdi_annual_252
# ---------------------------------------------------------------------------


def test_excesso_e_a_diferenca_simples_contra_o_cdi() -> None:
    """Put coberta 2% em 21 du: 26,8241794562545% a.a. - CDI 12% = 14,8241794562545 p.p."""
    excesso = excess_over_cdi_annual_252(0.2682417945625453, make_cdi(0.12))
    assert excesso is not None
    assert_close(excesso, 0.1482417945625453, rel=REL_INCOME, abs_=ABS_INCOME, label="excesso")


def test_excesso_negativo_quando_rende_menos_que_o_cdi() -> None:
    excesso = excess_over_cdi_annual_252(0.10, make_cdi(0.12))
    assert excesso is not None
    assert_close(excesso, -0.02, rel=REL_INCOME, abs_=ABS_INCOME, label="excesso negativo")


def test_sem_anualizado_nao_ha_excesso() -> None:
    assert excess_over_cdi_annual_252(None, make_cdi()) is None


@pytest.mark.parametrize("anual", [0.15, None])
def test_cdi_em_capitalizacao_continua_e_rejeitado(anual: float | None) -> None:
    """Contínua -> efetiva não é método do VO: o domínio rejeita em vez de inventar."""
    with pytest.raises(InvalidDomainValueError):
        excess_over_cdi_annual_252(anual, RiskFreeRate(0.12, Compounding.CONTINUOUS))


@pytest.mark.parametrize("anual", [float("nan"), float("inf")])
def test_anualizado_nao_finito_e_rejeitado(anual: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        excess_over_cdi_annual_252(anual, make_cdi())

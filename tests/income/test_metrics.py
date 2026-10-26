"""Métricas de renda por estrutura — golden cases à mão, bordas e monotonia.

Oráculo: aritmética à mão (docstring de cada golden case) sobre a tabela de
custos ILUSTRATIVA dos builders (emolumentos 0,05% do prêmio, corretagem
5,00 por ordem, IR 15% sobre o ganho positivo), CDI 12% a.a. efetivo base
252 e o tamanho de referência de 100 ações. Os literais anualizados vêm de
potências inteiras exatas (252/du inteiro), expandidas com aritmética
racional a 19 algarismos.
"""

from dataclasses import replace
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.income import (
    CostSchedule,
    IncomeMetrics,
    IncomeStructure,
    cash_secured_put_metrics,
    covered_call_metrics,
)
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import ABS_INCOME, INEQ_SLACK, REL_INCOME, assert_close
from tests.income._builders import make_cdi, make_cost_schedule, zero_cost_schedule


def _close(actual: float | None, expected: float, label: str) -> None:
    assert actual is not None, f"{label}: None inesperado"
    assert_close(actual, expected, rel=REL_INCOME, abs_=ABS_INCOME, label=label)


def _assert_nao_piora(antes: float | None, depois: float | None, label: str) -> None:
    """``depois >= antes`` com folga relativa (desigualdade estrita vira >= -folga)."""
    assert antes is not None
    assert depois is not None, label
    assert depois >= antes - INEQ_SLACK * max(1.0, abs(antes)), f"{label}: {depois} < {antes}"


# ---------------------------------------------------------------------------
# Put coberta (cash-secured put) — ADR-0005 §1: prêmio / strike
# ---------------------------------------------------------------------------


def _csp(**overrides: Any) -> IncomeMetrics:
    kwargs: dict[str, Any] = {
        "strike": 30.0,
        "premium_per_share": 0.60,
        "business_days": 21,
        "cdi": make_cdi(0.12),
        "cost_schedule": make_cost_schedule(),
    }
    kwargs.update(overrides)
    return cash_secured_put_metrics(**kwargs)


def test_put_coberta_golden_bruto() -> None:
    """Vende put K = 30,00 a 0,60, 21 du, CDI 12%.

    rendimento no período = 0,60 / 30,00                   = 0,02
    anualizado            = 1,02^(252/21) - 1 = 1,02^12 - 1 = 0,268241794562545318...
    excesso sobre o CDI   = 0,2682417945625453 - 0,12      = 0,1482417945625453
    breakeven             = 30,00 - 0,60                   = 29,40
    ganho máximo          = 0,60 x 100                     = 60,00
    pior resultado        = -(30,00 - 0,60) x 100          = -2.940,00
    """
    m = _csp()
    assert m.structure is IncomeStructure.CASH_SECURED_PUT
    _close(m.yield_period, 0.02, "rendimento")
    _close(m.yield_annual_252, 0.2682417945625453183, "anualizado")
    _close(m.excess_over_cdi_annual_252, 0.1482417945625453183, "excesso")
    _close(m.breakeven, 29.40, "breakeven")
    _close(m.max_gain_per_position, 60.0, "ganho máximo")
    _close(m.max_loss_per_position, -2940.0, "pior resultado")
    assert m.downside_protection is None
    _close(m.capital_base_per_share, 30.0, "base = strike")


def test_put_coberta_golden_liquido() -> None:
    """Mesma operação, líquida de custos (100 ações, 1 ordem).

    custos = 0,03 (emol.) + 5,00 (corret.) + 0,15 x 54,97 (IR = 8,2455) = 13,2755
    resultado líquido = 60,00 - 13,2755                  = 46,7245
    rendimento líquido = 46,7245 / (30,00 x 100)         = 0,015574833333...
    anualizado líquido = 1,0155748333...^12 - 1          = 0,203769020845069515...
    excesso líquido    = 0,2037690208450695 - 0,12       = 0,0837690208450695
    """
    m = _csp()
    _close(m.costs.total, 13.2755, "custos")
    _close(m.net_yield_period, 0.01557483333333333333, "rendimento líquido")
    _close(m.net_yield_annual_252, 0.2037690208450695159, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 0.0837690208450695159, "excesso líquido")
    assert m.costs.schedule == make_cost_schedule()


def test_put_coberta_carrega_as_entradas() -> None:
    """Rastreabilidade: o resultado guarda du, tamanho, CDI e a tabela usada."""
    m = _csp(reference_shares=300)
    assert (m.business_days, m.reference_shares) == (21, 300)
    assert m.cdi == make_cdi(0.12)
    assert m.premium_per_share == 0.60


def test_put_coberta_sem_custos_liquido_igual_ao_bruto() -> None:
    m = _csp(cost_schedule=zero_cost_schedule())
    _close(m.net_yield_period, m.yield_period, "líquido == bruto")
    assert m.yield_annual_252 is not None
    _close(m.net_yield_annual_252, m.yield_annual_252, "anualizado líquido == bruto")


def test_put_coberta_vencendo_hoje_nao_anualiza() -> None:
    """0 du: rendimento no período existe; anualizados e excessos são None."""
    m = _csp(business_days=0)
    _close(m.yield_period, 0.02, "rendimento")
    assert m.yield_annual_252 is None
    assert m.excess_over_cdi_annual_252 is None
    assert m.net_yield_annual_252 is None
    assert m.net_excess_over_cdi_annual_252 is None


def test_put_coberta_premio_zero() -> None:
    """Prêmio zero: rendimento bruto 0, excesso = -CDI; líquido paga só a corretagem.

    rendimento líquido = (0 - 5,00) / 3.000,00 = -0,0016666...; sem IR.
    """
    m = _csp(premium_per_share=0.0)
    _close(m.yield_period, 0.0, "rendimento")
    _close(m.yield_annual_252, 0.0, "anualizado")
    _close(m.excess_over_cdi_annual_252, -0.12, "excesso")
    _close(m.net_yield_period, -5.0 / 3000.0, "rendimento líquido")
    assert m.costs.income_tax == 0.0
    _close(m.max_gain_per_position, 0.0, "ganho máximo")


def test_tamanho_maior_dilui_a_corretagem_fixa() -> None:
    """Corretagem fixa por ordem: 1.000 ações rendem mais líquido que 100."""
    pequena, grande = _csp(), _csp(reference_shares=1000)
    _close(grande.yield_period, pequena.yield_period, "bruto não depende do tamanho")
    assert grande.net_yield_period > pequena.net_yield_period


@pytest.mark.parametrize("premio", [30.0, 31.0])
def test_put_coberta_premio_maior_ou_igual_ao_strike_e_inconsistente(premio: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        _csp(premium_per_share=premio)


@pytest.mark.parametrize("premio", [-0.01, float("nan"), float("inf")])
def test_put_coberta_premio_invalido(premio: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        _csp(premium_per_share=premio)


@pytest.mark.parametrize("strike", [0.0, -30.0, float("nan"), float("inf")])
def test_put_coberta_strike_invalido(strike: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        _csp(strike=strike)


@pytest.mark.parametrize(
    "overrides",
    [
        {"business_days": -1},
        {"reference_shares": 0},
        {"cdi": RiskFreeRate(0.12, Compounding.CONTINUOUS)},
    ],
)
def test_put_coberta_entradas_invalidas(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidDomainValueError):
        _csp(**overrides)


def test_custos_acima_do_capital_nao_tem_anualizacao() -> None:
    """Corretagem maior que o capital: (0 - 5,00) / 4,00 = -125% -> rejeitada."""
    with pytest.raises(InvalidDomainValueError):
        _csp(strike=0.04, premium_per_share=0.0)


# ---------------------------------------------------------------------------
# Venda coberta (covered call) — decisão da mesa: prêmio / spot
# ---------------------------------------------------------------------------


def _cc(**overrides: Any) -> IncomeMetrics:
    kwargs: dict[str, Any] = {
        "spot": 32.0,
        "strike": 34.0,
        "premium_per_share": 0.80,
        "business_days": 42,
        "cdi": make_cdi(0.12),
        "cost_schedule": make_cost_schedule(),
    }
    kwargs.update(overrides)
    return covered_call_metrics(**kwargs)


def test_venda_coberta_golden_bruto() -> None:
    """Ação a 32,00, vende call K = 34,00 a 0,80, 42 du, CDI 12%.

    rendimento no período = 0,80 / 32,00                       = 0,025
    anualizado            = 1,025^(252/42) - 1 = 1,025^6 - 1   = 0,159693418212890625
    excesso sobre o CDI   = 0,159693418212890625 - 0,12        = 0,039693418212890625
    proteção              = 0,80 / 32,00                       = 0,025
    breakeven             = 32,00 - 0,80                       = 31,20
    ganho máximo          = (34,00 - 32,00 + 0,80) x 100       = 280,00
    pior resultado        = -(32,00 - 0,80) x 100              = -3.120,00
    """
    m = _cc()
    assert m.structure is IncomeStructure.COVERED_CALL
    _close(m.yield_period, 0.025, "rendimento")
    _close(m.yield_annual_252, 0.159693418212890625, "anualizado")
    _close(m.excess_over_cdi_annual_252, 0.039693418212890625, "excesso")
    _close(m.downside_protection, 0.025, "proteção")
    _close(m.breakeven, 31.20, "breakeven")
    _close(m.max_gain_per_position, 280.0, "ganho máximo")
    _close(m.max_loss_per_position, -3120.0, "pior resultado")
    _close(m.capital_base_per_share, 32.0, "base = spot")


def test_venda_coberta_golden_liquido() -> None:
    """Mesma operação, líquida de custos (100 ações, 1 ordem — só a opção).

    custos = 0,04 (emol.) + 5,00 (corret.) + 0,15 x 74,96 (IR = 11,244) = 16,284
    resultado líquido  = 80,00 - 16,284                  = 63,716
    rendimento líquido = 63,716 / (32,00 x 100)          = 0,01991125
    anualizado líquido = 1,01991125^6 - 1                = 0,125574624109128730...
    excesso líquido    = 0,1255746241091287 - 0,12       = 0,0055746241091287
    """
    m = _cc()
    _close(m.costs.total, 16.284, "custos")
    _close(m.net_yield_period, 0.01991125, "rendimento líquido")
    _close(m.net_yield_annual_252, 0.1255746241091287306, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 0.0055746241091287306, "excesso líquido")


def test_venda_coberta_dentro_do_dinheiro() -> None:
    """Strike 30 abaixo do spot 32: ganho máximo = (30 - 32 + 2,50) x 100 = 50,00."""
    m = _cc(strike=30.0, premium_per_share=2.50)
    _close(m.max_gain_per_position, 50.0, "ganho máximo ITM")
    _close(m.yield_period, 2.50 / 32.0, "rendimento continua prêmio / spot")


def test_venda_coberta_premio_igual_ao_intrinseco_tem_ganho_maximo_zero() -> None:
    m = _cc(strike=30.0, premium_per_share=2.0)
    _close(m.max_gain_per_position, 0.0, "ganho máximo")


def test_venda_coberta_vencendo_hoje_nao_anualiza() -> None:
    m = _cc(business_days=0)
    _close(m.yield_period, 0.025, "rendimento")
    _close(m.downside_protection, 0.025, "proteção")
    assert m.yield_annual_252 is None
    assert m.net_yield_annual_252 is None
    assert m.excess_over_cdi_annual_252 is None
    assert m.net_excess_over_cdi_annual_252 is None


def test_venda_coberta_premio_zero() -> None:
    """Prêmio zero: rendimento e proteção nulos; líquido = -5,00 / 3.200,00."""
    m = _cc(premium_per_share=0.0)
    _close(m.yield_period, 0.0, "rendimento")
    _close(m.downside_protection, 0.0, "proteção")
    _close(m.net_yield_period, -5.0 / 3200.0, "rendimento líquido")
    assert m.costs.income_tax == 0.0


@pytest.mark.parametrize(
    "overrides",
    [
        {"premium_per_share": 32.0},  # call valendo o spot inteiro
        {"strike": 30.0, "premium_per_share": 1.50},  # abaixo do intrínseco (2,00)
        {"premium_per_share": -0.01},
        {"premium_per_share": float("nan")},
        {"spot": 0.0},
        {"spot": float("inf")},
        {"strike": 0.0},
        {"business_days": -1},
        {"cdi": RiskFreeRate(0.12, Compounding.CONTINUOUS)},
    ],
)
def test_venda_coberta_entradas_invalidas(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidDomainValueError):
        _cc(**overrides)


# ---------------------------------------------------------------------------
# IncomeMetrics — invariantes do VO de resultado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campo_valor",
    [
        {"premium_per_share": -0.01},
        {"capital_base_per_share": 0.0},
        {"business_days": -1},
        {"reference_shares": 0},
        {"cdi": RiskFreeRate(0.12, Compounding.CONTINUOUS)},
        {"yield_period": float("nan")},
        {"net_yield_period": float("inf")},
        {"breakeven": float("nan")},
        {"max_gain_per_position": float("inf")},
        {"max_loss_per_position": float("-inf")},
        {"yield_annual_252": None},
        {"net_excess_over_cdi_annual_252": float("nan")},
        {"business_days": 0},  # anualizados presentes com 0 du
        {"downside_protection": 0.02},  # proteção só existe na venda coberta
        {"structure": IncomeStructure.COVERED_CALL},  # venda coberta sem proteção
        {"structure": IncomeStructure.COVERED_CALL, "downside_protection": float("nan")},
    ],
)
def test_vo_de_resultado_rejeita_estado_invalido(campo_valor: dict[str, Any]) -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(_csp(), **campo_valor)


# ---------------------------------------------------------------------------
# Propriedades — mais prêmio, mais rendimento; mais custo, menos líquido
# ---------------------------------------------------------------------------

_strike = st.integers(min_value=500, max_value=10_000).map(lambda centavos: centavos / 100.0)
_fracao_do_strike = st.floats(min_value=0.0, max_value=0.5)
_du = st.integers(min_value=0, max_value=504)
_tabela = st.builds(
    make_cost_schedule,
    exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    brokerage_per_order=st.floats(min_value=0.0, max_value=50.0),
    income_tax_rate=st.floats(min_value=0.0, max_value=0.3),
)


def _rendimentos(m: IncomeMetrics) -> tuple[tuple[str, float | None], ...]:
    return (
        ("yield_period", m.yield_period),
        ("yield_annual_252", m.yield_annual_252),
        ("excess_over_cdi_annual_252", m.excess_over_cdi_annual_252),
        ("net_yield_period", m.net_yield_period),
        ("net_yield_annual_252", m.net_yield_annual_252),
        ("net_excess_over_cdi_annual_252", m.net_excess_over_cdi_annual_252),
    )


def _assert_todos_nao_pioram(antes: IncomeMetrics, depois: IncomeMetrics) -> None:
    for (nome, a), (_, d) in zip(_rendimentos(antes), _rendimentos(depois), strict=True):
        if a is None:  # du = 0: ambos sem anualização
            assert d is None
        else:
            _assert_nao_piora(a, d, nome)


def _somar_tabelas(barata: CostSchedule, acrescimo: CostSchedule) -> CostSchedule:
    """Tabela mais cara em TODOS os parâmetros (cada um >= o da barata)."""
    return make_cost_schedule(
        exchange_fee_rate=barata.exchange_fee_rate + acrescimo.exchange_fee_rate,
        brokerage_per_order=barata.brokerage_per_order + acrescimo.brokerage_per_order,
        income_tax_rate=barata.income_tax_rate + acrescimo.income_tax_rate,
    )


@given(strike=_strike, f1=_fracao_do_strike, f2=_fracao_do_strike, du=_du, tabela=_tabela)
def test_put_coberta_mais_premio_mais_rendimento(
    strike: float, f1: float, f2: float, du: int, tabela: CostSchedule
) -> None:
    baixo, alto = sorted((f1 * strike, f2 * strike))
    menor = _csp(strike=strike, premium_per_share=baixo, business_days=du, cost_schedule=tabela)
    maior = _csp(strike=strike, premium_per_share=alto, business_days=du, cost_schedule=tabela)
    _assert_todos_nao_pioram(menor, maior)


@given(strike=_strike, fracao=_fracao_do_strike, du=_du, barata=_tabela, acrescimo=_tabela)
def test_put_coberta_mais_custo_menos_liquido(
    strike: float, fracao: float, du: int, barata: CostSchedule, acrescimo: CostSchedule
) -> None:
    cara = _somar_tabelas(barata, acrescimo)
    premio = fracao * strike
    m_barata = _csp(strike=strike, premium_per_share=premio, business_days=du, cost_schedule=barata)
    m_cara = _csp(strike=strike, premium_per_share=premio, business_days=du, cost_schedule=cara)
    # Custo só mexe no líquido: o caro nunca rende mais que o barato.
    _assert_todos_nao_pioram(m_cara, m_barata)
    _close(m_cara.yield_period, m_barata.yield_period, "bruto independe do custo")


@given(
    spot=_strike,
    moneyness=st.floats(min_value=0.0, max_value=0.3),
    f1=_fracao_do_strike,
    f2=_fracao_do_strike,
    du=_du,
    tabela=_tabela,
)
def test_venda_coberta_mais_premio_mais_rendimento(
    spot: float, moneyness: float, f1: float, f2: float, du: int, tabela: CostSchedule
) -> None:
    """Strike >= spot (OTM/ATM): todo prêmio em [0, spot/2] respeita os limites."""
    strike = spot * (1.0 + moneyness)
    baixo, alto = sorted((f1 * spot, f2 * spot))
    comum: dict[str, Any] = {
        "spot": spot,
        "strike": strike,
        "business_days": du,
        "cost_schedule": tabela,
    }
    menor = _cc(premium_per_share=baixo, **comum)
    maior = _cc(premium_per_share=alto, **comum)
    _assert_todos_nao_pioram(menor, maior)
    _assert_nao_piora(menor.downside_protection, maior.downside_protection, "proteção")


@given(spot=_strike, fracao=_fracao_do_strike, du=_du, barata=_tabela, acrescimo=_tabela)
def test_venda_coberta_mais_custo_menos_liquido(
    spot: float, fracao: float, du: int, barata: CostSchedule, acrescimo: CostSchedule
) -> None:
    comum: dict[str, Any] = {
        "spot": spot,
        "strike": spot,
        "premium_per_share": fracao * spot,
        "business_days": du,
    }
    m_barata = _cc(cost_schedule=barata, **comum)
    m_cara = _cc(cost_schedule=_somar_tabelas(barata, acrescimo), **comum)
    _assert_todos_nao_pioram(m_cara, m_barata)
    _close(m_cara.yield_period, m_barata.yield_period, "bruto independe do custo")

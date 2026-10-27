"""Métricas de renda por estrutura — golden cases à mão, bordas e monotonia.

Oráculo: aritmética à mão (docstring de cada golden case) sobre a tabela de
custos ILUSTRATIVA dos builders (emolumentos de opções 0,05% do prêmio, do
à vista 0,02%, corretagem 5,00 por ordem, corretagem de exercício 2,00, IR
15% sobre o ganho positivo), CDI 12% a.a. efetivo base 252 e o tamanho de
referência de 100 ações. Os literais anualizados vêm de
potências inteiras exatas (252/du inteiro), expandidas com aritmética
racional a 19 algarismos.
"""

from dataclasses import replace
from typing import Any

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from options_engine.domain.income import (
    CostSchedule,
    IncomeMetrics,
    IncomeStructure,
    cash_secured_put_metrics,
    covered_call_metrics,
    credit_spread_metrics,
)
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    InvalidStrategyError,
    MissingPremiumError,
)
from options_engine.domain.model.factories import vertical_spread
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import payoff_profile
from tests._tolerances import (
    ABS_BREAKEVEN,
    ABS_INCOME,
    INEQ_SLACK,
    REL_BREAKEVEN,
    REL_INCOME,
    assert_close,
)
from tests.domain._builders import make_straddle_legs, make_vertical_legs
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


def test_put_coberta_golden_extremos_liquidos() -> None:
    """Mesma operação: breakeven e extremos líquidos (ADR-0005 item 4).

    exercício (put exercida) = 0,0002 x 3.000,00 + 2,00        = 2,60
    ganho máximo líquido = 60,00 - 5,03 - 8,2455 (IR)           = 46,7245
    perda máxima líquida = -2.940,00 - 5,03 - 2,60 (sem IR)     = -2.947,63
    breakeven líquido    = 30,00 - 0,60 + (5,03 + 2,60) / 100   = 29,4763
    """
    m = _csp()
    _close(m.net_max_gain_per_position, 46.7245, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -2947.63, "perda máxima líquida")
    _close(m.net_breakeven, 29.4763, "breakeven líquido")


def test_put_coberta_breakeven_liquido_no_salto_do_exercicio() -> None:
    """Prêmio 0,06: (5,003 + 2,60) / 100 = 0,07603 >= 0,06 — o trecho exercido nunca zera.

    O resultado só fica >= 0 em K = 30, onde o exercício some: breakeven = 30.
    ganho máximo líquido = (6,00 - 5,003) x 0,85 = 0,84745
    """
    m = _csp(premium_per_share=0.06)
    _close(m.net_breakeven, 30.0, "breakeven no strike")
    _close(m.net_max_gain_per_position, 0.84745, "ganho máximo líquido")


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
    _close(m.net_breakeven, m.breakeven, "breakeven líquido == bruto")
    _close(m.net_max_gain_per_position, m.max_gain_per_position, "ganho líquido == bruto")
    _close(m.net_max_loss_per_position, m.max_loss_per_position, "perda líquida == bruta")


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
    # Custos > prêmio: o resultado líquido nunca chega a zero.
    assert m.net_breakeven is None
    _close(m.net_max_gain_per_position, -5.0, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -3007.60, "perda máxima líquida")


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
    """Mesma operação, líquida de custos (100 ações; montagem = opção + compra da ação).

    montagem = 0,0005 x 80,00 + 0,0002 x 3.200,00 = 0,68 (emol.) + 2 x 5,00 (corret.)
                                                  = 10,68
    IR       = 0,15 x (80,00 - 10,68) = 0,15 x 69,32 = 10,398
    custos   = 10,68 + 10,398                      = 21,078
    resultado líquido  = 80,00 - 21,078            = 58,922
    rendimento líquido = 58,922 / (32,00 x 100)    = 0,018413125
    anualizado líquido = 1,018413125^6 - 1         = 0,115690991462836284...
    excesso líquido    = 0,1156909914628363 - 0,12 = -0,0043090085371637
    """
    m = _cc()
    _close(m.costs.setup.total, 10.68, "montagem")
    _close(m.costs.total, 21.078, "custos")
    _close(m.net_yield_period, 0.018413125, "rendimento líquido")
    _close(m.net_yield_annual_252, 0.1156909914628362845, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, -0.0043090085371637155, "excesso líquido")


def test_venda_coberta_golden_extremos_liquidos() -> None:
    """Mesma operação: breakeven e extremos líquidos (ADR-0005 itens 3 e 4).

    exercício (call exercida) = 0,0002 x 3.400,00 + 2,00            = 2,68
    ganho máximo antes do IR  = 280,00 - 10,68 - 2,68               = 266,64
    IR só sobre o prêmio      = 0,15 x (80,00 - 5,04 da ordem)      = 11,244
    ganho máximo líquido      = 266,64 - 11,244                     = 255,396
    perda máxima líquida      = -3.120,00 - 10,68 (sem exercício)   = -3.130,68
    breakeven líquido         = 32,00 - 0,80 + 10,68 / 100          = 31,3068
    """
    m = _cc()
    _close(m.net_max_gain_per_position, 255.396, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -3130.68, "perda máxima líquida")
    _close(m.net_breakeven, 31.3068, "breakeven líquido")


def test_venda_coberta_sem_breakeven_liquido_quando_passa_do_strike() -> None:
    """Call ATM K = 32 a 0,05: 32,00 - 0,05 + 10,6425 / 100 = 32,056425 > K.

    Até o strike o resultado não zera, e o exercido é ainda menor: nenhum
    preço zera o líquido. ganho máximo líquido = 5,00 - 10,6425 - 2,64 = -8,2825.
    """
    m = _cc(strike=32.0, premium_per_share=0.05)
    assert m.net_breakeven is None
    _close(m.net_max_gain_per_position, -8.2825, "ganho máximo líquido")


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
    """Prêmio zero: rendimento e proteção nulos; o líquido paga a montagem sem IR.

    montagem = 5,00 (ordem da opção) + 0,64 + 5,00 (compra da ação) = 10,64
    rendimento líquido = -10,64 / 3.200,00 = -0,003325
    """
    m = _cc(premium_per_share=0.0)
    _close(m.yield_period, 0.0, "rendimento")
    _close(m.downside_protection, 0.0, "proteção")
    _close(m.net_yield_period, -0.003325, "rendimento líquido")
    # Sem prêmio ainda há breakeven: a ação sobe até cobrir a montagem.
    _close(m.net_breakeven, 32.1064, "breakeven líquido")
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
# Trava de crédito — decisão da mesa: crédito / (largura - crédito)
# ---------------------------------------------------------------------------


def _bull_put(premiums: tuple[float, float] | None = (0.50, 0.90), quantity: int = 10) -> Strategy:
    """Trava de alta com put: compra put 28 a 0,50, vende put 30 a 0,90."""
    return vertical_spread(make_vertical_legs(premiums=premiums, quantity=quantity))


def _bear_call(premiums: tuple[float, float] = (1.10, 0.35), quantity: int = 10) -> Strategy:
    """Trava de baixa com call: vende call 32 a 1,10, compra call 34 a 0,35."""
    return vertical_spread(
        make_vertical_legs(
            option_type=OptionType.CALL,
            direction=Side.SELL,
            strikes=(32.0, 34.0),
            premiums=premiums,
            quantity=quantity,
        )
    )


def _spread(trava: Strategy, **overrides: Any) -> IncomeMetrics:
    kwargs: dict[str, Any] = {
        "business_days": 63,
        "cdi": make_cdi(0.12),
        "cost_schedule": make_cost_schedule(),
    }
    kwargs.update(overrides)
    return credit_spread_metrics(trava, **kwargs)


def test_trava_de_alta_com_put_golden_bruto() -> None:
    """Compra put 28 a 0,50 e vende put 30 a 0,90, 63 du, CDI 12%.

    crédito               = 0,90 - 0,50                     = 0,40
    largura / risco       = 30 - 28 = 2,00;  2,00 - 0,40    = 1,60
    retorno sobre risco   = 0,40 / 1,60                     = 0,25
    anualizado            = 1,25^(252/63) - 1 = 1,25^4 - 1  = 1,44140625
    excesso sobre o CDI   = 1,44140625 - 0,12               = 1,32140625
    breakeven             = 30 - 0,40                       = 29,60
    ganho máximo          = 0,40 x 100                      = 40,00
    pior resultado        = -1,60 x 100                     = -160,00
    """
    m = _spread(_bull_put())
    assert m.structure is IncomeStructure.CREDIT_SPREAD
    _close(m.premium_per_share, 0.40, "crédito")
    _close(m.capital_base_per_share, 1.60, "risco")
    _close(m.yield_period, 0.25, "retorno sobre risco")
    _close(m.yield_annual_252, 1.44140625, "anualizado")
    _close(m.excess_over_cdi_annual_252, 1.32140625, "excesso")
    _close(m.breakeven, 29.60, "breakeven")
    _close(m.max_gain_per_position, 40.0, "ganho máximo")
    _close(m.max_loss_per_position, -160.0, "pior resultado")
    assert m.downside_protection is None


def test_trava_de_alta_com_put_golden_liquido() -> None:
    """Mesma trava, líquida de custos (100 ações, 2 ordens).

    custos = 0,0005 x (50 + 90) = 0,07 (emol.) + 10,00 (corret.)
             + 0,15 x (40,00 - 10,07) = 4,4895 (IR)            = 14,5595
    resultado líquido   = 40,00 - 14,5595                     = 25,4405
    retorno líquido     = 25,4405 / 160,00                    = 0,159003125
    anualizado líquido  = 1,159003125^4 - 1                   = 0,804423305823195512...
    excesso líquido     = 0,8044233058231955 - 0,12           = 0,6844233058231955
    """
    m = _spread(_bull_put())
    _close(m.costs.total, 14.5595, "custos")
    _close(m.net_yield_period, 0.159003125, "retorno líquido")
    _close(m.net_yield_annual_252, 0.8044233058231955126, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 0.6844233058231955126, "excesso líquido")


def test_trava_de_alta_com_put_golden_extremos_liquidos() -> None:
    """Mesma trava: breakeven e extremos líquidos (ADR-0005 item 4).

    exercício da vendida (put 30)  = 0,0002 x 3.000,00 + 2,00            = 2,60
    exercício das duas (28 e 30)   = 0,0002 x 5.800,00 + 2 x 2,00        = 5,16
    ganho máximo líquido = 40,00 - 10,07 - 4,4895 (IR)                    = 25,4405
    perda máxima líquida = -160,00 - 10,07 - 5,16 (sem IR)                = -175,23
    breakeven líquido    = 30,00 - 0,40 + (10,07 + 2,60) / 100            = 29,7267
    """
    m = _spread(_bull_put())
    _close(m.net_max_gain_per_position, 25.4405, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -175.23, "perda máxima líquida")
    _close(m.net_breakeven, 29.7267, "breakeven líquido")


def test_trava_de_baixa_com_call_golden_bruto_e_liquido() -> None:
    """Vende call 32 a 1,10 e compra call 34 a 0,35, 126 du, CDI 12%.

    crédito = 1,10 - 0,35 = 0,75;  risco = 2,00 - 0,75 = 1,25
    retorno sobre risco = 0,75 / 1,25 = 0,6;  anualizado = 1,6^2 - 1 = 1,56
    excesso = 1,56 - 0,12 = 1,44;  breakeven = 32 + 0,75 = 32,75
    ganho máximo = 75,00;  pior resultado = -125,00
    custos = 0,0005 x (110 + 35) = 0,0725 + 10,00
             + 0,15 x (75,00 - 10,0725) = 9,739125              = 19,811625
    retorno líquido = (75,00 - 19,811625) / 125,00 = 55,188375 / 125 = 0,441507
    anualizado líquido = 1,441507^2 - 1 = 1,077942431049;  excesso = 0,957942431049
    """
    m = _spread(_bear_call(), business_days=126)
    _close(m.premium_per_share, 0.75, "crédito")
    _close(m.yield_period, 0.6, "retorno sobre risco")
    _close(m.yield_annual_252, 1.56, "anualizado")
    _close(m.excess_over_cdi_annual_252, 1.44, "excesso")
    _close(m.breakeven, 32.75, "breakeven")
    _close(m.max_gain_per_position, 75.0, "ganho máximo")
    _close(m.max_loss_per_position, -125.0, "pior resultado")
    _close(m.costs.total, 19.811625, "custos")
    _close(m.net_yield_period, 0.441507, "retorno líquido")
    _close(m.net_yield_annual_252, 1.077942431049, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 0.957942431049, "excesso líquido")


def test_trava_de_baixa_com_call_golden_extremos_liquidos() -> None:
    """Mesma trava: breakeven e extremos líquidos (ADR-0005 item 4).

    exercício da vendida (call 32) = 0,0002 x 3.200,00 + 2,00            = 2,64
    exercício das duas (32 e 34)   = 0,0002 x 6.600,00 + 2 x 2,00        = 5,32
    ganho máximo líquido = 75,00 - 10,0725 - 9,739125 (IR)                = 55,188375
    perda máxima líquida = -125,00 - 10,0725 - 5,32 (sem IR)              = -140,3925
    breakeven líquido    = 32,00 + 0,75 - (10,0725 + 2,64) / 100          = 32,622875
    """
    m = _spread(_bear_call(), business_days=126)
    _close(m.net_max_gain_per_position, 55.188375, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -140.3925, "perda máxima líquida")
    _close(m.net_breakeven, 32.622875, "breakeven líquido")


@pytest.mark.parametrize(
    ("trava", "strike_vendido"),
    [
        (_bull_put(premiums=(0.05, 0.16)), 30.0),
        (_bear_call(premiums=(0.16, 0.05)), 32.0),
    ],
)
def test_trava_breakeven_liquido_no_salto_do_exercicio(
    trava: Strategy, strike_vendido: float
) -> None:
    """Crédito 0,11: (10,0105 + 2,60 ou 2,64) / 100 > 0,11 — o trecho exercido nunca zera.

    O resultado só fica >= 0 no strike vendido, onde o exercício some.
    ganho máximo líquido = (11,00 - 10,0105) x 0,85 = 0,841075
    """
    m = _spread(trava)
    _close(m.net_breakeven, strike_vendido, "breakeven no strike vendido")
    _close(m.net_max_gain_per_position, 0.841075, "ganho máximo líquido")


@pytest.mark.parametrize("trava", [_bull_put(quantity=100), _bear_call(quantity=100)])
def test_trava_bate_com_o_perfil_de_payoff_do_motor(trava: Strategy) -> None:
    """Oráculo independente: breakeven e extremos do kernel de payoff (forma fechada).

    Com 100 contratos nas legs, o perfil do motor está na mesma escala dos
    valores por posição (tamanho de referência de 100 ações).
    """
    m = _spread(trava)
    perfil = payoff_profile(trava, (20.0, 40.0))
    assert perfil.breakevens is not None
    assert len(perfil.breakevens) == 1
    assert_close(
        m.breakeven, perfil.breakevens[0], rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="BE"
    )
    assert perfil.max_gain is not None
    assert perfil.max_loss is not None
    _close(m.max_gain_per_position, perfil.max_gain, "ganho máximo")
    _close(m.max_loss_per_position, perfil.max_loss, "pior resultado")


def test_quantidade_das_legs_nao_muda_as_metricas() -> None:
    """Métricas normalizadas por ação e reescaladas para o tamanho de referência."""
    dez, mil = _spread(_bull_put(quantity=10)), _spread(_bull_put(quantity=1000))
    _close(mil.yield_period, dez.yield_period, "rendimento")
    _close(mil.net_yield_period, dez.net_yield_period, "rendimento líquido")
    _close(mil.max_loss_per_position, dez.max_loss_per_position, "pior resultado")


def test_trava_aceita_estrutura_montada_fora_da_factory() -> None:
    """Legs fora de ordem num Strategy cru: a composição é revalidada e canonizada."""
    cru = Strategy.create("bull put manual", list(reversed(make_vertical_legs())))
    m = _spread(cru)
    _close(m.breakeven, 29.60, "breakeven")


def test_trava_vencendo_hoje_nao_anualiza() -> None:
    m = _spread(_bull_put(), business_days=0)
    _close(m.yield_period, 0.25, "retorno sobre risco")
    assert m.yield_annual_252 is None
    assert m.net_yield_annual_252 is None
    assert m.excess_over_cdi_annual_252 is None
    assert m.net_excess_over_cdi_annual_252 is None


def test_trava_com_credito_zero() -> None:
    """Prêmios iguais: crédito 0, retorno 0, breakeven no strike vendido, risco = largura.

    líquido = -(0,0005 x (50 + 50) + 10,00) / 200,00 = -10,05 / 200 = -0,05025
    """
    m = _spread(_bull_put(premiums=(0.50, 0.50)))
    _close(m.premium_per_share, 0.0, "crédito")
    _close(m.yield_period, 0.0, "retorno")
    _close(m.breakeven, 30.0, "breakeven")
    _close(m.max_loss_per_position, -200.0, "pior resultado")
    _close(m.net_yield_period, -0.05025, "retorno líquido")
    assert m.costs.income_tax == 0.0
    assert m.net_breakeven is None
    _close(m.net_max_loss_per_position, -215.21, "perda máxima líquida")


@pytest.mark.parametrize("premiums", [(0.10, 2.10), (0.10, 2.50)])
def test_trava_com_credito_maior_ou_igual_a_largura_e_inconsistente(
    premiums: tuple[float, float],
) -> None:
    """Crédito >= largura: risco <= 0 (arbitragem/dado inconsistente) -> erro, nunca inf."""
    with pytest.raises(InvalidDomainValueError):
        _spread(_bull_put(premiums=premiums))


def test_trava_de_credito_com_premios_formando_debito_e_inconsistente() -> None:
    """Put 30 vendida mais barata que a put 28 comprada: viola não-arbitragem."""
    with pytest.raises(InvalidDomainValueError):
        _spread(_bull_put(premiums=(0.50, 0.40)))


@pytest.mark.parametrize(
    ("option_type", "strikes", "premiums"),
    [
        (OptionType.PUT, (28.0, 30.0), (0.50, 0.90)),  # trava de baixa com put
        (OptionType.CALL, (32.0, 34.0), (1.10, 0.35)),  # trava de alta com call
    ],
)
def test_trava_de_debito_nao_tem_metrica_de_credito(
    option_type: OptionType, strikes: tuple[float, float], premiums: tuple[float, float]
) -> None:
    debito = vertical_spread(
        make_vertical_legs(
            option_type=option_type, direction=Side.BUY, strikes=strikes, premiums=premiums
        )
    )
    with pytest.raises(InvalidStrategyError):
        _spread(debito)


def test_estrutura_que_nao_e_trava_e_rejeitada() -> None:
    straddle = Strategy.create("straddle", make_straddle_legs(direction=Side.SELL))
    with pytest.raises(InvalidStrategyError):
        _spread(straddle)


def test_trava_sem_premio_nao_tem_metrica() -> None:
    with pytest.raises(MissingPremiumError):
        _spread(_bull_put(premiums=None))


@pytest.mark.parametrize(
    "overrides",
    [
        {"business_days": -1},
        {"reference_shares": 0},
        {"cdi": RiskFreeRate(0.12, Compounding.CONTINUOUS)},
    ],
)
def test_trava_entradas_invalidas(overrides: dict[str, Any]) -> None:
    with pytest.raises(InvalidDomainValueError):
        _spread(_bull_put(), **overrides)


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
        {"net_breakeven": float("nan")},
        {"net_max_gain_per_position": float("inf")},
        {"net_max_loss_per_position": float("nan")},
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
    option_exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    spot_exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    brokerage_per_order=st.floats(min_value=0.0, max_value=50.0),
    exercise_brokerage_per_order=st.floats(min_value=0.0, max_value=50.0),
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
        option_exchange_fee_rate=barata.option_exchange_fee_rate
        + acrescimo.option_exchange_fee_rate,
        spot_exchange_fee_rate=barata.spot_exchange_fee_rate + acrescimo.spot_exchange_fee_rate,
        brokerage_per_order=barata.brokerage_per_order + acrescimo.brokerage_per_order,
        exercise_brokerage_per_order=barata.exercise_brokerage_per_order
        + acrescimo.exercise_brokerage_per_order,
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


# Travas: corretagem pequena frente ao crédito (largura >= 0,50, crédito >=
# 10% da largura) — mantém o retorno líquido acima de -100% (anualizável) e,
# no teste de prêmio, o resultado líquido >= 0, região onde o retorno sobre
# risco líquido é monótono no crédito (com resultado NEGATIVO, encolher o
# risco torna a razão mais negativa — propriedade da razão, não bug).
_largura = st.integers(min_value=50, max_value=1_000).map(lambda centavos: centavos / 100.0)
_fracao_da_largura = st.floats(min_value=0.1, max_value=0.9)
_premio_comprado = st.integers(min_value=0, max_value=200).map(lambda centavos: centavos / 100.0)
_tabela_trava = st.builds(
    make_cost_schedule,
    option_exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    spot_exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    brokerage_per_order=st.floats(min_value=0.0, max_value=2.0),
    exercise_brokerage_per_order=st.floats(min_value=0.0, max_value=2.0),
    income_tax_rate=st.floats(min_value=0.0, max_value=0.3),
)


def _trava_de_credito(
    option_type: OptionType, largura: float, credito: float, premio_comprado: float
) -> Strategy:
    """Trava de crédito com strike baixo 30 e prêmio vendido = comprado + crédito."""
    vendido = premio_comprado + credito
    premios = (
        (premio_comprado, vendido) if option_type is OptionType.PUT else (vendido, premio_comprado)
    )
    return vertical_spread(
        make_vertical_legs(
            option_type=option_type,
            direction=Side.SELL,
            strikes=(30.0, 30.0 + largura),
            premiums=premios,
        )
    )


@given(
    option_type=st.sampled_from([OptionType.PUT, OptionType.CALL]),
    largura=_largura,
    f1=_fracao_da_largura,
    f2=_fracao_da_largura,
    premio_comprado=_premio_comprado,
    du=_du,
    tabela=_tabela_trava,
)
def test_trava_mais_credito_mais_retorno(
    option_type: OptionType,
    largura: float,
    f1: float,
    f2: float,
    premio_comprado: float,
    du: int,
    tabela: CostSchedule,
) -> None:
    baixo, alto = sorted((f1 * largura, f2 * largura))
    menor = _spread(
        _trava_de_credito(option_type, largura, baixo, premio_comprado),
        business_days=du,
        cost_schedule=tabela,
    )
    assume(menor.net_yield_period >= 0.0)
    maior = _spread(
        _trava_de_credito(option_type, largura, alto, premio_comprado),
        business_days=du,
        cost_schedule=tabela,
    )
    _assert_todos_nao_pioram(menor, maior)


@given(
    option_type=st.sampled_from([OptionType.PUT, OptionType.CALL]),
    largura=_largura,
    fracao=_fracao_da_largura,
    premio_comprado=_premio_comprado,
    du=_du,
    barata=_tabela_trava,
    acrescimo=_tabela_trava,
)
def test_trava_mais_custo_menos_liquido(
    option_type: OptionType,
    largura: float,
    fracao: float,
    premio_comprado: float,
    du: int,
    barata: CostSchedule,
    acrescimo: CostSchedule,
) -> None:
    trava = _trava_de_credito(option_type, largura, fracao * largura, premio_comprado)
    m_barata = _spread(trava, business_days=du, cost_schedule=barata)
    m_cara = _spread(trava, business_days=du, cost_schedule=_somar_tabelas(barata, acrescimo))
    _assert_todos_nao_pioram(m_cara, m_barata)
    _close(m_cara.yield_period, m_barata.yield_period, "bruto independe do custo")

"""Custos de operação — ``CostSchedule`` validada e cálculo em forma fechada.

Oráculo: aritmética à mão sobre a tabela ILUSTRATIVA dos builders
(emolumentos 0,05% do valor financeiro do prêmio, corretagem 5,00 por
ordem, IR 15% sobre o ganho positivo). Tolerâncias de ``tests/_tolerances.py``.
"""

from dataclasses import FrozenInstanceError
from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.income.costs import (
    REFERENCE_POSITION_SHARES,
    CostSchedule,
    OperationCosts,
    estimate_operation_costs,
)
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import ABS_INCOME, INEQ_SLACK, REL_INCOME, assert_close
from tests.income._builders import make_cost_schedule, zero_cost_schedule

# ---------------------------------------------------------------------------
# CostSchedule — VO com vigência
# ---------------------------------------------------------------------------


def test_tabela_carrega_vigencia_e_parametros() -> None:
    tabela = CostSchedule(
        valid_from=date(2026, 3, 2),
        exchange_fee_rate=0.0005,
        brokerage_per_order=5.0,
        income_tax_rate=0.15,
    )
    assert tabela.valid_from == date(2026, 3, 2)
    # Valores armazenados e relidos sem aritmética: == permitido.
    assert tabela.exchange_fee_rate == 0.0005
    assert tabela.brokerage_per_order == 5.0
    assert tabela.income_tax_rate == 0.15
    assert tabela == make_cost_schedule(valid_from=date(2026, 3, 2))


def test_tabela_sem_custo_e_legal() -> None:
    tabela = zero_cost_schedule()
    assert (tabela.exchange_fee_rate, tabela.brokerage_per_order, tabela.income_tax_rate) == (
        0.0,
        0.0,
        0.0,
    )


def test_tabela_e_imutavel() -> None:
    tabela = make_cost_schedule()
    with pytest.raises(FrozenInstanceError):
        tabela.income_tax_rate = 0.20  # type: ignore[misc]


_ILEGAIS_FRACAO = [float("nan"), float("inf"), -0.01, 1.0, 1.5]


@pytest.mark.parametrize("taxa", _ILEGAIS_FRACAO)
def test_emolumento_fora_de_0_1_e_irrepresentavel(taxa: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_cost_schedule(exchange_fee_rate=taxa)


@pytest.mark.parametrize("taxa", _ILEGAIS_FRACAO)
def test_aliquota_de_ir_fora_de_0_1_e_irrepresentavel(taxa: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_cost_schedule(income_tax_rate=taxa)


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.01])
def test_corretagem_negativa_ou_nao_finita_e_irrepresentavel(valor: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_cost_schedule(brokerage_per_order=valor)


# ---------------------------------------------------------------------------
# OperationCosts — VO de resultado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["exchange_fees", "brokerage", "income_tax"])
@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.01])
def test_custo_negativo_ou_nao_finito_e_irrepresentavel(campo: str, valor: float) -> None:
    componentes = {"exchange_fees": 0.0, "brokerage": 0.0, "income_tax": 0.0, campo: valor}
    with pytest.raises(InvalidDomainValueError):
        OperationCosts(schedule=make_cost_schedule(), **componentes)


# ---------------------------------------------------------------------------
# estimate_operation_costs — golden cases calculados à mão
# ---------------------------------------------------------------------------


def test_tamanho_de_referencia_e_100_acoes() -> None:
    assert REFERENCE_POSITION_SHARES == 100


def test_golden_uma_perna_put_coberta() -> None:
    """Venda de 100 puts a 0,60 (ganho bruto 60,00).

    emolumentos = 0,0005 x (0,60 x 100)        = 0,03
    corretagem  = 5,00 x 1 ordem                = 5,00
    IR          = 0,15 x (60,00 - 0,03 - 5,00)  = 0,15 x 54,97 = 8,2455
    total       = 0,03 + 5,00 + 8,2455          = 13,2755
    """
    custos = estimate_operation_costs(
        make_cost_schedule(), leg_premiums_per_share=[0.60], gross_gain=60.0
    )
    assert_close(custos.exchange_fees, 0.03, rel=REL_INCOME, abs_=ABS_INCOME, label="emolumentos")
    assert_close(custos.brokerage, 5.0, rel=REL_INCOME, abs_=ABS_INCOME, label="corretagem")
    assert_close(custos.income_tax, 8.2455, rel=REL_INCOME, abs_=ABS_INCOME, label="IR")
    assert_close(custos.total, 13.2755, rel=REL_INCOME, abs_=ABS_INCOME, label="total")
    assert custos.schedule == make_cost_schedule()


def test_golden_duas_pernas_emolumento_sobre_cada_perna() -> None:
    """Trava: compra put a 0,50 e vende put a 0,90 (crédito 0,40 -> 40,00).

    Emolumento incide sobre o valor financeiro de CADA perna, não do líquido:
    emolumentos = 0,0005 x (50,00 + 90,00)       = 0,07
    corretagem  = 5,00 x 2 ordens                = 10,00
    IR          = 0,15 x (40,00 - 0,07 - 10,00)  = 0,15 x 29,93 = 4,4895
    total       = 0,07 + 10,00 + 4,4895          = 14,5595
    """
    custos = estimate_operation_costs(
        make_cost_schedule(), leg_premiums_per_share=[0.50, 0.90], gross_gain=40.0
    )
    assert_close(custos.exchange_fees, 0.07, rel=REL_INCOME, abs_=ABS_INCOME, label="emolumentos")
    assert_close(custos.brokerage, 10.0, rel=REL_INCOME, abs_=ABS_INCOME, label="corretagem")
    assert_close(custos.income_tax, 4.4895, rel=REL_INCOME, abs_=ABS_INCOME, label="IR")
    assert_close(custos.total, 14.5595, rel=REL_INCOME, abs_=ABS_INCOME, label="total")


def test_tamanho_da_posicao_escala_emolumento_mas_nao_corretagem() -> None:
    """Corretagem fixa por ordem não escala com o tamanho — por isso o tamanho é parâmetro."""
    custos = estimate_operation_costs(
        make_cost_schedule(), leg_premiums_per_share=[0.60], gross_gain=600.0, shares=1000
    )
    assert_close(custos.exchange_fees, 0.30, rel=REL_INCOME, abs_=ABS_INCOME, label="emolumentos")
    assert_close(custos.brokerage, 5.0, rel=REL_INCOME, abs_=ABS_INCOME, label="corretagem")


@pytest.mark.parametrize("ganho", [3.0, 0.0, -25.0])
def test_sem_ganho_positivo_depois_dos_custos_nao_ha_ir(ganho: float) -> None:
    """Ganho 3,00 < custos 5,0015: base do IR negativa -> IR = 0 (estimativa por operação)."""
    custos = estimate_operation_costs(
        make_cost_schedule(), leg_premiums_per_share=[0.03], gross_gain=ganho
    )
    # Ramo fechado max(base, 0) = 0.0 multiplicado pela alíquota: == permitido.
    assert custos.income_tax == 0.0


def test_premio_zero_ainda_paga_corretagem() -> None:
    custos = estimate_operation_costs(
        make_cost_schedule(), leg_premiums_per_share=[0.0], gross_gain=0.0
    )
    assert custos.exchange_fees == 0.0
    assert_close(custos.total, 5.0, rel=REL_INCOME, abs_=ABS_INCOME, label="só corretagem")


def test_tabela_sem_custo_zera_tudo() -> None:
    custos = estimate_operation_costs(
        zero_cost_schedule(), leg_premiums_per_share=[0.50, 0.90], gross_gain=40.0
    )
    assert custos.total == 0.0


@pytest.mark.parametrize(
    "premios",
    [[], [-0.01], [float("nan")], [0.5, float("inf")]],
)
def test_pernas_invalidas_sao_rejeitadas(premios: list[float]) -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_operation_costs(
            make_cost_schedule(), leg_premiums_per_share=premios, gross_gain=10.0
        )


def test_tamanho_de_posicao_nao_positivo_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_operation_costs(
            make_cost_schedule(), leg_premiums_per_share=[0.60], gross_gain=60.0, shares=0
        )


@pytest.mark.parametrize("ganho", [float("nan"), float("inf"), float("-inf")])
def test_ganho_nao_finito_e_rejeitado(ganho: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_operation_costs(
            make_cost_schedule(), leg_premiums_per_share=[0.60], gross_gain=ganho
        )


# ---------------------------------------------------------------------------
# Propriedades — custo nunca negativo e monótono em cada parâmetro da tabela
# ---------------------------------------------------------------------------

_taxa = st.floats(min_value=0.0, max_value=0.5, allow_nan=False)
_corretagem = st.floats(min_value=0.0, max_value=50.0, allow_nan=False)
_premios = st.lists(
    st.integers(min_value=0, max_value=1000).map(lambda centavos: centavos / 100.0),
    min_size=1,
    max_size=4,
)
_ganho = st.floats(min_value=-1_000.0, max_value=1_000.0, allow_nan=False)
_acoes = st.integers(min_value=1, max_value=1_000)


@given(fee=_taxa, corretagem=_corretagem, ir=_taxa, premios=_premios, ganho=_ganho, acoes=_acoes)
def test_componentes_nao_negativos_e_total_e_a_soma(
    fee: float, corretagem: float, ir: float, premios: list[float], ganho: float, acoes: int
) -> None:
    tabela = make_cost_schedule(
        exchange_fee_rate=fee, brokerage_per_order=corretagem, income_tax_rate=ir
    )
    custos = estimate_operation_costs(
        tabela, leg_premiums_per_share=premios, gross_gain=ganho, shares=acoes
    )
    assert min(custos.exchange_fees, custos.brokerage, custos.income_tax) >= 0.0
    assert_close(
        custos.total,
        custos.exchange_fees + custos.brokerage + custos.income_tax,
        rel=REL_INCOME,
        abs_=ABS_INCOME,
        label="total",
    )
    # O IR nunca excede a alíquota sobre o ganho bruto: custos só reduzem a base.
    assert custos.income_tax <= ir * max(ganho, 0.0) + INEQ_SLACK


@given(
    base=st.tuples(_taxa, _corretagem, _taxa),
    acrescimo=st.tuples(_taxa, _corretagem, _taxa),
    premios=_premios,
    ganho=_ganho,
)
def test_mais_custo_na_tabela_nunca_reduz_o_custo_total(
    base: tuple[float, float, float],
    acrescimo: tuple[float, float, float],
    premios: list[float],
    ganho: float,
) -> None:
    """Monotonia: subir emolumento, corretagem ou alíquota nunca barateia a operação."""
    barata = make_cost_schedule(
        exchange_fee_rate=base[0], brokerage_per_order=base[1], income_tax_rate=base[2]
    )
    cara = make_cost_schedule(
        exchange_fee_rate=min(base[0] + acrescimo[0], 0.99),
        brokerage_per_order=base[1] + acrescimo[1],
        income_tax_rate=min(base[2] + acrescimo[2], 0.99),
    )
    custo_barato = estimate_operation_costs(
        barata, leg_premiums_per_share=premios, gross_gain=ganho
    )
    custo_caro = estimate_operation_costs(cara, leg_premiums_per_share=premios, gross_gain=ganho)
    escala = max(1.0, abs(ganho), custo_caro.total)
    assert custo_caro.total >= custo_barato.total - INEQ_SLACK * escala

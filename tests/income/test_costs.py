"""Custos de operação — ``CostSchedule`` validada e cálculo em forma fechada.

Oráculo: aritmética à mão sobre a tabela ILUSTRATIVA dos builders
(emolumentos de opções 0,05% do valor financeiro do prêmio, emolumentos do
à vista 0,02%, corretagem 5,00 por ordem, corretagem de exercício 2,00, IR
15% sobre o ganho positivo). Tolerâncias de ``tests/_tolerances.py``.
"""

from dataclasses import FrozenInstanceError
from datetime import date
from math import fsum
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.income.costs import (
    REFERENCE_POSITION_SHARES,
    CostSchedule,
    OperationCosts,
    OrderCosts,
    estimate_exercise_costs,
    estimate_income_tax,
    estimate_setup_costs,
)
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import ABS_INCOME, INEQ_SLACK, REL_INCOME, assert_close
from tests.income._builders import make_cost_schedule, zero_cost_schedule


def _close(actual: float, expected: float, label: str) -> None:
    assert_close(actual, expected, rel=REL_INCOME, abs_=ABS_INCOME, label=label)


# ---------------------------------------------------------------------------
# CostSchedule — VO com vigência
# ---------------------------------------------------------------------------


def test_tabela_carrega_vigencia_e_parametros() -> None:
    tabela = CostSchedule(
        valid_from=date(2026, 3, 2),
        option_exchange_fee_rate=0.0005,
        spot_exchange_fee_rate=0.0002,
        brokerage_per_order=5.0,
        exercise_brokerage_per_order=2.0,
        income_tax_rate=0.15,
    )
    assert tabela.valid_from == date(2026, 3, 2)
    # Valores armazenados e relidos sem aritmética: == permitido.
    assert tabela.option_exchange_fee_rate == 0.0005
    assert tabela.spot_exchange_fee_rate == 0.0002
    assert tabela.brokerage_per_order == 5.0
    assert tabela.exercise_brokerage_per_order == 2.0
    assert tabela.income_tax_rate == 0.15
    assert tabela == make_cost_schedule(valid_from=date(2026, 3, 2))


def test_tabela_sem_custo_e_legal() -> None:
    tabela = zero_cost_schedule()
    assert (
        tabela.option_exchange_fee_rate,
        tabela.spot_exchange_fee_rate,
        tabela.brokerage_per_order,
        tabela.exercise_brokerage_per_order,
        tabela.income_tax_rate,
    ) == (0.0, 0.0, 0.0, 0.0, 0.0)


def test_tabela_e_imutavel() -> None:
    tabela = make_cost_schedule()
    with pytest.raises(FrozenInstanceError):
        tabela.income_tax_rate = 0.20  # type: ignore[misc]


_ILEGAIS_FRACAO = [float("nan"), float("inf"), -0.01, 1.0, 1.5]


@pytest.mark.parametrize("campo", ["option_exchange_fee_rate", "spot_exchange_fee_rate"])
@pytest.mark.parametrize("taxa", _ILEGAIS_FRACAO)
def test_emolumento_fora_de_0_1_e_irrepresentavel(campo: str, taxa: float) -> None:
    with pytest.raises(InvalidDomainValueError, match=campo):
        parametros: dict[str, Any] = {campo: taxa}
        make_cost_schedule(**parametros)


@pytest.mark.parametrize("taxa", _ILEGAIS_FRACAO)
def test_aliquota_de_ir_fora_de_0_1_e_irrepresentavel(taxa: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_cost_schedule(income_tax_rate=taxa)


@pytest.mark.parametrize("campo", ["brokerage_per_order", "exercise_brokerage_per_order"])
@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.01])
def test_corretagem_negativa_ou_nao_finita_e_irrepresentavel(campo: str, valor: float) -> None:
    with pytest.raises(InvalidDomainValueError, match=campo):
        parametros: dict[str, Any] = {campo: valor}
        make_cost_schedule(**parametros)


# ---------------------------------------------------------------------------
# OrderCosts e OperationCosts — VOs de resultado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("campo", ["exchange_fees", "brokerage"])
@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.01])
def test_custo_de_ordem_negativo_ou_nao_finito_e_irrepresentavel(campo: str, valor: float) -> None:
    componentes = {"exchange_fees": 0.0, "brokerage": 0.0, campo: valor}
    with pytest.raises(InvalidDomainValueError):
        OrderCosts(schedule=make_cost_schedule(), **componentes)


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.01])
def test_ir_negativo_ou_nao_finito_e_irrepresentavel(valor: float) -> None:
    montagem = OrderCosts(schedule=make_cost_schedule(), exchange_fees=0.0, brokerage=0.0)
    with pytest.raises(InvalidDomainValueError):
        OperationCosts(setup=montagem, income_tax=valor)


def test_custos_da_operacao_somam_montagem_e_ir_e_carregam_a_tabela() -> None:
    montagem = OrderCosts(schedule=make_cost_schedule(), exchange_fees=0.03, brokerage=5.0)
    custos = OperationCosts(setup=montagem, income_tax=8.2455)
    _close(montagem.total, 5.03, "montagem")
    _close(custos.total, 13.2755, "montagem + IR")
    assert custos.schedule == make_cost_schedule()


# ---------------------------------------------------------------------------
# estimate_setup_costs — golden cases calculados à mão
# ---------------------------------------------------------------------------


def test_tamanho_de_referencia_e_100_acoes() -> None:
    assert REFERENCE_POSITION_SHARES == 100


def test_golden_montagem_uma_perna_put_coberta() -> None:
    """Venda de 100 puts a 0,60.

    emolumentos = 0,0005 x (0,60 x 100) = 0,03
    corretagem  = 5,00 x 1 ordem        = 5,00
    """
    montagem = estimate_setup_costs(make_cost_schedule(), option_leg_premiums_per_share=[0.60])
    _close(montagem.exchange_fees, 0.03, "emolumentos")
    _close(montagem.brokerage, 5.0, "corretagem")
    _close(montagem.total, 5.03, "total")
    assert montagem.schedule == make_cost_schedule()


def test_golden_montagem_duas_pernas_emolumento_sobre_cada_perna() -> None:
    """Trava: compra put a 0,50 e vende put a 0,90.

    Emolumento incide sobre o valor financeiro de CADA perna, não do líquido:
    emolumentos = 0,0005 x (50,00 + 90,00) = 0,07
    corretagem  = 5,00 x 2 ordens          = 10,00
    """
    montagem = estimate_setup_costs(
        make_cost_schedule(), option_leg_premiums_per_share=[0.50, 0.90]
    )
    _close(montagem.exchange_fees, 0.07, "emolumentos")
    _close(montagem.brokerage, 10.0, "corretagem")


def test_golden_montagem_venda_coberta_paga_a_compra_da_acao() -> None:
    """Compra 100 ações a 32,00 e vende 100 calls a 0,80 (ADR-0005 item 3).

    emolumentos = 0,0005 x 80,00 (opção) + 0,0002 x 3.200,00 (à vista)
                = 0,04 + 0,64                                = 0,68
    corretagem  = 5,00 x 2 ordens (opção + ação)             = 10,00
    """
    montagem = estimate_setup_costs(
        make_cost_schedule(),
        option_leg_premiums_per_share=[0.80],
        stock_purchase_price_per_share=32.0,
    )
    _close(montagem.exchange_fees, 0.68, "emolumentos")
    _close(montagem.brokerage, 10.0, "corretagem")
    _close(montagem.total, 10.68, "total")


def test_tamanho_da_posicao_escala_emolumento_mas_nao_corretagem() -> None:
    """Corretagem fixa por ordem não escala com o tamanho — por isso o tamanho é parâmetro."""
    montagem = estimate_setup_costs(
        make_cost_schedule(), option_leg_premiums_per_share=[0.60], shares=1000
    )
    _close(montagem.exchange_fees, 0.30, "emolumentos")
    _close(montagem.brokerage, 5.0, "corretagem")


def test_premio_zero_ainda_paga_corretagem() -> None:
    montagem = estimate_setup_costs(make_cost_schedule(), option_leg_premiums_per_share=[0.0])
    assert montagem.exchange_fees == 0.0
    _close(montagem.total, 5.0, "só corretagem")


def test_tabela_sem_custo_zera_a_montagem() -> None:
    montagem = estimate_setup_costs(
        zero_cost_schedule(),
        option_leg_premiums_per_share=[0.50, 0.90],
        stock_purchase_price_per_share=32.0,
    )
    assert montagem.total == 0.0


@pytest.mark.parametrize(
    "premios",
    [[], [-0.01], [float("nan")], [0.5, float("inf")]],
)
def test_pernas_invalidas_sao_rejeitadas(premios: list[float]) -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_setup_costs(make_cost_schedule(), option_leg_premiums_per_share=premios)


@pytest.mark.parametrize("preco", [0.0, -32.0, float("nan"), float("inf")])
def test_preco_de_compra_da_acao_invalido_e_rejeitado(preco: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_setup_costs(
            make_cost_schedule(),
            option_leg_premiums_per_share=[0.80],
            stock_purchase_price_per_share=preco,
        )


def test_tamanho_de_posicao_nao_positivo_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_setup_costs(make_cost_schedule(), option_leg_premiums_per_share=[0.60], shares=0)


# ---------------------------------------------------------------------------
# estimate_exercise_costs — golden cases calculados à mão
# ---------------------------------------------------------------------------


def test_golden_exercicio_de_uma_perna() -> None:
    """Put 30 exercida, 100 ações: compra ao strike pela tabela do à vista.

    emolumentos = 0,0002 x (30,00 x 100) = 0,60
    corretagem  = 2,00 x 1 exercício     = 2,00
    """
    exercicio = estimate_exercise_costs(make_cost_schedule(), exercised_strikes=[30.0])
    _close(exercicio.exchange_fees, 0.60, "emolumentos")
    _close(exercicio.brokerage, 2.0, "corretagem")
    _close(exercicio.total, 2.60, "total")


def test_golden_exercicio_das_duas_pernas_de_uma_trava() -> None:
    """Trava 28/30 com as duas pernas dentro do dinheiro.

    emolumentos = 0,0002 x (2.800,00 + 3.000,00) = 1,16
    corretagem  = 2,00 x 2 exercícios            = 4,00
    """
    exercicio = estimate_exercise_costs(make_cost_schedule(), exercised_strikes=[28.0, 30.0])
    _close(exercicio.exchange_fees, 1.16, "emolumentos")
    _close(exercicio.brokerage, 4.0, "corretagem")


def test_cenario_sem_exercicio_nao_custa_nada() -> None:
    exercicio = estimate_exercise_costs(make_cost_schedule(), exercised_strikes=[])
    assert exercicio.total == 0.0


@pytest.mark.parametrize("strikes", [[0.0], [-30.0], [float("nan")], [30.0, float("inf")]])
def test_strike_exercido_invalido_e_rejeitado(strikes: list[float]) -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_exercise_costs(make_cost_schedule(), exercised_strikes=strikes)


def test_exercicio_com_tamanho_nao_positivo_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        estimate_exercise_costs(make_cost_schedule(), exercised_strikes=[30.0], shares=0)


# ---------------------------------------------------------------------------
# estimate_income_tax — IR sobre o resultado positivo, limitado ao prêmio
# ---------------------------------------------------------------------------


def test_golden_ir_sobre_o_resultado_do_cenario() -> None:
    """Put coberta que vira pó: 60,00 - 5,03 de montagem = 54,97; IR = 0,15 x 54,97."""
    imposto = estimate_income_tax(make_cost_schedule(), pre_tax_result=54.97, premium_result=54.97)
    _close(imposto, 8.2455, "IR")


def test_golden_ir_limitado_ao_resultado_do_premio() -> None:
    """Venda coberta exercida: resultado 266,64, prêmio 80,00 - 5,04 da ordem = 74,96.

    A valorização da ação fica fora (ADR-0005, escolha 2): IR = 0,15 x 74,96 = 11,244.
    """
    imposto = estimate_income_tax(make_cost_schedule(), pre_tax_result=266.64, premium_result=74.96)
    _close(imposto, 11.244, "IR só sobre o prêmio")


def test_perda_da_acao_abate_a_base_do_ir() -> None:
    """Resultado 30,00 abaixo do prêmio 74,96: IR = 0,15 x 30,00 = 4,50."""
    imposto = estimate_income_tax(make_cost_schedule(), pre_tax_result=30.0, premium_result=74.96)
    _close(imposto, 4.5, "IR sobre o resultado")


@pytest.mark.parametrize(
    ("resultado", "premio"), [(0.0, 54.97), (-25.0, 54.97), (30.0, -2.0), (-1.0, -1.0)]
)
def test_sem_resultado_positivo_nao_ha_ir(resultado: float, premio: float) -> None:
    imposto = estimate_income_tax(
        make_cost_schedule(), pre_tax_result=resultado, premium_result=premio
    )
    # Ramo fechado max(base, 0) = 0.0 multiplicado pela alíquota: == permitido.
    assert imposto == 0.0


@pytest.mark.parametrize("campo", ["pre_tax_result", "premium_result"])
@pytest.mark.parametrize("valor", [float("nan"), float("inf"), float("-inf")])
def test_resultado_nao_finito_e_rejeitado(campo: str, valor: float) -> None:
    resultados = {"pre_tax_result": 10.0, "premium_result": 10.0, campo: valor}
    with pytest.raises(InvalidDomainValueError, match=campo):
        estimate_income_tax(make_cost_schedule(), **resultados)


# ---------------------------------------------------------------------------
# Propriedades — custo nunca negativo e monótono em cada parâmetro da tabela
# ---------------------------------------------------------------------------

_taxa = st.floats(min_value=0.0, max_value=0.5, allow_nan=False)
_corretagem = st.floats(min_value=0.0, max_value=50.0, allow_nan=False)
_centavos = st.integers(min_value=0, max_value=1000).map(lambda centavos: centavos / 100.0)
_premios = st.lists(_centavos, min_size=1, max_size=4)
_strikes = st.lists(_centavos.map(lambda k: k + 1.0), min_size=0, max_size=2)
_acao = st.none() | _centavos.map(lambda preco: preco + 1.0)
_resultado = st.floats(min_value=-1_000.0, max_value=1_000.0, allow_nan=False)
_acoes = st.integers(min_value=1, max_value=1_000)
_tabela = st.builds(
    make_cost_schedule,
    option_exchange_fee_rate=_taxa,
    spot_exchange_fee_rate=_taxa,
    brokerage_per_order=_corretagem,
    exercise_brokerage_per_order=_corretagem,
    income_tax_rate=_taxa,
)


@given(tabela=_tabela, premios=_premios, acao=_acao, strikes=_strikes, acoes=_acoes)
def test_componentes_nao_negativos_e_total_e_a_soma(
    tabela: CostSchedule,
    premios: list[float],
    acao: float | None,
    strikes: list[float],
    acoes: int,
) -> None:
    montagem = estimate_setup_costs(
        tabela,
        option_leg_premiums_per_share=premios,
        stock_purchase_price_per_share=acao,
        shares=acoes,
    )
    exercicio = estimate_exercise_costs(tabela, exercised_strikes=strikes, shares=acoes)
    for custo in (montagem, exercicio):
        assert min(custo.exchange_fees, custo.brokerage) >= 0.0
        _close(custo.total, custo.exchange_fees + custo.brokerage, "total")


@given(tabela=_tabela, resultado=_resultado, premio=_resultado)
def test_ir_nunca_passa_da_aliquota_sobre_o_resultado_nem_sobre_o_premio(
    tabela: CostSchedule, resultado: float, premio: float
) -> None:
    imposto = estimate_income_tax(tabela, pre_tax_result=resultado, premium_result=premio)
    t = tabela.income_tax_rate
    assert imposto >= 0.0
    assert imposto <= t * max(resultado, 0.0) + INEQ_SLACK
    assert imposto <= t * max(premio, 0.0) + INEQ_SLACK


def _somar(barata: CostSchedule, acrescimo: CostSchedule) -> CostSchedule:
    return make_cost_schedule(
        option_exchange_fee_rate=min(
            barata.option_exchange_fee_rate + acrescimo.option_exchange_fee_rate, 0.99
        ),
        spot_exchange_fee_rate=min(
            barata.spot_exchange_fee_rate + acrescimo.spot_exchange_fee_rate, 0.99
        ),
        brokerage_per_order=barata.brokerage_per_order + acrescimo.brokerage_per_order,
        exercise_brokerage_per_order=barata.exercise_brokerage_per_order
        + acrescimo.exercise_brokerage_per_order,
        income_tax_rate=min(barata.income_tax_rate + acrescimo.income_tax_rate, 0.99),
    )


@given(
    barata=_tabela,
    acrescimo=_tabela,
    premios=_premios,
    acao=_acao,
    strikes=_strikes,
    receita=_resultado,
)
def test_mais_custo_na_tabela_nunca_reduz_o_custo(
    barata: CostSchedule,
    acrescimo: CostSchedule,
    premios: list[float],
    acao: float | None,
    strikes: list[float],
    receita: float,
) -> None:
    """Monotonia: subir qualquer parâmetro nunca barateia montagem, exercício ou o total.

    O total do cenário de rendimento é montagem + IR(receita - montagem): com
    alíquota < 1, custo a mais na montagem reduz o IR em menos do que soma.
    """
    cara = _somar(barata, acrescimo)

    def custos(tabela: CostSchedule) -> tuple[float, float, float]:
        montagem = estimate_setup_costs(
            tabela, option_leg_premiums_per_share=premios, stock_purchase_price_per_share=acao
        )
        exercicio = estimate_exercise_costs(tabela, exercised_strikes=strikes)
        antes_do_ir = fsum((receita, -montagem.total))
        imposto = estimate_income_tax(
            tabela, pre_tax_result=antes_do_ir, premium_result=antes_do_ir
        )
        return montagem.total, exercicio.total, fsum((montagem.total, imposto))

    for nome, barato, caro in zip(
        ("montagem", "exercício", "montagem + IR"), custos(barata), custos(cara), strict=True
    ):
        escala = max(1.0, abs(receita), caro)
        assert caro >= barato - INEQ_SLACK * escala, f"{nome}: {caro} < {barato}"

"""Strike ajustado pela B3 (tarefa 1.5): o evento de ajuste e a regra de quando aplicá-lo."""

import math

import pytest

from options_engine.domain.income.costs import estimate_exercise_costs_by_leg
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.adjustment import (
    MAX_PROVENTO_DROP,
    StrikeChange,
    strike_change,
)
from options_engine.domain.portfolio.exercise import apply_exercise
from options_engine.domain.portfolio.model import Close, Exercise, Open, StrikeAdjusted
from options_engine.domain.portfolio.positions import leg_states, open_legs, realized_result
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import D1, D2, D3, acao, call, operacao, put

_V, _C = Side.SELL, Side.BUY
FONTE = "Cadastro da B3 de 05/11/2026"


def test_ajuste_muda_o_strike_em_vigor_e_guarda_a_perna_gravada() -> None:
    op = operacao(
        [call(30.0)], [Open(0, D1, _V, 100, 1.0), StrikeAdjusted(0, D2, 30.0, 29.47, FONTE)]
    )
    (perna,) = leg_states(op)
    assert perna.ref.terms.strike == 29.47  # type: ignore[union-attr]
    assert op.legs[0].terms.strike == 30.0  # type: ignore[union-attr]
    assert (perna.side, perna.quantity, perna.average_price) == (_V, 100, 1.0)


def test_dois_ajustes_seguidos_partem_do_strike_em_vigor() -> None:
    op = operacao(
        [call(30.0)],
        [
            Open(0, D1, _V, 100, 1.0),
            StrikeAdjusted(0, D2, 30.0, 29.47, FONTE),
            StrikeAdjusted(0, D3, 29.47, 29.0, "Cadastro da B3 de 10/11/2026"),
        ],
    )
    assert open_legs(op)[0].ref.terms.strike == 29.0  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("pernas", "eventos", "motivo"),
    [
        (
            [call(30.0)],
            [Open(0, D1, _V, 100, 1.0), StrikeAdjusted(0, D2, 31.0, 29.47, FONTE)],
            "anterior",
        ),
        ([acao()], [Open(0, D1, _C, 100, 30.0), StrikeAdjusted(0, D2, 30.0, 29.0, FONTE)], "ação"),
        (
            [call(30.0)],
            [
                Open(0, D1, _V, 100, 1.0),
                Close(0, D2, 100, 0.5),
                StrikeAdjusted(0, D3, 30.0, 29.0, FONTE),
            ],
            "aberto",
        ),
        (
            [call(30.0)],
            [Open(0, D1, _V, 100, 1.0), StrikeAdjusted(0, D2, 30.0, 0.0, FONTE)],
            "strike",
        ),
        (
            [call(30.0)],
            [Open(0, D1, _V, 100, 1.0), StrikeAdjusted(0, D2, 30.0, math.nan, FONTE)],
            "strike",
        ),
        (
            [call(30.0)],
            [Open(0, D1, _V, 100, 1.0), StrikeAdjusted(0, D2, 30.0, 29.0, " ")],
            "fonte",
        ),
    ],
)
def test_ajuste_incoerente_e_recusado(pernas: list, eventos: list, motivo: str) -> None:  # type: ignore[type-arg]
    with pytest.raises(InvalidDomainValueError, match=motivo):
        operacao(pernas, eventos)


def test_atribuicao_usa_o_strike_ajustado_no_preco_da_acao() -> None:
    vendida = operacao(
        [put(30.0)], [Open(0, D1, _V, 100, 0.9), StrikeAdjusted(0, D2, 30.0, 29.47, FONTE)]
    )
    acoes = open_legs(apply_exercise(vendida, 0, 100, D3))[0]
    assert acoes.average_price == pytest.approx(29.47 - 0.9, abs=1e-12)


def test_emolumento_do_exercicio_usa_o_strike_ajustado() -> None:
    tabela = make_cost_schedule()  # à vista 0,02%, R$ 5 por ordem, R$ 2 por exercício
    exercida = operacao(
        [call(30.0), acao()],
        [
            Open(0, D1, _C, 100, 1.0, costs=0.0),
            StrikeAdjusted(0, D2, 30.0, 29.5, FONTE),
            Exercise(0, D3, 100),
            Open(1, D3, _C, 100, 30.5, costs=0.0),
        ],
    )
    exercicio = estimate_exercise_costs_by_leg(tabela, exercised=[(29.5, 100)]).total
    assert realized_result(exercida, [tabela]) == pytest.approx(-exercicio, abs=1e-9)


def test_ajuste_nao_tem_custo_nem_resultado() -> None:
    tabela = make_cost_schedule()
    sem = operacao([call(30.0)], [Open(0, D1, _V, 100, 1.0, costs=0.0)])
    com = sem.with_events(StrikeAdjusted(0, D2, 30.0, 29.47, FONTE))
    assert realized_result(com, [tabela]) == realized_result(sem, [tabela])


@pytest.mark.parametrize(
    ("listado", "esperado"),
    [
        (30.0, StrikeChange.SAME),
        (30.004, StrikeChange.SAME),  # meio centavo é ruído de arredondamento
        (29.99, StrikeChange.APPLY),  # provento pequeno: um centavo
        (29.47, StrikeChange.APPLY),
        (25.5, StrikeChange.APPLY),  # exatamente 15%: a borda aplica
        (25.49, StrikeChange.CHECK),
        (30.5, StrikeChange.CHECK),  # alta: grupamento, nunca provento
        (15.0, StrikeChange.CHECK),  # desdobramento 2 para 1
    ],
)
def test_so_a_queda_de_ate_15_por_cento_e_aplicada(listado: float, esperado: StrikeChange) -> None:
    assert MAX_PROVENTO_DROP == 0.15
    assert strike_change(30.0, listado) is esperado


@pytest.mark.parametrize(
    ("atual", "listado"), [(0.0, 29.0), (30.0, -1.0), (math.inf, 29.0), (30.0, math.nan)]
)
def test_strike_invalido_na_regra_e_recusado(atual: float, listado: float) -> None:
    with pytest.raises(InvalidDomainValueError, match="strike"):
        strike_change(atual, listado)

"""Operação e posições: preço médio ponderado, encerramento, pó e as regras dos eventos."""

from collections.abc import Callable

import pytest

from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Exercise,
    Expired,
    Open,
    Operation,
)
from options_engine.domain.portfolio.positions import (
    is_closed,
    leg_states,
    open_legs,
    realized_result,
)
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import D1, D2, D3, acao, call, operacao, put

_V, _C = Side.SELL, Side.BUY


def test_duas_aberturas_dao_o_preco_medio_ponderado() -> None:
    op = operacao([call(32.0)], [Open(0, D1, _V, 100, 1.00), Open(0, D2, _V, 200, 1.30)])
    (perna,) = open_legs(op)
    assert (perna.side, perna.quantity) == (_V, 300)
    assert perna.average_price == pytest.approx(1.20, abs=1e-12)


def test_encerramento_parcial_realiza_a_parte_encerrada() -> None:
    op = operacao(
        [call(32.0), put(28.0)],
        [
            Open(0, D1, _V, 300, 1.20),
            Close(0, D3, 100, 0.70),
            Open(1, D1, _C, 100, 0.50),
            Close(1, D3, 100, 0.80),
        ],
    )
    vendida, comprada = leg_states(op)
    assert vendida.quantity == 200 and vendida.realized == pytest.approx(50.0, abs=1e-9)
    assert comprada.quantity == 0 and comprada.realized == pytest.approx(30.0, abs=1e-9)
    assert not is_closed(op)


@pytest.mark.parametrize(
    ("eventos", "motivo"),
    [
        ([Open(0, D1, _V, 100, 1.0), Close(0, D2, 150, 0.5)], "aberto"),
        ([Open(0, D1, _V, 100, 1.0), Open(0, D2, _C, 100, 0.5)], "lado"),
        ([Close(0, D1, 100, 0.5)], "aberto"),
        ([Open(0, D1, _V, 100, 1.0), Exercise(0, D2, 100)], "comprada"),
        ([Open(0, D1, _C, 100, 1.0), Assignment(0, D2, 100)], "vendida"),
        ([Open(1, D1, _C, 100, 30.0), Expired(1, D2)], "opção"),
        ([Open(2, D1, _C, 100, 1.0)], "perna"),
        ([Open(0, D1, _V, 0, 1.0)], "quantidade"),
        ([Open(0, D1, _V, 100, -1.0)], "preço"),
    ],
)
def test_evento_impossivel_e_recusado(eventos: list[object], motivo: str) -> None:
    with pytest.raises(InvalidDomainValueError, match=motivo):
        operacao([call(32.0), acao()], eventos)  # type: ignore[arg-type]


def test_acao_da_carteira_nao_abre_e_so_fecha_com_o_custo_medio() -> None:
    carteira = acao(StockOrigin.CARTEIRA)
    with pytest.raises(InvalidDomainValueError, match="carteira"):
        operacao([carteira], [Open(0, D1, _C, 100, 30.0)])
    with pytest.raises(InvalidDomainValueError, match="custo médio"):
        operacao([carteira], [Close(0, D1, 100, 33.0)])
    vendida = operacao([carteira], [Close(0, D1, 100, 33.0, cost_basis=29.0)])
    assert leg_states(vendida)[0].realized == pytest.approx(400.0, abs=1e-9)
    with pytest.raises(InvalidDomainValueError, match="custo médio"):
        operacao([call(32.0)], [Open(0, D1, _V, 100, 1.0), Close(0, D2, 100, 0.5, cost_basis=1.0)])


def test_po_e_ganho_do_lancador_e_perda_do_titular() -> None:
    # IN RFB 1.585/2015, art. 60, § 3º.
    vendida = operacao([call(32.0)], [Open(0, D1, _V, 100, 1.00), Expired(0, D3)])
    comprada = operacao([put(28.0)], [Open(0, D1, _C, 100, 0.50), Expired(0, D3)])
    assert leg_states(vendida)[0].realized == pytest.approx(100.0, abs=1e-9)
    assert leg_states(comprada)[0].realized == pytest.approx(-50.0, abs=1e-9)
    assert is_closed(vendida) and is_closed(comprada)


def test_resultado_realizado_tira_os_custos_reais_ou_os_estimados() -> None:
    op = operacao([call(32.0)], [Open(0, D1, _V, 100, 1.00), Close(0, D3, 100, 0.40, costs=2.0)])
    tabela = make_cost_schedule()  # 0,05% de emolumentos de opção e R$ 5 por ordem
    estimada = 0.0005 * 100.0 + 5.0
    assert realized_result(op, [tabela]) == pytest.approx(60.0 - estimada - 2.0, abs=1e-9)


def test_operacao_sem_evento_e_aberta_sem_posicao() -> None:
    op = operacao([call(32.0)], [])
    assert open_legs(op) == () and not is_closed(op)


@pytest.mark.parametrize(
    ("criar", "motivo"),
    [
        (lambda: Operation(" ", "PETR4", "x", D1, (call(32.0),), ()), "id e nome"),
        (lambda: Operation("op", "PETR4", "x", D1, (), ()), "sem perna"),
        (lambda: Operation("op", "VALE3", "x", D1, (call(32.0),), ()), "VALE3"),
        (lambda: operacao([call(32.0)], [Open(0, D1, _V, 100, 1.0, costs=-1.0)]), "custos"),
        (lambda: operacao([acao()], [Open(0, D1, _C, 100, 30.0), Exercise(0, D2, 100)]), "ação"),
        (
            lambda: operacao([call(32.0)], [Open(0, D1, _C, 100, 1.0), Exercise(0, D2, 200)]),
            "aberto",
        ),
        (lambda: operacao([call(32.0)], [Expired(0, D2)]), "nada em aberto"),
    ],
)
def test_operacao_invalida_e_recusada(criar: Callable[[], object], motivo: str) -> None:
    with pytest.raises(InvalidDomainValueError, match=motivo):
        criar()


def test_novos_eventos_criam_outra_operacao_validada() -> None:
    op = operacao([call(32.0)], [Open(0, D1, _V, 100, 1.0)])
    encerrada = op.with_events(Close(0, D2, 100, 0.5))
    assert is_closed(encerrada) and not is_closed(op)
    with pytest.raises(InvalidDomainValueError):
        op.with_events(Close(0, D2, 200, 0.5))


def test_custos_estimados_de_po_exercicio_e_acao() -> None:
    tabela = make_cost_schedule()  # à vista 0,02%, R$ 5 por ordem, R$ 2 por exercício
    po = operacao([call(32.0)], [Open(0, D1, _V, 100, 1.0, costs=0.0), Expired(0, D3)])
    assert realized_result(po, [tabela]) == pytest.approx(100.0, abs=1e-9)
    exercida = operacao(
        [call(30.0), acao()],
        [Open(0, D1, _C, 100, 1.0, costs=0.0), Exercise(0, D3, 100), Open(1, D3, _C, 100, 31.0)],
    )
    exercicio, ordem_de_acao = 0.0002 * 30.0 * 100 + 2.0, 0.0002 * 31.0 * 100 + 5.0
    assert realized_result(exercida, [tabela]) == pytest.approx(
        -exercicio - ordem_de_acao, abs=1e-9
    )

"""Peças de resultado por série para o IR mensal: day trade separado do comum, pó e exercício."""

from datetime import date, timedelta
from math import fsum

from hypothesis import given
from hypothesis import strategies as st
from pytest import approx

from options_engine.domain.model.enums import Side
from options_engine.domain.portfolio.income_tax import (
    ExerciseNote,
    PieceKind,
    TaxCategory,
    TaxRecords,
    tax_records,
)
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Event,
    Exercise,
    Expired,
    Open,
    Operation,
)
from options_engine.domain.portfolio.positions import realized_result
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import acao, call, operacao, put

OUT1, OUT15 = date(2026, 10, 1), date(2026, 10, 15)
NOV3, NOV12, NOV19 = date(2026, 11, 3), date(2026, 11, 12), date(2026, 11, 19)


def test_day_trade_parcial_separa_o_casado_do_resto() -> None:
    # compra 200 a 1,00 (custo 2,00) e vende 100 a 1,30 (custo 1,00) no mesmo dia;
    # vende o resto a 0,50 (custo 1,00)
    op = operacao(
        [call(30.0)],
        [
            Open(0, OUT1, Side.BUY, 200, 1.00, 2.00),
            Close(0, OUT1, 100, 1.30, 1.00),
            Close(0, OUT15, 100, 0.50, 1.00),
        ],
        nome="call de outubro",
    )
    r = tax_records([op], [])
    assert [(p.on, p.category, p.kind) for p in r.pieces] == [
        (OUT1, TaxCategory.DAY_TRADE, PieceKind.CLOSE),
        (OUT15, TaxCategory.COMMON, PieceKind.CLOSE),
    ]
    assert [p.result for p in r.pieces] == [approx(28.00), approx(-52.00)]
    assert r.pieces[0].operations == ("call de outubro",)


def test_venda_e_recompra_parcial_no_mesmo_dia() -> None:
    # vende 200 a 1,00 e recompra 100 a 0,70 no mesmo dia (custo 0);
    # recompra o resto a 0,40 noutro dia
    op = operacao(
        [call(30.0)],
        [
            Open(0, NOV3, Side.SELL, 200, 1.00, 0.0),
            Close(0, NOV3, 100, 0.70, 0.0),
            Close(0, NOV12, 100, 0.40, 0.0),
        ],
    )
    pecas = tax_records([op], []).pieces
    assert [p.category for p in pecas] == [TaxCategory.DAY_TRADE, TaxCategory.COMMON]
    assert [p.result for p in pecas] == [approx(30.00), approx(60.00)]


def test_po_da_vendida_realiza_o_premio_liquido_como_comum() -> None:
    op = operacao(
        [put(28.0)],
        [
            Open(0, NOV3, Side.SELL, 200, 0.80, 2.00),
            Close(0, NOV12, 100, 0.20, 1.00),
            Expired(0, NOV19),
        ],
        nome="venda de put",
    )
    pecas = tax_records([op], []).pieces
    assert [(p.on, p.kind) for p in pecas] == [(NOV12, PieceKind.CLOSE), (NOV19, PieceKind.EXPIRED)]
    assert [p.result for p in pecas] == [approx(58.00), approx(79.00)]


def test_po_da_comprada_realiza_a_perda() -> None:
    op = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 0.50, 1.00), Expired(0, NOV19)])
    assert [p.result for p in tax_records([op], []).pieces] == [approx(-51.00)]


def test_exercicio_e_atribuicao_nao_geram_resultado_e_viram_nota() -> None:
    exercida = operacao(
        [call(32.0)],
        [Open(0, NOV3, Side.BUY, 100, 0.40, 1.00), Exercise(0, NOV19, 100, 0.0)],
        nome="call exercida",
    )
    atribuida = operacao(
        [put(28.0)],
        [Open(0, NOV3, Side.SELL, 100, 0.60, 1.00), Assignment(0, NOV19, 100, 0.0)],
        id_="op2",
        nome="put atribuída",
    )
    r = tax_records([exercida, atribuida], [])
    assert r.pieces == ()
    assert r.exercises == (
        ExerciseNote(NOV19, "PETRK320", "call exercida"),
        ExerciseNote(NOV19, "PETRW280", "put atribuída"),
    )


def test_virada_de_lado_no_mesmo_dia() -> None:
    # compra 100 a 1,00, vende 100 a 1,20 e vende mais 100 a 1,30 no mesmo dia;
    # recompra 100 a 1,00 no outro
    op = operacao(
        [call(30.0)],
        [
            Open(0, NOV3, Side.BUY, 100, 1.00, 0.0),
            Close(0, NOV3, 100, 1.20, 0.0),
            Open(0, NOV3, Side.SELL, 100, 1.30, 0.0),
            Close(0, NOV12, 100, 1.00, 0.0),
        ],
    )
    pecas = tax_records([op], []).pieces
    assert [p.category for p in pecas] == [TaxCategory.DAY_TRADE, TaxCategory.COMMON]
    assert [p.result for p in pecas] == [approx(25.00), approx(25.00)]


def test_comum_vem_antes_do_day_trade_no_mesmo_dia() -> None:
    # compra 100 a 1,00 no dia 3; no dia 12 vende 100 a 1,50, compra 100 a 1,20 e vende 100 a
    # 1,50: o casado do dia é day trade (100 x 0,30) e a venda que sobra encerra a comprada de 1,00
    op = operacao(
        [call(30.0)],
        [
            Open(0, NOV3, Side.BUY, 100, 1.00, 0.0),
            Close(0, NOV12, 100, 1.50, 0.0),
            Open(0, NOV12, Side.BUY, 100, 1.20, 0.0),
            Close(0, NOV12, 100, 1.50, 0.0),
        ],
    )
    pecas = tax_records([op], []).pieces
    assert [(p.on, p.category, p.kind) for p in pecas] == [
        (NOV12, TaxCategory.COMMON, PieceKind.CLOSE),
        (NOV12, TaxCategory.DAY_TRADE, PieceKind.CLOSE),
    ]
    assert [p.result for p in pecas] == [approx(50.00), approx(30.00)]


def test_mesma_serie_em_duas_operacoes_no_mesmo_dia_e_day_trade() -> None:
    x = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 1.00, 0.0)], id_="x", nome="x")
    y = operacao([call(30.0)], [Open(0, NOV3, Side.SELL, 100, 1.20, 0.0)], id_="y", nome="y")
    (peca,) = tax_records([x, y], []).pieces
    assert (peca.category, peca.operations) == (TaxCategory.DAY_TRADE, ("x", "y"))
    assert peca.result == approx(20.00)


def test_preco_medio_por_serie_junta_as_operacoes() -> None:
    x = operacao(
        [call(30.0)],
        [Open(0, NOV3, Side.BUY, 100, 1.00, 0.0), Close(0, NOV19, 100, 2.50, 0.0)],
        id_="x",
        nome="x",
    )
    y = operacao([call(30.0)], [Open(0, NOV12, Side.BUY, 100, 2.00, 0.0)], id_="y", nome="y")
    # médio 1,50, não 1,00
    assert [p.result for p in tax_records([x, y], []).pieces] == [approx(100.00)]


def test_serie_compartilhada_com_po_nas_duas_pernas() -> None:
    # x compra 100 a 1,00; y vende 60 a 1,20 e encerra 60 do médio; no vencimento, o pó de x
    # realiza só os 40 que sobram da série e o pó de y não tem o que tirar
    x = operacao(
        [call(30.0)],
        [Open(0, NOV3, Side.BUY, 100, 1.00, 0.0), Expired(0, NOV19)],
        id_="x",
        nome="x",
    )
    y = operacao(
        [call(30.0)],
        [Open(0, NOV12, Side.SELL, 60, 1.20, 0.0), Expired(0, NOV19)],
        id_="y",
        nome="y",
    )
    pecas = tax_records([x, y], []).pieces
    assert [(p.on, p.category, p.kind, p.operations) for p in pecas] == [
        (NOV12, TaxCategory.COMMON, PieceKind.CLOSE, ("y",)),
        (NOV19, TaxCategory.COMMON, PieceKind.EXPIRED, ("x",)),
    ]
    assert [p.result for p in pecas] == [approx(12.00), approx(-40.00)]
    assert fsum(p.result for p in pecas) == approx(-28.00)
    assert fsum(p.result for p in pecas) == approx(fsum(realized_result(o, []) for o in (x, y)))


def test_acao_fica_de_fora() -> None:
    op = operacao(
        [acao()], [Open(0, NOV3, Side.BUY, 100, 30.0, 0.0), Close(0, NOV12, 100, 32.0, 0.0)]
    )
    assert tax_records([op], []) == TaxRecords((), ())


def test_custos_da_tabela_quando_nao_digitados() -> None:
    tabela = [make_cost_schedule()]
    op = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 1.00), Close(0, NOV12, 100, 1.50)])
    (peca,) = tax_records([op], tabela).pieces
    assert peca.result == approx(realized_result(op, tabela))


_DIAS = [NOV3 + timedelta(days=i) for i in range(4)]
_QUANTIDADE = st.integers(1, 50)
_PRECO = st.floats(0.01, 5.0)
_CUSTO = st.floats(0.0, 5.0)


@st.composite
def _perna(draw: st.DrawFn, indice: int) -> list[Event]:
    lado = draw(st.sampled_from(Side))
    dia = draw(st.integers(0, len(_DIAS) - 1))
    eventos: list[Event] = []
    aberta = 0
    for _ in range(draw(st.integers(1, 3))):
        quantidade = draw(_QUANTIDADE)
        aberta += quantidade
        eventos.append(Open(indice, _DIAS[dia], lado, quantidade, draw(_PRECO), draw(_CUSTO)))
        dia = draw(st.integers(dia, len(_DIAS) - 1))
    while aberta:
        if draw(st.booleans()):
            # pó só no vencimento da série (o último dia): com a mesma série em duas pernas, pó
            # no meio da vida deixaria a posição da série sem par (a outra perna segue aberta)
            eventos.append(Expired(indice, _DIAS[-1]))
            break
        quantidade = draw(st.integers(1, aberta))
        aberta -= quantidade
        eventos.append(Close(indice, _DIAS[dia], quantidade, draw(_PRECO), draw(_CUSTO)))
        dia = draw(st.integers(dia, len(_DIAS) - 1))
    return eventos


@st.composite
def _operacoes(draw: st.DrawFn) -> list[Operation]:
    operacoes = []
    for i in range(draw(st.integers(1, 3))):
        strikes = draw(st.lists(st.sampled_from([30.0, 32.0]), min_size=1, max_size=2))
        eventos = [e for j in range(len(strikes)) for e in draw(_perna(j))]
        eventos.sort(key=lambda e: e.on)  # estável: a ordem de cada perna se mantém
        operacoes.append(
            operacao([call(k) for k in strikes], eventos, id_=f"op{i}", nome=f"operação {i}")
        )
    return operacoes


@given(_operacoes())
def test_soma_das_pecas_bate_com_o_realizado_da_carteira(operacoes: list[Operation]) -> None:
    pecas = tax_records(operacoes, []).pieces
    esperado = fsum(realized_result(o, []) for o in operacoes)
    assert fsum(p.result for p in pecas) == approx(esperado, abs=1e-6)

"""Exercício e atribuição pela IN RFB 1.585/2015, art. 60: o prêmio entra no preço da ação."""

import pytest

from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.exercise import (
    StockMovement,
    apply_exercise,
    stock_from_option,
    takes_portfolio_shares,
)
from options_engine.domain.portfolio.model import Assignment, Close, Exercise, Open
from options_engine.domain.portfolio.positions import is_closed, leg_states, open_legs
from tests.portfolio._builders import D1, D3, acao, call, operacao, put

_V, _C = Side.SELL, Side.BUY


@pytest.mark.parametrize(
    ("tipo", "lado", "esperado"),
    [
        (OptionType.CALL, _C, StockMovement(_C, 100, 31.2)),  # alínea a: custo = K + P
        (OptionType.CALL, _V, StockMovement(_V, 100, 31.2)),  # alínea b: venda = K + P
        (OptionType.PUT, _C, StockMovement(_V, 100, 28.8)),  # alínea c: venda = K - P
        (OptionType.PUT, _V, StockMovement(_C, 100, 28.8)),  # alínea d: custo = K - P
    ],
)
def test_os_quatro_casos_da_receita(tipo: OptionType, lado: Side, esperado: StockMovement) -> None:
    obtido = stock_from_option(tipo, lado, strike=30.0, premium=1.2, quantity=100)
    assert (obtido.side, obtido.quantity) == (esperado.side, esperado.quantity)
    assert obtido.price == pytest.approx(esperado.price, abs=1e-12)


def test_premio_que_zera_o_preco_da_acao_e_recusado() -> None:
    with pytest.raises(InvalidDomainValueError, match="prêmio"):
        stock_from_option(OptionType.PUT, _V, strike=1.0, premium=1.0, quantity=100)


def test_venda_coberta_atribuida_entrega_as_acoes_e_fecha_com_o_ganho_maximo() -> None:
    coberta = operacao(
        [call(32.0), acao()], [Open(1, D1, _C, 100, 30.0), Open(0, D1, _V, 100, 1.00)]
    )
    atribuida = apply_exercise(coberta, 0, 100, D3)
    assert atribuida.events[-2:] == (
        Assignment(0, D3, 100),
        Close(1, D3, 100, pytest.approx(33.0), costs=0.0),  # type: ignore[arg-type]
    )
    opcao, acoes = leg_states(atribuida)
    assert opcao.realized == 0.0  # o prêmio foi para o preço de venda da ação
    assert acoes.realized == pytest.approx(300.0, abs=1e-9)  # (32 - 30 + 1) x 100
    assert is_closed(atribuida)


def test_venda_coberta_com_acao_da_carteira_usa_o_custo_medio_dela() -> None:
    coberta = operacao([call(32.0), acao(StockOrigin.CARTEIRA)], [Open(0, D1, _V, 100, 1.00)])
    with pytest.raises(InvalidDomainValueError, match="preço médio"):
        apply_exercise(coberta, 0, 100, D3)
    atribuida = apply_exercise(coberta, 0, 100, D3, portfolio_average=29.0)
    assert leg_states(atribuida)[1].realized == pytest.approx(400.0, abs=1e-9)


def test_so_a_acao_que_sai_sem_as_proprias_vem_da_carteira() -> None:
    da_carteira = operacao(
        [call(32.0), acao(StockOrigin.CARTEIRA), put(28.0)],
        [Open(0, D1, _V, 100, 1.00), Open(2, D1, _V, 100, 0.50)],
    )
    assert takes_portfolio_shares(da_carteira, 0, 100)
    assert not takes_portfolio_shares(da_carteira, 2, 100)  # a put atribuída faz entrar ações
    propria = operacao(
        [call(32.0), acao()], [Open(1, D1, _C, 100, 30.0), Open(0, D1, _V, 100, 1.00)]
    )
    assert not takes_portfolio_shares(propria, 0, 100)


def test_call_comprada_exercida_cria_a_perna_de_acao_com_o_premio_no_custo() -> None:
    comprada = operacao([call(30.0)], [Open(0, D1, _C, 200, 1.5)])
    exercida = apply_exercise(comprada, 0, 100, D3)
    assert exercida.legs[1] == acao()
    assert exercida.events[-2] == Exercise(0, D3, 100)
    parcial, acoes = open_legs(exercida)
    assert (parcial.quantity, parcial.side) == (100, _C)
    assert (acoes.side, acoes.quantity) == (_C, 100)
    assert acoes.average_price == pytest.approx(31.5, abs=1e-12)


def test_put_vendida_atribuida_compra_as_acoes_pelo_strike_menos_o_premio() -> None:
    vendida = operacao([put(28.0)], [Open(0, D1, _V, 100, 0.9)])
    atribuida = apply_exercise(vendida, 0, 100, D3)
    acoes = open_legs(atribuida)[0]
    assert (acoes.side, acoes.quantity) == (_C, 100)
    assert acoes.average_price == pytest.approx(27.1, abs=1e-12)


def test_put_comprada_exercida_sem_acoes_fica_vendida_em_acoes() -> None:
    comprada = operacao([put(28.0)], [Open(0, D1, _C, 100, 0.5)])
    acoes = open_legs(apply_exercise(comprada, 0, 100, D3))[0]
    assert (acoes.side, acoes.quantity) == (_V, 100)
    assert acoes.average_price == pytest.approx(27.5, abs=1e-12)


def test_exercer_mais_do_que_o_aberto_ou_perna_de_acao_e_recusado() -> None:
    comprada = operacao(
        [call(30.0), acao()], [Open(0, D1, _C, 100, 1.5), Open(1, D1, _C, 100, 30.0)]
    )
    with pytest.raises(InvalidDomainValueError, match="aberto"):
        apply_exercise(comprada, 0, 200, D3)
    with pytest.raises(InvalidDomainValueError, match="opção"):
        apply_exercise(comprada, 1, 100, D3)


def test_perna_inexistente_e_acao_comprada_que_ja_existe_recebe_a_nova() -> None:
    comprada = operacao([call(30.0), acao()], [Open(0, D1, _C, 100, 1.5)])
    with pytest.raises(InvalidDomainValueError, match="inexistente"):
        apply_exercise(comprada, 5, 100, D3)
    exercida = apply_exercise(comprada, 0, 100, D3)
    assert len(exercida.legs) == 2
    assert exercida.events[-1] == Open(1, D3, _C, 100, pytest.approx(31.5), costs=0.0)  # type: ignore[arg-type]

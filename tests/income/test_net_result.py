"""Resultado líquido no vencimento de qualquer estrutura: bruto - montagem - exercício - IR."""

import pytest

from options_engine.domain.income.metrics import covered_call_metrics
from options_engine.domain.income.net_result import net_result_at_expiry
from options_engine.domain.income.profile import PositionLeg, result_at_expiry
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import MissingPremiumError
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import pnl
from tests._tolerances import ABS_INCOME, REL_INCOME, assert_close
from tests.domain._builders import make_leg, make_stock_leg, make_terms
from tests.income._builders import make_cdi, make_cost_schedule, reference_cost_schedule


def _coberta(premio: float = 1.0) -> Strategy:
    call = make_leg(terms=make_terms(strike=32.0), side=Side.SELL, quantity=100, premium=premio)
    return Strategy.create("venda coberta", [call], [make_stock_leg(price=30.0)])


def _perto(a: float, b: float) -> None:
    assert_close(a, b, rel=REL_INCOME, abs_=ABS_INCOME * 3200, label="líquido")


def test_venda_coberta_bate_com_as_metricas_de_renda_nos_extremos() -> None:
    tabela = reference_cost_schedule()
    metricas = covered_call_metrics(
        spot=30.0,
        strike=32.0,
        premium_per_share=1.0,
        business_days=20,
        cdi=make_cdi(),
        cost_schedule=tabela,
    )
    _perto(net_result_at_expiry(_coberta(), 40.0, tabela), metricas.net_max_gain_per_position)
    _perto(net_result_at_expiry(_coberta(), 0.0, tabela), metricas.net_max_loss_per_position)


@pytest.mark.parametrize("spot", [20.0, 27.0, 28.5, 30.0, 32.0, 35.0])
def test_trava_bate_com_o_perfil_de_renda(spot: float) -> None:
    tabela = make_cost_schedule()
    put_baixa = make_leg(
        symbol="P27", terms=make_terms(strike=27.0, option_type=OptionType.PUT), premium=0.4
    )
    put_alta = make_leg(
        symbol="P29",
        terms=make_terms(strike=29.0, option_type=OptionType.PUT),
        side=Side.SELL,
        premium=1.1,
    )
    trava = Strategy.create("trava de alta com put", [put_baixa, put_alta])
    _, esperado = result_at_expiry(
        [
            PositionLeg(OptionType.PUT, Side.BUY, 27.0, 0.4),
            PositionLeg(OptionType.PUT, Side.SELL, 29.0, 1.1),
        ],
        spot,
        schedule=tabela,
        shares=10,
    )
    _perto(net_result_at_expiry(trava, spot, tabela), esperado)


def test_acao_que_ja_esta_na_carteira_nao_paga_a_compra() -> None:
    tabela = make_cost_schedule()
    comprada = net_result_at_expiry(_coberta(), 31.0, tabela)
    da_carteira = net_result_at_expiry(_coberta(), 31.0, tabela, stock_already_held=True)
    compra = 0.0002 * 30.0 * 100 + 5.0
    # A 31 o IR já está no teto do resultado do prêmio: a compra da ação não muda o imposto.
    _perto(da_carteira - comprada, compra)


def test_sem_custos_o_liquido_e_o_bruto() -> None:
    tabela = make_cost_schedule(
        option_exchange_fee_rate=0.0,
        spot_exchange_fee_rate=0.0,
        brokerage_per_order=0.0,
        exercise_brokerage_per_order=0.0,
        income_tax_rate=0.0,
    )
    for spot in (0.0, 29.0, 35.0):
        _perto(net_result_at_expiry(_coberta(), spot, tabela), pnl(_coberta(), spot))


def test_borboleta_paga_o_exercicio_de_cada_perna_pela_quantidade() -> None:
    tabela = make_cost_schedule(option_exchange_fee_rate=0.0, income_tax_rate=0.0)
    asa_baixa = make_leg(symbol="C28", terms=make_terms(strike=28.0), quantity=100, premium=2.4)
    corpo = make_leg(
        symbol="C30", terms=make_terms(strike=30.0), side=Side.SELL, quantity=200, premium=1.2
    )
    asa_alta = make_leg(symbol="C32", terms=make_terms(strike=32.0), quantity=100, premium=0.5)
    borboleta = Strategy.create("borboleta", [asa_baixa, corpo, asa_alta])
    montagem = 3 * 5.0
    exercicio = 0.0002 * (28.0 * 100 + 30.0 * 200) + 2 * 2.0  # 28 e 30 exercidas a 31
    _perto(
        net_result_at_expiry(borboleta, 31.0, tabela), pnl(borboleta, 31.0) - montagem - exercicio
    )


def test_so_acao_da_carteira_nao_tem_custo_de_ordem() -> None:
    so_acao = Strategy.create("ações", [], [make_stock_leg(price=30.0)])
    _perto(
        net_result_at_expiry(so_acao, 31.0, make_cost_schedule(), stock_already_held=True), 100.0
    )


def test_sem_premio_o_liquido_e_recusado() -> None:
    sem = Strategy.create("c", [make_leg(premium=None)])
    with pytest.raises(MissingPremiumError):
        net_result_at_expiry(sem, 30.0, make_cost_schedule())

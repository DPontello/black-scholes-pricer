"""Mark-to-model e gregas com a perna de ação: a ação vale o spot e tem delta igual à quantidade."""

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.conventions import TimeToExpiry
from options_engine.domain.model.enums import Side
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import mark_to_model_value, portfolio_greeks
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.domain._builders import make_leg, make_snapshot, make_stock_leg, make_terms

_TTX = TimeToExpiry.from_days(126)


def _coberta() -> Strategy:
    chamada = make_leg(terms=make_terms(strike=32.0), side=Side.SELL, quantity=100, premium=1.0)
    return Strategy.create("venda coberta", [chamada], [make_stock_leg(price=30.0)])


def test_valor_a_mercado_soma_as_acoes_ao_spot() -> None:
    snapshot = make_snapshot()
    chamada = bs_outputs(31.0, 32.0, _TTX.year_fraction, 0.10, 0.25, is_call=True)
    assert_close(
        mark_to_model_value(_coberta(), 31.0, time_to_expiry=_TTX, snapshot=snapshot),
        100 * 31.0 - 100 * chamada.price,
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * 3100,
        label="valor da venda coberta",
    )


def test_delta_inclui_as_acoes_e_as_outras_gregas_nao() -> None:
    snapshot = make_snapshot()
    chamada = bs_outputs(30.0, 32.0, _TTX.year_fraction, 0.10, 0.25, is_call=True)
    gregas = portfolio_greeks(_coberta(), time_to_expiry=_TTX, snapshot=snapshot)
    assert_close(gregas.delta, 100 - 100 * chamada.delta, rel=REL_SELF, abs_=ABS_SELF_FLOOR * 100)
    assert_close(gregas.gamma, -100 * chamada.gamma, rel=REL_SELF, abs_=ABS_SELF_FLOOR * 100)

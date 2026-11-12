"""Fábricas de opção a seco e das estruturas com ação: forma certa aceita, errada recusada."""

import pytest

from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidStrategyError
from options_engine.domain.model.factories import (
    cash_secured_put,
    collar,
    covered_call,
    long_call,
    long_put,
    protective_put,
)
from options_engine.domain.model.strategy import StrategyLeg
from tests.domain._builders import make_leg, make_stock_leg, make_terms


def _perna(
    option_type: OptionType, side: Side, strike: float = 30.0, quantity: int = 100
) -> StrategyLeg:
    return make_leg(
        symbol=f"{option_type.value}{strike:g}",
        terms=make_terms(strike=strike, option_type=option_type),
        side=side,
        quantity=quantity,
    )


def test_compra_de_call_e_de_put_a_seco() -> None:
    assert long_call([_perna(OptionType.CALL, Side.BUY)]).name == "compra de call"
    assert long_put([_perna(OptionType.PUT, Side.BUY)]).name == "compra de put"


@pytest.mark.parametrize(
    "pernas",
    [
        [_perna(OptionType.CALL, Side.SELL)],
        [_perna(OptionType.PUT, Side.BUY)],
        [_perna(OptionType.CALL, Side.BUY), _perna(OptionType.CALL, Side.BUY, 32.0)],
    ],
)
def test_compra_de_call_recusa_outra_forma(pernas: list[StrategyLeg]) -> None:
    with pytest.raises(InvalidStrategyError, match="compra de call"):
        long_call(pernas)


def test_compra_de_put_recusa_put_vendida() -> None:
    with pytest.raises(InvalidStrategyError, match="compra de put"):
        long_put([_perna(OptionType.PUT, Side.SELL)])


def test_put_coberta_e_put_vendida() -> None:
    assert cash_secured_put([_perna(OptionType.PUT, Side.SELL)]).name == "put coberta"
    with pytest.raises(InvalidStrategyError, match="put coberta"):
        cash_secured_put([_perna(OptionType.PUT, Side.BUY)])


def test_venda_coberta_e_acao_comprada_mais_call_vendida_na_mesma_quantidade() -> None:
    coberta = covered_call([_perna(OptionType.CALL, Side.SELL, 32.0)], make_stock_leg())
    assert coberta.name == "venda coberta"
    assert coberta.stock_legs == (make_stock_leg(),)


@pytest.mark.parametrize(
    ("perna", "acao"),
    [
        (_perna(OptionType.CALL, Side.BUY, 32.0), make_stock_leg()),
        (_perna(OptionType.PUT, Side.SELL, 32.0), make_stock_leg()),
        (_perna(OptionType.CALL, Side.SELL, 32.0), make_stock_leg(side=Side.SELL)),
        (_perna(OptionType.CALL, Side.SELL, 32.0), make_stock_leg(quantity=200)),
    ],
)
def test_venda_coberta_recusa_outra_forma(perna: StrategyLeg, acao: object) -> None:
    with pytest.raises(InvalidStrategyError, match="venda coberta"):
        covered_call([perna], acao)  # type: ignore[arg-type]


def test_put_protetora_e_acao_comprada_mais_put_comprada() -> None:
    protegida = protective_put([_perna(OptionType.PUT, Side.BUY, 28.0)], make_stock_leg())
    assert protegida.name == "put protetora"
    with pytest.raises(InvalidStrategyError, match="put protetora"):
        protective_put([_perna(OptionType.PUT, Side.SELL, 28.0)], make_stock_leg())
    with pytest.raises(InvalidStrategyError, match="put protetora"):
        protective_put([_perna(OptionType.PUT, Side.BUY, 28.0)], make_stock_leg(quantity=300))


def test_collar_tem_put_comprada_abaixo_da_call_vendida() -> None:
    pernas = [_perna(OptionType.CALL, Side.SELL, 33.0), _perna(OptionType.PUT, Side.BUY, 28.0)]
    montado = collar(pernas, make_stock_leg())
    assert montado.name == "collar"
    assert [leg.terms.strike for leg in montado.legs] == [28.0, 33.0]


@pytest.mark.parametrize(
    "pernas",
    [
        [_perna(OptionType.PUT, Side.BUY, 33.0), _perna(OptionType.CALL, Side.SELL, 33.0)],
        [_perna(OptionType.PUT, Side.BUY, 35.0), _perna(OptionType.CALL, Side.SELL, 33.0)],
        [_perna(OptionType.PUT, Side.BUY, 28.0), _perna(OptionType.CALL, Side.BUY, 33.0)],
        [_perna(OptionType.PUT, Side.BUY, 28.0)],
    ],
)
def test_collar_recusa_outra_forma(pernas: list[StrategyLeg]) -> None:
    with pytest.raises(InvalidStrategyError, match="collar"):
        collar(pernas, make_stock_leg())

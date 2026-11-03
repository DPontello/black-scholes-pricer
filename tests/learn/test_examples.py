"""Exemplos da aba Aprender: as 18 operações com o resultado vindo da mesma conta do Montador."""

from datetime import date
from math import copysign

from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.learn.examples import Example, ExampleLeg, examples
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.strategy import StockLeg, Strategy, StrategyLeg
from options_engine.domain.model.templates import TEMPLATES, template
from options_engine.domain.simulation.valuation import expiry_pnl, expiry_summary
from tests._tolerances import ABS_BREAKEVEN, ABS_PAYOFF, REL_PAYOFF, assert_close

# Ordem do strike x ações do exemplo (R$ 50 x 100): o ruído de float escala com ela.
_ESCALA = 1e4


def _por_chave(chave: str) -> Example:
    return next(e for e in examples() if e.key == chave)


def _estrategia(exemplo: Example) -> Strategy:
    """A Strategy do exemplo, pelo mesmo ``Template.build`` do Montador."""
    vencimento = date(2026, 12, 21)
    pernas = [
        StrategyLeg(
            f"{exemplo.key}-{i}",
            OptionTerms("PETR4", p.strike, vencimento, p.option_type),
            p.side,
            p.quantity,
            p.premium,
        )
        for i, p in enumerate(exemplo.legs)
    ]
    acao = None
    if exemplo.stock_quantity:
        acao = StockLeg("PETR4", Side.BUY, exemplo.stock_quantity, exemplo.spot)
    return template(exemplo.key).build(pernas, acao)


def test_todo_modelo_tem_exemplo() -> None:
    assert [e.key for e in examples()] == [t.key for t in TEMPLATES]


def test_venda_coberta() -> None:
    premio = round(bs_price(50, 52, 21 / 252, 0.14, 0.30, is_call=True), 2)
    e = _por_chave("venda_coberta")

    assert premio == 1.14
    assert e.legs == (ExampleLeg(OptionType.CALL, Side.SELL, 52.0, premio, 100),)
    assert (e.spot, e.stock_quantity, e.net_premium) == (50.0, 100, 114.0)
    assert e.scenarios == ((45.0, -386.0), (50.0, 114.0), (55.0, 314.0))
    assert len(e.breakevens) == 1
    assert_close(e.breakevens[0], 48.86, rel=0.0, abs_=ABS_BREAKEVEN, label="empate")
    assert (e.max_gain, e.max_loss) == (314.0, 4886.0)


def test_resultado_vem_do_dominio() -> None:
    for e in examples():
        estrategia = _estrategia(e)
        for preco, resultado in (*e.scenarios, *e.curve):
            assert_close(
                resultado,
                expiry_pnl(estrategia, preco),
                rel=REL_PAYOFF,
                abs_=ABS_PAYOFF * _ESCALA,
                label=f"{e.key} em {preco}",
            )
        empates, maximo, minimo = expiry_summary(estrategia)
        assert len(e.breakevens) == len(empates), e.key
        for obtido, esperado in zip(e.breakevens, empates, strict=True):
            assert_close(obtido, esperado, rel=0.0, abs_=ABS_BREAKEVEN, label=f"{e.key} empate")
        if maximo is None or e.max_gain is None:
            assert e.max_gain is None and maximo is None, e.key
        else:
            assert_close(e.max_gain, maximo, rel=REL_PAYOFF, abs_=ABS_PAYOFF * _ESCALA)
        if minimo is None or e.max_loss is None:
            assert e.max_loss is None and minimo is None, e.key
        else:
            assert_close(e.max_loss, max(0.0, -minimo), rel=REL_PAYOFF, abs_=ABS_PAYOFF * _ESCALA)


def test_sem_limite() -> None:
    assert _por_chave("straddle_vendido").max_loss is None
    assert _por_chave("strangle_vendido").max_loss is None
    assert _por_chave("compra_call").max_gain is None
    assert _por_chave("put_protetora").max_gain is None


def test_strikes_seguem_o_passo_do_modelo() -> None:
    strikes = tuple(p.strike for p in _por_chave("iron_condor_vendido").legs)
    assert strikes == (46.0, 48.0, 52.0, 54.0)


def test_acao_so_nos_modelos_com_acao() -> None:
    for modelo, e in zip(TEMPLATES, examples(), strict=True):
        assert e.stock_quantity == (0 if modelo.stock is None else 100), modelo.key


def test_lote_de_100_por_unidade_de_proporcao() -> None:
    assert [p.quantity for p in _por_chave("borboleta_comprada").legs] == [100, 200, 100]


def test_cenarios_e_curva_do_exemplo_fixo() -> None:
    for e in examples():
        assert [preco for preco, _ in e.scenarios] == [45.0, 50.0, 55.0], e.key
        assert len(e.curve) == 81, e.key
        assert (e.curve[0][0], e.curve[-1][0]) == (30.0, 70.0), e.key


def test_valores_em_reais_vem_em_centavos() -> None:
    for e in examples():
        valores = [e.net_premium, *(r for _, r in e.scenarios), *(r for _, r in e.curve)]
        valores += [v for v in (e.max_gain, e.max_loss) if v is not None]
        assert all(round(v, 2) == v for v in valores), e.key
        assert all(copysign(1.0, v) > 0 for v in valores if v == 0.0), e.key

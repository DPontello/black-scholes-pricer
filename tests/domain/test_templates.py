"""Catálogo de modelos prontos: famílias, sugestão de strikes e montagem pela fábrica certa."""

import pytest

from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidStrategyError
from options_engine.domain.model.strategy import StockLeg, StrategyLeg
from options_engine.domain.model.templates import (
    TEMPLATES,
    Family,
    Template,
    suggest_strikes,
    template,
)
from tests.domain._builders import make_leg, make_stock_leg, make_terms

STRIKES = (26.0, 28.0, 30.0, 32.0, 34.0)


def _pernas(modelo: Template, strikes: tuple[float, ...], lote: int = 100) -> list[StrategyLeg]:
    return [
        make_leg(
            symbol=f"{perna.option_type.value}{strike:g}",
            terms=make_terms(strike=strike, option_type=perna.option_type),
            side=perna.side,
            quantity=lote * perna.ratio,
        )
        for perna, strike in zip(modelo.legs, strikes, strict=True)
    ]


def _acao(modelo: Template) -> StockLeg | None:
    return None if modelo.stock is None else make_stock_leg(side=modelo.stock)


def test_catalogo_tem_os_modelos_de_cada_familia() -> None:
    por_familia = {f: {m.key for m in TEMPLATES if m.family is f} for f in Family}
    assert por_familia == {
        Family.RENDA: {"venda_coberta", "put_coberta", "trava_alta_put", "trava_baixa_call"},
        Family.DIRECIONAIS: {"compra_call", "compra_put", "trava_alta_call", "trava_baixa_put"},
        Family.VOLATILIDADE: {
            "straddle_comprado",
            "straddle_vendido",
            "strangle_comprado",
            "strangle_vendido",
            "iron_condor_vendido",
            "iron_condor_comprado",
            "borboleta_comprada",
            "borboleta_vendida",
        },
        Family.PROTECAO: {"put_protetora", "collar"},
    }


def test_sugestao_parte_do_strike_mais_perto_do_spot() -> None:
    assert suggest_strikes(template("iron_condor_vendido"), STRIKES, 30.4) == (
        26.0,
        28.0,
        32.0,
        34.0,
    )
    assert suggest_strikes(template("straddle_comprado"), STRIKES, 30.4) == (30.0, 30.0)
    assert suggest_strikes(template("venda_coberta"), STRIKES, 29.2) == (32.0,)


def test_empate_entre_dois_strikes_fica_com_o_menor() -> None:
    assert suggest_strikes(template("compra_call"), STRIKES, 31.0) == (30.0,)


def test_cadeia_sem_strikes_suficientes_e_recusada() -> None:
    with pytest.raises(InvalidStrategyError, match="strikes"):
        suggest_strikes(template("iron_condor_vendido"), (30.0, 32.0), 30.0)
    with pytest.raises(InvalidStrategyError, match="strikes"):
        suggest_strikes(template("compra_call"), (), 30.0)


@pytest.mark.parametrize("modelo", TEMPLATES, ids=lambda m: m.key)
def test_cada_modelo_monta_pela_fabrica_da_familia(modelo: Template) -> None:
    strikes = suggest_strikes(modelo, STRIKES, 30.0)
    estrutura = modelo.build(_pernas(modelo, strikes), _acao(modelo))
    assert estrutura.name == modelo.name
    assert len(estrutura.legs) == len(modelo.legs)
    assert len(estrutura.stock_legs) == (0 if modelo.stock is None else 1)


def test_modelo_recusa_pernas_que_formam_outra_estrutura() -> None:
    trava = template("trava_alta_put")
    pernas = [leg.mirrored() for leg in _pernas(trava, suggest_strikes(trava, STRIKES, 30.0))]
    with pytest.raises(InvalidStrategyError, match="trava de alta com put"):
        trava.build(pernas, None)


def test_modelo_com_acao_exige_a_acao_e_o_sem_acao_recusa() -> None:
    coberta = template("venda_coberta")
    with pytest.raises(InvalidStrategyError, match="ação"):
        coberta.build(_pernas(coberta, (32.0,)), None)
    call = template("compra_call")
    with pytest.raises(InvalidStrategyError, match="ação"):
        call.build(_pernas(call, (30.0,)), make_stock_leg())


def test_modelo_desconhecido() -> None:
    with pytest.raises(KeyError):
        template("calendario")


def test_borboleta_tem_o_corpo_com_o_dobro() -> None:
    borboleta = template("borboleta_comprada")
    corpo = next(p for p in borboleta.legs if p.side is Side.SELL)
    assert (corpo.ratio, corpo.option_type) == (2, OptionType.CALL)


def test_modelo_com_acao_comprada_recusa_acao_vendida() -> None:
    coberta = template("venda_coberta")
    with pytest.raises(InvalidStrategyError, match="ação comprada"):
        coberta.build(_pernas(coberta, (32.0,)), make_stock_leg(side=Side.SELL))


def test_fabrica_com_acao_chamada_direto_sem_acao_e_recusada() -> None:
    coberta = template("venda_coberta")
    with pytest.raises(InvalidStrategyError, match="perna de ação"):
        coberta.factory(_pernas(coberta, (32.0,)), None, coberta.name)

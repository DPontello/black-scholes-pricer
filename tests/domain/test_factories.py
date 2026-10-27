"""Factories nomeadas — geometria E composição, nas duas direções.

Critério de aceite da Sprint 2: ``InvalidStrategyError`` tanto para strikes
fora de ordem quanto para composição errada de pernas (tipos/sides) — um
"condor" de 4 calls é tão inválido quanto um de strikes coincidentes.
"""

import pytest

from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidStrategyError
from options_engine.domain.model.factories import (
    butterfly,
    condor_direction,
    iron_condor,
    straddle,
    strangle,
    vertical_spread,
    vertical_spread_direction,
)
from options_engine.domain.simulation import net_premium_cashflow
from tests.domain._builders import (
    make_butterfly_legs,
    make_condor_legs,
    make_leg,
    make_straddle_legs,
    make_strangle_legs,
    make_terms,
    make_vertical_legs,
)

# ---------------------------------------------------------------------------
# iron_condor — decisão nº 3: ambas as direções
# ---------------------------------------------------------------------------


def test_condor_de_credito_e_valido_e_nomeado_pela_direcao() -> None:
    estrutura = iron_condor(make_condor_legs(direction=Side.SELL))
    assert estrutura.name == "iron condor vendido (crédito)"
    assert condor_direction(estrutura) is Side.SELL


def test_condor_de_debito_e_valido_decisao_3() -> None:
    estrutura = iron_condor(make_condor_legs(direction=Side.BUY))
    assert estrutura.name == "iron condor comprado (débito)"
    assert condor_direction(estrutura) is Side.BUY


def test_legs_saem_ordenadas_por_strike() -> None:
    """Ordem canônica determinística — base das agregações com fsum."""
    embaralhadas = list(reversed(make_condor_legs()))
    estrutura = iron_condor(embaralhadas)
    strikes = [leg.terms.strike for leg in estrutura.legs]
    assert strikes == sorted(strikes)


def test_nome_customizado_e_respeitado() -> None:
    assert iron_condor(make_condor_legs(), name="condor da mesa").name == "condor da mesa"


def test_condor_com_numero_errado_de_legs() -> None:
    with pytest.raises(InvalidStrategyError):
        iron_condor(make_condor_legs()[:3])


def test_condor_com_strikes_coincidentes() -> None:
    with pytest.raises(InvalidStrategyError):
        iron_condor(make_condor_legs(strikes=(26.0, 28.0, 28.0, 34.0)))


def test_condor_com_puts_acima_das_calls() -> None:
    """Strikes fora de ordem: o put spread precisa ficar ABAIXO do call spread."""
    legs = make_condor_legs()
    trocadas = [
        make_leg(
            symbol=leg.symbol,
            terms=make_terms(
                strike=leg.terms.strike,
                option_type=(
                    OptionType.CALL if leg.terms.option_type is OptionType.PUT else OptionType.PUT
                ),
            ),
            side=leg.side,
            quantity=leg.quantity,
        )
        for leg in legs
    ]
    with pytest.raises(InvalidStrategyError):
        iron_condor(trocadas)


def test_condor_de_quatro_calls_e_composicao_errada() -> None:
    legs = [
        make_leg(
            symbol=f"PETRC{int(k)}",
            terms=make_terms(strike=k, option_type=OptionType.CALL),
            side=side,
        )
        for k, side in ((26.0, Side.BUY), (28.0, Side.SELL), (32.0, Side.SELL), (34.0, Side.BUY))
    ]
    with pytest.raises(InvalidStrategyError):
        iron_condor(legs)


def test_condor_com_asas_em_lados_distintos() -> None:
    legs = make_condor_legs()
    legs[0] = legs[0].mirrored()  # asa baixa passa para o lado do corpo
    with pytest.raises(InvalidStrategyError):
        iron_condor(legs)


def test_condor_com_corpo_no_mesmo_lado_das_asas() -> None:
    """4 legs BUY não são um condor — são um strangle duplo comprado."""
    legs = [leg if leg.side is Side.BUY else leg.mirrored() for leg in make_condor_legs()]
    with pytest.raises(InvalidStrategyError):
        iron_condor(legs)


def test_condor_com_quantidades_desiguais() -> None:
    legs = make_condor_legs()
    legs[2] = make_leg(symbol=legs[2].symbol, terms=legs[2].terms, side=legs[2].side, quantity=99)
    with pytest.raises(InvalidStrategyError):
        iron_condor(legs)


# ---------------------------------------------------------------------------
# straddle
# ---------------------------------------------------------------------------


def test_straddle_comprado_e_vendido_sao_validos() -> None:
    assert straddle(make_straddle_legs(direction=Side.BUY)).name == "straddle comprado"
    assert straddle(make_straddle_legs(direction=Side.SELL)).name == "straddle vendido"


def test_straddle_com_strikes_distintos_e_um_strangle() -> None:
    legs = make_straddle_legs()
    legs[1] = make_leg(
        symbol="PETRP2800",
        terms=make_terms(strike=28.0, option_type=OptionType.PUT),
        side=legs[1].side,
    )
    with pytest.raises(InvalidStrategyError):
        straddle(legs)


def test_straddle_de_duas_calls_e_composicao_errada() -> None:
    legs = make_straddle_legs()
    legs[1] = make_leg(
        symbol="PETRC3000B",
        terms=make_terms(strike=30.0, option_type=OptionType.CALL),
        side=legs[1].side,
    )
    with pytest.raises(InvalidStrategyError):
        straddle(legs)


def test_straddle_com_lados_mistos_nao_e_straddle() -> None:
    legs = make_straddle_legs()
    legs[1] = legs[1].mirrored()
    with pytest.raises(InvalidStrategyError):
        straddle(legs)


# ---------------------------------------------------------------------------
# strangle
# ---------------------------------------------------------------------------


def test_strangle_valido_nas_duas_direcoes() -> None:
    assert strangle(make_strangle_legs(direction=Side.BUY)).name == "strangle comprado"
    assert strangle(make_strangle_legs(direction=Side.SELL)).name == "strangle vendido"


def test_strangle_exige_put_abaixo_da_call() -> None:
    """Tipos trocados (call abaixo, put acima) são composição errada."""
    legs = make_strangle_legs()
    invertidas = [
        make_leg(
            symbol="PETRC2800",
            terms=make_terms(strike=28.0, option_type=OptionType.CALL),
            side=legs[0].side,
        ),
        make_leg(
            symbol="PETRP3200",
            terms=make_terms(strike=32.0, option_type=OptionType.PUT),
            side=legs[1].side,
        ),
    ]
    with pytest.raises(InvalidStrategyError):
        strangle(invertidas)


def test_strangle_com_strikes_iguais_e_um_straddle() -> None:
    with pytest.raises(InvalidStrategyError):
        strangle(make_strangle_legs(put_strike=30.0, call_strike=30.0))


def test_strangle_com_lados_mistos() -> None:
    legs = make_strangle_legs()
    legs[0] = legs[0].mirrored()
    with pytest.raises(InvalidStrategyError):
        strangle(legs)


# ---------------------------------------------------------------------------
# butterfly
# ---------------------------------------------------------------------------


def test_butterfly_comprada_de_calls_e_valida() -> None:
    estrutura = butterfly(make_butterfly_legs(direction=Side.BUY))
    assert estrutura.name == "butterfly comprada"
    assert [leg.quantity for leg in estrutura.legs] == [10, 20, 10]


def test_butterfly_de_puts_e_valida() -> None:
    """All-puts tem payoff idêntico à all-calls — composição aceita."""
    estrutura = butterfly(make_butterfly_legs(option_type=OptionType.PUT))
    assert {leg.terms.option_type for leg in estrutura.legs} == {OptionType.PUT}


def test_butterfly_broken_wing_e_permitida() -> None:
    """Asas não precisam ser equidistantes; o pico continua em K2."""
    estrutura = butterfly(make_butterfly_legs(strikes=(28.0, 30.0, 33.0)))
    assert estrutura.legs[1].terms.strike == 30.0


def test_butterfly_com_tipos_mistos_e_composicao_errada() -> None:
    legs = make_butterfly_legs()
    legs[0] = make_leg(
        symbol="PETRP2800",
        terms=make_terms(strike=28.0, option_type=OptionType.PUT),
        side=legs[0].side,
        quantity=legs[0].quantity,
    )
    with pytest.raises(InvalidStrategyError):
        butterfly(legs)


def test_butterfly_exige_corpo_com_o_dobro_da_asa() -> None:
    legs = make_butterfly_legs()
    corpo_errado = make_leg(
        symbol=legs[1].symbol, terms=legs[1].terms, side=legs[1].side, quantity=15
    )
    with pytest.raises(InvalidStrategyError):
        butterfly([legs[0], corpo_errado, legs[2]])


def test_butterfly_com_asas_desiguais() -> None:
    legs = make_butterfly_legs()
    asa_errada = make_leg(symbol=legs[2].symbol, terms=legs[2].terms, side=legs[2].side, quantity=5)
    with pytest.raises(InvalidStrategyError):
        butterfly([legs[0], legs[1], asa_errada])


def test_butterfly_com_corpo_no_mesmo_lado_das_asas() -> None:
    legs = make_butterfly_legs()
    legs[1] = legs[1].mirrored()
    with pytest.raises(InvalidStrategyError):
        butterfly(legs)


def test_butterfly_com_strikes_coincidentes() -> None:
    with pytest.raises(InvalidStrategyError):
        butterfly(make_butterfly_legs(strikes=(28.0, 30.0, 30.0)))


def test_butterfly_com_asas_em_lados_distintos() -> None:
    legs = make_butterfly_legs()
    legs[0] = legs[0].mirrored()  # asa baixa muda de lado; a alta não
    with pytest.raises(InvalidStrategyError):
        butterfly(legs)


# ---------------------------------------------------------------------------
# vertical_spread — trava vertical nas duas direções (ROADMAP Sprint 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("option_type", "direction", "nome", "lado_strike_baixo"),
    [
        (OptionType.PUT, Side.SELL, "trava de alta com put (crédito)", Side.BUY),
        (OptionType.PUT, Side.BUY, "trava de baixa com put (débito)", Side.SELL),
        (OptionType.CALL, Side.BUY, "trava de alta com call (débito)", Side.BUY),
        (OptionType.CALL, Side.SELL, "trava de baixa com call (crédito)", Side.SELL),
    ],
)
def test_trava_vertical_nas_quatro_combinacoes(
    option_type: OptionType, direction: Side, nome: str, lado_strike_baixo: Side
) -> None:
    """Tendência = lado da perna de strike baixo; direção = lado da perna mais valiosa."""
    estrutura = vertical_spread(make_vertical_legs(option_type=option_type, direction=direction))
    assert estrutura.name == nome
    assert vertical_spread_direction(estrutura) is direction
    assert estrutura.legs[0].side is lado_strike_baixo


def test_trava_espelhada_inverte_a_direcao() -> None:
    """short == -long: espelhar a trava de crédito dá a de débito, e vice-versa."""
    credito = vertical_spread(make_vertical_legs(direction=Side.SELL))
    debito = vertical_spread(credito.mirrored().legs)
    assert vertical_spread_direction(debito) is Side.BUY
    assert debito.name == "trava de baixa com put (débito)"


def test_trava_legs_saem_ordenadas_por_strike() -> None:
    estrutura = vertical_spread(list(reversed(make_vertical_legs())))
    assert [leg.terms.strike for leg in estrutura.legs] == [28.0, 30.0]


def test_trava_nome_customizado_e_respeitado() -> None:
    assert vertical_spread(make_vertical_legs(), name="bull put PETR4").name == "bull put PETR4"


@pytest.mark.parametrize(
    ("option_type", "direction", "premiums"),
    [
        (OptionType.PUT, Side.SELL, (0.50, 0.90)),
        (OptionType.PUT, Side.BUY, (0.50, 0.90)),
        (OptionType.CALL, Side.SELL, (1.10, 0.35)),
        (OptionType.CALL, Side.BUY, (1.10, 0.35)),
    ],
)
def test_direcao_estrutural_coincide_com_o_fluxo_de_premios_sem_arbitragem(
    option_type: OptionType, direction: Side, premiums: tuple[float, float]
) -> None:
    """Prêmios monotônicos no strike (sem arbitragem): crédito <=> fluxo positivo."""
    estrutura = vertical_spread(
        make_vertical_legs(option_type=option_type, direction=direction, premiums=premiums)
    )
    fluxo = net_premium_cashflow(estrutura)
    assert (fluxo > 0.0) is (vertical_spread_direction(estrutura) is Side.SELL)


@pytest.mark.parametrize("n", [1, 3])
def test_trava_com_numero_errado_de_legs(n: int) -> None:
    legs = make_vertical_legs()
    extra = make_leg(symbol="PETRP3200", terms=make_terms(strike=32.0, option_type=OptionType.PUT))
    with pytest.raises(InvalidStrategyError):
        vertical_spread([*legs, extra][:n])


def test_trava_com_tipos_mistos_e_composicao_errada() -> None:
    """Put + call em strikes distintos é outra estrutura (risk reversal), não trava."""
    legs = make_vertical_legs()
    legs[1] = make_leg(
        symbol="PETRC3000",
        terms=make_terms(strike=30.0, option_type=OptionType.CALL),
        side=legs[1].side,
        quantity=legs[1].quantity,
    )
    with pytest.raises(InvalidStrategyError):
        vertical_spread(legs)


def test_trava_com_strikes_iguais_nao_e_estrutura() -> None:
    with pytest.raises(InvalidStrategyError):
        vertical_spread(make_vertical_legs(strikes=(30.0, 30.0)))


@pytest.mark.parametrize("lado", [Side.BUY, Side.SELL])
def test_trava_com_as_duas_pernas_do_mesmo_lado(lado: Side) -> None:
    legs = [leg if leg.side is lado else leg.mirrored() for leg in make_vertical_legs()]
    with pytest.raises(InvalidStrategyError):
        vertical_spread(legs)


def test_trava_com_quantidades_desiguais() -> None:
    legs = make_vertical_legs()
    legs[0] = make_leg(symbol=legs[0].symbol, terms=legs[0].terms, side=legs[0].side, quantity=7)
    with pytest.raises(InvalidStrategyError):
        vertical_spread(legs)

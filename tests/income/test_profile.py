"""Perfil bruto e líquido por preço — contra o oráculo numérico e os extremos da forma fechada.

O oráculo independente é ``_resultado_liquido`` de ``test_net_profile.py``
(somas ingênuas, perna a perna); os casos são os mesmos de lá.
"""

from collections.abc import Callable

import pytest
from hypothesis import given

from options_engine.domain.income.profile import (
    AXIS_POINTS,
    IncomeProfile,
    PositionLeg,
    ProfilePoint,
    income_profile,
    result_at_expiry,
)
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import ABS_INCOME_ORACLE_PER_SCALE, REL_INCOME_ORACLE, assert_close
from tests.income._builders import reference_cost_schedule
from tests.income.test_net_profile import _CASOS_FIXOS, _Caso, _casos, _resultado_liquido


def _pernas(caso: _Caso) -> tuple[list[PositionLeg], float | None]:
    opcoes = [
        PositionLeg(p.tipo, p.lado, p.preco, p.premio) for p in caso.pernas if p.tipo is not None
    ]
    acao = next((p.preco for p in caso.pernas if p.tipo is None), None)
    return opcoes, acao


def _confere(caso: _Caso, spots: list[float]) -> None:
    pernas, acao = _pernas(caso)
    piso = ABS_INCOME_ORACLE_PER_SCALE * caso.escala
    for s in spots:
        _, liquido = result_at_expiry(
            pernas,
            s,
            schedule=caso.tabela,
            shares=caso.metricas.reference_shares,
            stock_purchase_price=acao,
        )
        esperado = _resultado_liquido(caso.pernas, s, caso.tabela)
        assert_close(liquido, esperado, rel=REL_INCOME_ORACLE, abs_=piso, label=f"S={s}")


@pytest.mark.parametrize("fabrica", _CASOS_FIXOS)
def test_liquido_por_preco_bate_com_o_oraculo(fabrica: Callable[[], _Caso]) -> None:
    caso = fabrica()
    topo = 2.0 * max(caso.strikes)
    _confere(caso, [topo * i / 400 for i in range(401)] + list(caso.strikes))


@given(caso=_casos())
def test_liquido_por_preco_bate_com_o_oraculo_em_entradas_aleatorias(caso: _Caso) -> None:
    topo = 2.0 * max(caso.strikes)
    _confere(caso, [topo * i / 40 for i in range(41)])


@pytest.mark.parametrize("fabrica", _CASOS_FIXOS)
def test_extremos_da_forma_fechada_estao_no_perfil(fabrica: Callable[[], _Caso]) -> None:
    caso = fabrica()
    pernas, acao = _pernas(caso)
    m = caso.metricas
    piso = ABS_INCOME_ORACLE_PER_SCALE * caso.escala

    def liquido(s: float) -> float:
        return result_at_expiry(
            pernas, s, schedule=caso.tabela, shares=m.reference_shares, stock_purchase_price=acao
        )[1]

    assert_close(
        liquido(caso.cenario_de_ganho),
        m.net_max_gain_per_position,
        rel=REL_INCOME_ORACLE,
        abs_=piso,
        label="ganho",
    )
    assert_close(
        liquido(caso.cenario_de_perda),
        m.net_max_loss_per_position,
        rel=REL_INCOME_ORACLE,
        abs_=piso,
        label="perda",
    )


def test_bruto_da_venda_coberta_inclui_a_acao() -> None:
    """Ação comprada a 32 + call 34 vendida a 0,80: em S = 40, (34 - 32 + 0,80) x 100 = 280."""
    bruto, _ = result_at_expiry(
        [PositionLeg(OptionType.CALL, Side.SELL, 34.0, 0.80)],
        40.0,
        schedule=reference_cost_schedule(),
        shares=100,
        stock_purchase_price=32.0,
    )
    assert_close(bruto, 280.0, rel=1e-12, abs_=1e-9, label="ganho bruto exercido")


def test_eixo_vai_de_meio_a_uma_vez_e_meia_o_spot_com_quinas_e_breakevens() -> None:
    put = PositionLeg(OptionType.PUT, Side.SELL, 29.0, 0.30)
    perfil = income_profile(
        [put],
        current_spot=30.0,
        schedule=reference_cost_schedule(),
        shares=100,
        breakevens=(28.70, 28.7123, None, 99.0),
    )
    spots = [p.spot for p in perfil.points]
    assert spots[0] == 15.0 and spots[-1] == 45.0
    assert len(spots) == AXIS_POINTS + 4  # strike, vizinho exercido e dois breakevens dentro
    assert {29.0, 28.70, 28.7123} <= set(spots)
    assert 99.0 not in spots
    exercido = max(s for s in spots if s < 29.0)
    assert 29.0 - exercido < 1e-6  # o salto do exercício fica vertical no desenho
    no_strike = next(p for p in perfil.points if p.spot == 29.0)
    vizinho = next(p for p in perfil.points if p.spot == exercido)
    assert vizinho.net < no_strike.net  # custo de exercício só no lado exercido
    assert perfil.current_spot == 30.0


@pytest.mark.parametrize(
    "chamada",
    [
        lambda: income_profile(
            [], current_spot=30.0, schedule=reference_cost_schedule(), shares=100
        ),
        lambda: income_profile(
            [PositionLeg(OptionType.PUT, Side.SELL, 29.0, 0.3)],
            current_spot=0.0,
            schedule=reference_cost_schedule(),
            shares=100,
        ),
        lambda: income_profile(
            [PositionLeg(OptionType.PUT, Side.SELL, 29.0, 0.3)],
            current_spot=30.0,
            schedule=reference_cost_schedule(),
            shares=100,
            points=1,
        ),
        lambda: result_at_expiry(
            [PositionLeg(OptionType.PUT, Side.SELL, 29.0, 0.3)],
            -1.0,
            schedule=reference_cost_schedule(),
            shares=100,
        ),
        lambda: PositionLeg(OptionType.PUT, Side.SELL, 0.0, 0.3),
        lambda: PositionLeg(OptionType.PUT, Side.SELL, 29.0, -0.1),
    ],
)
def test_entradas_invalidas(chamada: Callable[[], object]) -> None:
    with pytest.raises(InvalidDomainValueError):
        chamada()


def test_strike_fora_do_eixo_nao_entra_e_strike_na_borda_nao_tem_vizinho_fora() -> None:
    longe = PositionLeg(OptionType.CALL, Side.BUY, 100.0, 0.01)
    na_borda = PositionLeg(OptionType.CALL, Side.SELL, 45.0, 0.05)
    perfil = income_profile(
        [na_borda, longe], current_spot=30.0, schedule=reference_cost_schedule(), shares=100
    )
    spots = [p.spot for p in perfil.points]
    assert 100.0 not in spots
    assert spots[-1] == 45.0  # o vizinho exercido de 45 passaria do topo do eixo
    assert len(spots) == AXIS_POINTS


@pytest.mark.parametrize(
    "spots", [(30.0,), (30.0, 30.0), (31.0, 30.0)], ids=["um", "repetido", "decrescente"]
)
def test_perfil_exige_dois_pontos_crescentes(spots: tuple[float, ...]) -> None:
    with pytest.raises(InvalidDomainValueError):
        IncomeProfile(points=tuple(ProfilePoint(s, 0.0, 0.0) for s in spots), current_spot=30.0)

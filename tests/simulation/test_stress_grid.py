"""Grid de estresse spot x vol — determinismo, forma e posição vencida."""

from itertools import pairwise

import pytest

from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import MixedAnnualizationBaseError
from options_engine.domain.model.factories import iron_condor, straddle
from options_engine.domain.model.scenarios import ScenarioGrid
from options_engine.domain.simulation import payoff_at_expiry, stress_grid
from tests._tolerances import ABS_SELF_FLOOR, INEQ_SLACK, REL_SELF, assert_close
from tests.domain._builders import make_condor_legs, make_snapshot, make_straddle_legs

_TTX = TimeToExpiry.from_days(126)  # 0.5 ano em BUSINESS_252
_GRID = ScenarioGrid(
    spot_min=24.0, spot_max=36.0, spot_steps=13, vol_min=0.15, vol_max=0.45, vol_steps=7
)


def test_forma_e_eixos_do_grid() -> None:
    resultado = stress_grid(
        iron_condor(make_condor_legs()), _GRID, time_to_expiry=_TTX, snapshot=make_snapshot()
    )
    assert len(resultado.spots) == 13
    assert len(resultado.vols) == 7
    assert len(resultado.values) == 13
    assert all(len(linha) == 7 for linha in resultado.values)
    # Extremos exatos por contrato do linspace — o canto do grid é o pedido.
    assert resultado.spots[0] == 24.0
    assert resultado.spots[-1] == 36.0
    assert resultado.vols[0] == 0.15
    assert resultado.vols[-1] == 0.45


def test_grid_e_deterministico_bit_a_bit() -> None:
    """Funções puras: mesma entrada, mesmo grid — inclusive o último bit.
    Guarda contra não-determinismo futuro (iteração de set, cache, etc.)."""
    condor = iron_condor(make_condor_legs())
    snap = make_snapshot()
    a = stress_grid(condor, _GRID, time_to_expiry=_TTX, snapshot=snap)
    b = stress_grid(condor, _GRID, time_to_expiry=_TTX, snapshot=snap)
    assert a == b  # VOs frozen: igualdade estrutural, célula a célula


def test_posicao_vencida_no_grid_e_intrinseco_descontado() -> None:
    """Decisão nº 5 + critério de aceite: célula com tau = 0 retorna o
    intrínseco (fator de desconto 1), sem NaN — o VO já rejeita NaN, e o
    valor bate com o payoff no vencimento."""
    condor = iron_condor(make_condor_legs())
    vencida = TimeToExpiry.from_days(0)
    resultado = stress_grid(condor, _GRID, time_to_expiry=vencida, snapshot=make_snapshot())
    for i, spot in enumerate(resultado.spots):
        for j in range(len(resultado.vols)):
            assert_close(
                resultado.values[i][j],
                payoff_at_expiry(condor, spot),
                rel=REL_SELF,
                abs_=ABS_SELF_FLOOR * 30.0,
                label=f"célula vencida ({i},{j})",
            )


def test_eixo_de_vol_move_o_straddle_comprado_para_cima() -> None:
    """Sanidade do eixo de vol: estrutura long vega (straddle comprado) tem
    linhas não-decrescentes ao longo do eixo de vol."""
    comprado = straddle(make_straddle_legs(direction=Side.BUY))
    resultado = stress_grid(comprado, _GRID, time_to_expiry=_TTX, snapshot=make_snapshot())
    folga = INEQ_SLACK * 30.0
    for linha in resultado.values:
        for menor_vol, maior_vol in pairwise(linha):
            assert maior_vol >= menor_vol - folga


def test_grid_com_base_misturada_e_rejeitado() -> None:
    snap_365 = make_snapshot(vol_base=DayCountConvention.CALENDAR_365)
    with pytest.raises(MixedAnnualizationBaseError):
        stress_grid(iron_condor(make_condor_legs()), _GRID, time_to_expiry=_TTX, snapshot=snap_365)

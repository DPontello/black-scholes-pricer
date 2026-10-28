"""``realized_volatility`` — vol realizada a partir de fechamentos, com o motivo da falta."""

import itertools
import math
import statistics

import pytest

from options_engine.adapters.outbound.cotahist.volatility import realized_volatility
from options_engine.domain.model.conventions import DayCountConvention, Volatility
from tests._tolerances import REL_SELF


def test_vol_realizada_confere_com_o_calculo_manual_e_explica_a_falta() -> None:
    closes = [30.0, 30.3, 29.9, 30.6, 30.2]
    retornos = [math.log(b / a) for a, b in itertools.pairwise(closes)]
    esperado = statistics.stdev(retornos) * math.sqrt(252)
    vol = realized_volatility(closes, window=4)
    assert isinstance(vol, Volatility) and vol.value == pytest.approx(esperado, rel=REL_SELF)
    motivo = realized_volatility(closes, window=21)
    assert isinstance(motivo, str) and "mínimo 22" in motivo


def test_base_de_anualizacao_e_business_252() -> None:
    vol = realized_volatility([30.0, 30.3, 29.9], window=2)
    assert isinstance(vol, Volatility)
    assert vol.annualization_base is DayCountConvention.BUSINESS_252


def test_so_os_ultimos_window_retornos_entram() -> None:
    closes = [10.0, 99.0, 30.0, 30.3, 29.9, 30.6]
    recentes = closes[-4:]
    retornos = [math.log(b / a) for a, b in itertools.pairwise(recentes)]
    esperado = statistics.stdev(retornos) * math.sqrt(252)
    vol = realized_volatility(closes, window=3)
    assert isinstance(vol, Volatility) and vol.value == pytest.approx(esperado, rel=REL_SELF)


def test_historico_insuficiente_traz_a_contagem_e_o_minimo() -> None:
    motivo = realized_volatility([30.0, 30.3, 29.9], window=21)
    assert motivo == (
        "histórico insuficiente para a vol realizada: 3 fechamentos até o pregão, "
        "mínimo 22 (21 retornos)"
    )


def test_vol_zero_e_motivo_nunca_numero() -> None:
    motivo = realized_volatility([30.0, 30.0, 30.0, 30.0], window=3)
    assert motivo == "vol realizada zero nos últimos 3 retornos"


@pytest.mark.parametrize("janela", [1, 0, -3])
def test_janela_menor_que_dois_retornos_e_recusada(janela: int) -> None:
    with pytest.raises(ValueError, match="window"):
        realized_volatility([30.0, 30.3, 29.9, 30.6], window=janela)

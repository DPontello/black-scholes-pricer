"""IV no prazo de 30 dias úteis, IV rank, percentil e regime de vol, contra contas feitas à mão."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.analytics.volatility import (
    ExpiryVol,
    HorizonVol,
    VolRegime,
    iv_at_horizon,
    iv_percentile,
    iv_rank,
    vol_regime,
)
from options_engine.domain.model.errors import InvalidDomainValueError
from tests._tolerances import ABS_REGRESSION_FLOOR, REL_REGRESSION, assert_close


def _iv(pontos: list[tuple[int, float]]) -> HorizonVol | None:
    return iv_at_horizon([ExpiryVol(dias, vol) for dias, vol in pontos])


def _perto(atual: float, esperado: float) -> None:
    assert_close(atual, esperado, rel=REL_REGRESSION, abs_=ABS_REGRESSION_FLOOR)


def test_iv_de_30_dias_interpola_a_variancia_total_e_nao_a_vol() -> None:
    """20 du a 30% e 40 du a 34%: w30 = (0,09 x 20 + 0,1156 x 40) / 2 / 252 = 3,212 / 252.

    IV 30 = sqrt(3,212 / 30) = 0,327210...; a média das vols daria 0,32.
    """
    resultado = _iv([(20, 0.30), (40, 0.34)])
    assert resultado is not None
    _perto(resultado.vol, 0.3272104317815474)
    assert resultado.extrapolated is False


def test_iv_de_30_dias_com_vol_caindo_no_prazo() -> None:
    """25 du a 32% e 45 du a 28%: w30 = 2,56 + (3,528 - 2,56) x 5 / 20 = 2,802 (em 1/252)."""
    resultado = _iv([(45, 0.28), (25, 0.32)])
    assert resultado is not None
    _perto(resultado.vol, 0.3056141357987225)


def test_vencimento_exato_no_prazo_vale_a_propria_vol() -> None:
    assert _iv([(10, 0.40), (30, 0.31), (50, 0.27)]) == HorizonVol(0.31, extrapolated=False)


def test_so_vencimentos_depois_do_prazo_vale_o_mais_perto_extrapolado() -> None:
    assert _iv([(60, 0.25), (35, 0.28)]) == HorizonVol(0.28, extrapolated=True)


def test_so_vencimentos_antes_do_prazo_vale_o_mais_perto_extrapolado() -> None:
    assert _iv([(10, 0.30), (25, 0.32)]) == HorizonVol(0.32, extrapolated=True)


def test_vencimento_com_menos_de_5_dias_uteis_fica_fora() -> None:
    """Sem o corte, 3 du a 50% e 40 du a 30% dariam uma IV de 30 dias bem acima de 30%."""
    assert _iv([(3, 0.50), (40, 0.30)]) == HorizonVol(0.30, extrapolated=True)
    no_minimo = _iv([(5, 0.50), (40, 0.30)])
    assert no_minimo is not None
    assert no_minimo.extrapolated is False
    assert no_minimo.vol > 0.30


def test_sem_vencimento_utilizavel_nao_ha_iv() -> None:
    assert _iv([]) is None
    assert _iv([(2, 0.40), (4, 0.35)]) is None


def test_vencimentos_repetidos_sao_recusados() -> None:
    with pytest.raises(InvalidDomainValueError, match="repetidos"):
        _iv([(20, 0.30), (20, 0.31), (40, 0.30)])


@pytest.mark.parametrize("vol", [0.0, -0.1, float("nan"), float("inf")])
def test_vol_do_vencimento_invalida(vol: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        ExpiryVol(20, vol)


def test_dias_uteis_negativos_e_prazo_invalido() -> None:
    with pytest.raises(InvalidDomainValueError):
        ExpiryVol(-1, 0.30)
    with pytest.raises(InvalidDomainValueError):
        iv_at_horizon([ExpiryVol(20, 0.30)], horizon_days=0)


@given(
    vol=st.floats(min_value=0.01, max_value=3.0),
    curto=st.integers(min_value=5, max_value=29),
    longo=st.integers(min_value=31, max_value=400),
)
def test_vol_plana_nos_vencimentos_da_a_mesma_vol_no_prazo(
    vol: float, curto: int, longo: int
) -> None:
    resultado = iv_at_horizon([ExpiryVol(curto, vol), ExpiryVol(longo, vol)])
    assert resultado is not None
    _perto(resultado.vol, vol)


@given(
    vol_curto=st.floats(min_value=0.01, max_value=3.0),
    vol_longo=st.floats(min_value=0.01, max_value=3.0),
    curto=st.integers(min_value=5, max_value=29),
    longo=st.integers(min_value=31, max_value=400),
)
def test_iv_no_prazo_fica_entre_as_vols_dos_vencimentos_vizinhos(
    vol_curto: float, vol_longo: float, curto: int, longo: int
) -> None:
    """A variância no prazo é média ponderada (pesos >= 0) das vizinhas: não sai do intervalo."""
    resultado = iv_at_horizon([ExpiryVol(curto, vol_curto), ExpiryVol(longo, vol_longo)])
    assert resultado is not None
    baixo, alto = sorted((vol_curto, vol_longo))
    assert baixo * (1 - REL_REGRESSION) <= resultado.vol <= alto * (1 + REL_REGRESSION)


_CEM_PREGOES = [0.200 + i / 1000 for i in range(100)]


def test_rank_e_percentil_numa_serie_de_100_pregoes() -> None:
    """Série de 0,200 a 0,299 e hoje 0,2505: rank 0,0505 / 0,099; 51 pregões abaixo de hoje."""
    rank = iv_rank(_CEM_PREGOES, 0.2505)
    assert rank is not None
    _perto(rank, 0.0505 / 0.099)
    assert iv_percentile(_CEM_PREGOES, 0.2505) == 0.51


def test_hoje_fora_do_historico_fica_nos_extremos() -> None:
    assert iv_rank(_CEM_PREGOES, 0.35) == 1.0
    assert iv_percentile(_CEM_PREGOES, 0.35) == 1.0
    assert iv_rank(_CEM_PREGOES, 0.10) == 0.0
    assert iv_percentile(_CEM_PREGOES, 0.10) == 0.0


def test_janela_e_dos_ultimos_252_pregoes() -> None:
    """Os 48 pregões mais antigos, a 90%, ficam fora da janela e não mexem no rank."""
    historico = [0.90] * 48 + [0.20 + (i % 100) / 1000 for i in range(252)]
    assert iv_rank(historico, 0.2505) == iv_rank(historico[-252:], 0.2505)
    rank = iv_rank(historico, 0.2505)
    assert rank is not None and rank < 1.0


def test_historico_curto_nao_tem_rank_nem_percentil() -> None:
    assert iv_rank(_CEM_PREGOES[:59], 0.25) is None
    assert iv_percentile(_CEM_PREGOES[:59], 0.25) is None
    assert iv_rank(_CEM_PREGOES[:60], 0.25) is not None
    assert iv_percentile(_CEM_PREGOES[:60], 0.25) is not None


def test_historico_todo_na_mesma_iv_nao_tem_rank() -> None:
    assert iv_rank([0.30] * 80, 0.30) is None
    assert iv_percentile([0.30] * 80, 0.30) == 0.0


def test_iv_invalida_no_rank() -> None:
    with pytest.raises(InvalidDomainValueError):
        iv_rank(_CEM_PREGOES, 0.0)
    with pytest.raises(InvalidDomainValueError):
        iv_percentile([*_CEM_PREGOES, float("nan")], 0.25)


@pytest.mark.parametrize(
    ("iv", "hv", "rank", "regime"),
    [
        (0.35, 0.30, 0.60, VolRegime.ALTA),
        (0.30, 0.30, 0.50, VolRegime.ALTA),
        (0.28, 0.30, 0.60, VolRegime.NEUTRA),
        (0.25, 0.30, 0.20, VolRegime.BAIXA),
        (0.30, 0.30, 0.30, VolRegime.BAIXA),
        (0.32, 0.30, 0.20, VolRegime.NEUTRA),
        (0.30, 0.30, 0.40, VolRegime.NEUTRA),
    ],
)
def test_regime_com_rank(iv: float, hv: float, rank: float, regime: VolRegime) -> None:
    assert vol_regime(iv, hv, rank) == (regime, False)


@pytest.mark.parametrize(
    ("iv", "regime"),
    [
        (0.34, VolRegime.ALTA),
        (0.30 * 1.1, VolRegime.NEUTRA),
        (0.30, VolRegime.NEUTRA),
        (0.30 * 0.9, VolRegime.NEUTRA),
        (0.26, VolRegime.BAIXA),
    ],
)
def test_regime_sem_rank_pela_margem_de_10_por_cento(iv: float, regime: VolRegime) -> None:
    assert vol_regime(iv, 0.30, None) == (regime, True)


def test_regime_com_entrada_invalida() -> None:
    with pytest.raises(InvalidDomainValueError):
        vol_regime(0.30, 0.0, 0.5)
    with pytest.raises(InvalidDomainValueError):
        vol_regime(0.30, 0.30, 1.5)

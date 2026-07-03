"""V&V do kernel de payoff — forma fechada exata e propriedades.

Oráculos: aritmética manual (payoff é soma/máximo, sem transcendentais —
tolerância REL_PAYOFF/ABS_PAYOFF da tabela) e as fórmulas fechadas de
breakeven (K2 - crédito / K3 + crédito no condor). Propriedades: todo
breakeven reportado é zero da curva; os extremos limitam a curva amostrada;
pesos espelhados espelham o payoff.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.kernel.payoff import (
    PayoffLeg,
    breakevens,
    intrinsic,
    linspace,
    payoff,
    payoff_extrema,
)
from options_engine.domain.model.errors import InvalidKernelInputError
from tests._tolerances import (
    ABS_BREAKEVEN,
    ABS_PAYOFF,
    ABS_SELF_FLOOR,
    INEQ_SLACK,
    REL_BREAKEVEN,
    REL_PAYOFF,
    REL_SELF,
    assert_close,
)

# Condor de crédito canônico: asas compradas em 26/34, corpo vendido em
# 28/32, crédito líquido 1.00 -> breakevens exatos em 27 e 33.
_CONDOR = (
    PayoffLeg(26.0, 1.0, False),
    PayoffLeg(28.0, -1.0, False),
    PayoffLeg(32.0, -1.0, True),
    PayoffLeg(34.0, 1.0, True),
)
_CREDITO = 1.0

# ---------------------------------------------------------------------------
# intrinsic e payoff — forma fechada
# ---------------------------------------------------------------------------


def test_intrinseco_call_e_put() -> None:
    # Ramos de forma fechada com caminho aritmético idêntico: == permitido.
    assert intrinsic(42.0, 40.0, is_call=True) == 2.0
    assert intrinsic(38.0, 40.0, is_call=True) == 0.0
    assert intrinsic(38.0, 40.0, is_call=False) == 2.0
    assert intrinsic(42.0, 40.0, is_call=False) == 0.0
    assert intrinsic(0.0, 40.0, is_call=False) == 40.0  # ganho máximo da put


def test_payoff_do_condor_nos_vertices_e_plateaus() -> None:
    """Geometria conhecida de cor: 4 vértices e os 3 platôs do condor."""
    esperados = {
        0.0: -2.0,  # platô esquerdo: put spread inteiro contra
        26.0: -2.0,  # vértice da asa baixa
        27.0: -1.0,  # rampa do put spread
        28.0: 0.0,  # vértice do corpo put
        30.0: 0.0,  # platô central: tudo OTM
        32.0: 0.0,  # vértice do corpo call
        33.0: -1.0,  # rampa do call spread
        34.0: -2.0,  # vértice da asa alta
        40.0: -2.0,  # platô direito
    }
    for spot, esperado in esperados.items():
        assert_close(
            payoff(spot, _CONDOR),
            esperado,
            rel=REL_PAYOFF,
            abs_=ABS_PAYOFF,
            label=f"condor payoff s={spot}",
        )


@pytest.mark.parametrize(
    ("s_t", "k"),
    [(-1.0, 40.0), (42.0, 0.0), (42.0, -40.0), (float("nan"), 40.0), (42.0, float("inf"))],
)
def test_intrinseco_rejeita_entradas_ilegais(s_t: float, k: float) -> None:
    with pytest.raises(InvalidKernelInputError):
        intrinsic(s_t, k, is_call=True)


def test_payoff_rejeita_leg_ilegal() -> None:
    with pytest.raises(InvalidKernelInputError):
        payoff(30.0, [PayoffLeg(0.0, 1.0, True)])
    with pytest.raises(InvalidKernelInputError):
        payoff(30.0, [PayoffLeg(30.0, float("inf"), True)])


# ---------------------------------------------------------------------------
# linspace — materialização determinística de eixo
# ---------------------------------------------------------------------------


def test_linspace_extremos_exatos_e_uniforme() -> None:
    malha = linspace(0.0, 100.0, 5)
    assert malha == (0.0, 25.0, 50.0, 75.0, 100.0)


def test_linspace_ultimo_ponto_e_hi_por_construcao() -> None:
    # 0.1 + 6*passo terminaria a ulps de 0.7; o contrato exige exatidão.
    assert linspace(0.1, 0.7, 7)[-1] == 0.7


def test_linspace_eixo_degenerado() -> None:
    assert linspace(30.0, 30.0, 1) == (30.0,)


@pytest.mark.parametrize(
    ("lo", "hi", "n"),
    [(0.0, 100.0, 0), (100.0, 0.0, 5), (0.0, 100.0, 1), (float("nan"), 1.0, 3)],
)
def test_linspace_rejeita_especificacao_ilegal(lo: float, hi: float, n: int) -> None:
    with pytest.raises(InvalidKernelInputError):
        linspace(lo, hi, n)


# ---------------------------------------------------------------------------
# breakevens — forma fechada por segmento
# ---------------------------------------------------------------------------


def test_breakevens_do_condor_batem_com_a_forma_fechada() -> None:
    """K2 - crédito e K3 + crédito — o critério de aceite da Sprint 2."""
    zeros = breakevens(_CONDOR, offset=_CREDITO)
    assert len(zeros) == 2
    assert_close(zeros[0], 28.0 - _CREDITO, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="K2-c")
    assert_close(zeros[1], 32.0 + _CREDITO, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="K3+c")


def test_breakeven_de_call_comprada_vem_da_cauda_direita() -> None:
    """Zero além do último strike: K + prêmio, resolvido pela inclinação."""
    zeros = breakevens([PayoffLeg(100.0, 1.0, True)], offset=-5.0)
    assert len(zeros) == 1
    assert_close(zeros[0], 105.0, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="call 105")


def test_breakeven_de_put_comprada_e_interior() -> None:
    zeros = breakevens([PayoffLeg(100.0, 1.0, False)], offset=-5.0)
    assert len(zeros) == 1
    assert_close(zeros[0], 95.0, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="put 95")


def test_breakevens_do_straddle_comprado() -> None:
    legs = [PayoffLeg(100.0, 1.0, True), PayoffLeg(100.0, 1.0, False)]
    zeros = breakevens(legs, offset=-10.0)
    assert len(zeros) == 2
    assert_close(zeros[0], 90.0, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="straddle 90")
    assert_close(zeros[1], 110.0, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="straddle 110")


def test_curva_sempre_positiva_nao_tem_breakeven() -> None:
    assert breakevens([PayoffLeg(100.0, 1.0, True)], offset=5.0) == ()


def test_plato_em_zero_reporta_os_nos_extremos() -> None:
    """Butterfly bruta: payoff == 0 em [0, K1] e em [K3, ∞) — os nós que
    tocam zero são reportados (semântica documentada, não acidente)."""
    fly = [PayoffLeg(28.0, 1.0, True), PayoffLeg(30.0, -2.0, True), PayoffLeg(32.0, 1.0, True)]
    assert breakevens(fly, offset=0.0) == (0.0, 28.0, 32.0)


def test_breakevens_rejeita_offset_ilegal() -> None:
    with pytest.raises(InvalidKernelInputError):
        breakevens(_CONDOR, offset=float("nan"))


# ---------------------------------------------------------------------------
# payoff_extrema — máximo/mínimo com None = ilimitado
# ---------------------------------------------------------------------------


def test_extremos_do_condor_de_credito_sao_limitados() -> None:
    maximo, minimo = payoff_extrema(_CONDOR, offset=_CREDITO)
    assert maximo is not None
    assert minimo is not None
    # Ganho máximo = crédito; perda máxima = crédito - largura da asa (2.0).
    assert_close(maximo, 1.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="condor max")
    assert_close(minimo, -1.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="condor min")


def test_call_comprada_tem_ganho_ilimitado() -> None:
    maximo, minimo = payoff_extrema([PayoffLeg(100.0, 1.0, True)], offset=-5.0)
    assert maximo is None
    assert minimo is not None
    assert_close(minimo, -5.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="call min")


def test_call_vendida_tem_perda_ilimitada() -> None:
    maximo, minimo = payoff_extrema([PayoffLeg(100.0, -1.0, True)], offset=5.0)
    assert minimo is None
    assert maximo is not None
    assert_close(maximo, 5.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="short call max")


def test_put_comprada_tem_ganho_maximo_em_s_zero() -> None:
    """O domínio é [0, ∞): a esquerda é limitada porque ação não vale < 0."""
    maximo, minimo = payoff_extrema([PayoffLeg(100.0, 1.0, False)], offset=-5.0)
    assert maximo is not None
    assert minimo is not None
    assert_close(maximo, 95.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="put max")
    assert_close(minimo, -5.0, rel=REL_PAYOFF, abs_=ABS_PAYOFF, label="put min")


def test_extrema_rejeita_offset_ilegal() -> None:
    with pytest.raises(InvalidKernelInputError):
        payoff_extrema(_CONDOR, offset=float("inf"))


# ---------------------------------------------------------------------------
# Propriedades (Hypothesis) — estruturas arbitrárias
# ---------------------------------------------------------------------------

# Strikes em meios-pontos (exatos em binário) e pesos inteiros: mantém a
# aritmética exata onde a forma fechada promete exatidão.
_LEG = st.builds(
    PayoffLeg,
    st.integers(min_value=2, max_value=400).map(lambda n: n / 2.0),
    st.integers(min_value=-5, max_value=5).filter(lambda w: w != 0).map(float),
    st.booleans(),
)
_LEGS = st.lists(_LEG, min_size=1, max_size=5).map(tuple)
_OFFSET = st.integers(min_value=-200, max_value=200).map(lambda n: n / 2.0)


def _escala(legs: tuple[PayoffLeg, ...], offset: float) -> float:
    return max(max(leg.k for leg in legs), abs(offset), 1.0)


@given(legs=_LEGS, offset=_OFFSET)
def test_todo_breakeven_reportado_e_zero_da_curva(
    legs: tuple[PayoffLeg, ...], offset: float
) -> None:
    escala = _escala(legs, offset)
    for zero in breakevens(legs, offset):
        assert_close(
            payoff(zero, legs) + offset,
            0.0,
            rel=0.0,
            abs_=ABS_BREAKEVEN * escala,
            label=f"f({zero}) deveria ser 0",
        )


@given(legs=_LEGS, offset=_OFFSET)
def test_extremos_limitam_a_curva_amostrada(legs: tuple[PayoffLeg, ...], offset: float) -> None:
    maximo, minimo = payoff_extrema(legs, offset)
    escala = _escala(legs, offset)
    folga = INEQ_SLACK * escala
    k_max = max(leg.k for leg in legs)
    amostras = [0.0, *(leg.k for leg in legs), *(leg.k + 0.25 for leg in legs), 2.0 * k_max + 10.0]
    for s in amostras:
        f = payoff(s, legs) + offset
        if maximo is not None:
            assert f <= maximo + folga
        if minimo is not None:
            assert f >= minimo - folga


@given(legs=_LEGS, spot=st.integers(min_value=0, max_value=500).map(lambda n: n / 2.0))
def test_pesos_espelhados_espelham_o_payoff(legs: tuple[PayoffLeg, ...], spot: float) -> None:
    """short == -long no nível do kernel — o anti-inversão-de-P&L."""
    espelhadas = tuple(PayoffLeg(leg.k, -leg.w, leg.is_call) for leg in legs)
    escala = _escala(legs, 0.0)
    assert_close(
        payoff(spot, espelhadas),
        -payoff(spot, legs),
        rel=REL_SELF,
        abs_=ABS_SELF_FLOOR * escala,
        label="espelho",
    )

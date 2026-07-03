"""Kernel de payoff no vencimento — functional core, forma fechada exata.

Funções puras sobre floats, stdlib only. O payoff de qualquer estrutura de
opções europeias no vencimento é PIECEWISE-LINEAR em S_T, com quebras
(kinks) exatamente nos strikes — isso permite breakevens e extremos em
forma fechada, sem root-finding numérico nem interpolação de amostras:
basta avaliar nos kinks e resolver a equação linear de cada segmento.

Convenções deste módulo:
    s_t     preço do subjacente NO VENCIMENTO, >= 0 (uma ação pode valer 0;
            para puts, é onde vive o ganho máximo).
    legs    sequência de ``PayoffLeg(k, w, is_call)`` — primitivos do
            kernel. ``w`` é o peso ASSINADO (side.sign * quantity, derivado
            no domínio): positivo = comprado, negativo = vendido.
    offset  constante somada à curva (ex.: fluxo líquido de prêmios, para
            P&L). O kernel não conhece "prêmio" — só a geometria.

Sem desconto aqui: payoff no vencimento é valor NO vencimento. Posição
vencida dentro de um grid (decisão nº 5) usa o ramo tau=0 de
``bs_outputs`` — intrínseco descontado com fator 1.

Nota de modelagem (mesma do kernel BS): ``is_call: bool`` é a representação
do functional core; no domínio o tipo é o enum ``OptionType``.
"""

from collections.abc import Sequence
from math import fsum, isfinite
from typing import NamedTuple

from options_engine.domain.model.errors import InvalidKernelInputError

__all__ = ["PayoffLeg", "breakevens", "intrinsic", "linspace", "payoff", "payoff_extrema"]


class PayoffLeg(NamedTuple):
    """Leg primitiva do kernel: strike, peso assinado, tipo como bool."""

    k: float
    w: float
    is_call: bool


def intrinsic(s_t: float, k: float, *, is_call: bool) -> float:
    """Valor intrínseco no vencimento: ``max(±(s_t - k), 0)``."""
    if not (isfinite(s_t) and isfinite(k)):
        raise InvalidKernelInputError(f"s_t e k devem ser finitos; recebido s_t={s_t!r}, k={k!r}")
    # `not (x >= 0)` / `not (x > 0)`: NaN compara False com tudo — rejeitado
    # mesmo sem a guarda de finitude acima (defesa em profundidade).
    if not (s_t >= 0.0):
        raise InvalidKernelInputError(f"s_t deve ser >= 0; recebido {s_t!r}")
    if not (k > 0.0):
        raise InvalidKernelInputError(f"strike deve ser > 0; recebido {k!r}")
    if is_call:
        return max(s_t - k, 0.0)
    return max(k - s_t, 0.0)


def _check_legs(legs: Sequence[PayoffLeg]) -> None:
    for leg in legs:
        if not (isfinite(leg.k) and leg.k > 0.0):
            raise InvalidKernelInputError(f"strike deve ser finito e > 0; recebido {leg.k!r}")
        if not isfinite(leg.w):
            raise InvalidKernelInputError(f"peso deve ser finito; recebido {leg.w!r}")


def payoff(s_t: float, legs: Sequence[PayoffLeg]) -> float:
    """Payoff bruto da estrutura no vencimento: ``Σ w_i · intrínseco_i``.

    ``fsum`` em ordem de entrada (determinística por contrato do chamador:
    legs canonicamente ordenadas por strike) — soma naive reordenada muda o
    último bit e quebra os testes de 1e-12 (CONVENTIONS §6).
    """
    _check_legs(legs)
    return fsum(leg.w * intrinsic(s_t, leg.k, is_call=leg.is_call) for leg in legs)


def linspace(lo: float, hi: float, n: int) -> tuple[float, ...]:
    """Malha uniforme determinística com extremos EXATOS.

    Materialização de eixo de grid (a especificação declarativa é o VO
    ``ScenarioGrid``; floats são daqui). O último ponto é ``hi`` por
    construção, não por acumulação — ``lo + (n-1)·passo`` termina a ulps de
    ``hi`` e um grid cujo canto não é o pedido é bug de auditoria.
    """
    if not (isfinite(lo) and isfinite(hi)):
        raise InvalidKernelInputError(f"extremos devem ser finitos; recebido lo={lo!r}, hi={hi!r}")
    if n < 1:
        raise InvalidKernelInputError(f"n deve ser >= 1; recebido {n!r}")
    if not (lo <= hi):
        raise InvalidKernelInputError(f"exigido lo <= hi; recebido lo={lo!r}, hi={hi!r}")
    if n == 1:
        if lo != hi:
            raise InvalidKernelInputError(
                f"n == 1 exige lo == hi (eixo degenerado); recebido lo={lo!r}, hi={hi!r}"
            )
        return (lo,)
    passo = (hi - lo) / (n - 1)
    return tuple(hi if i == n - 1 else lo + i * passo for i in range(n))


def _kinks(legs: Sequence[PayoffLeg]) -> list[float]:
    """Strikes únicos em ordem crescente — os nós da curva piecewise-linear.

    ``sorted`` sobre o ``set`` devolve ordem determinística; iterar o set
    cru mudaria a ordem das avaliações entre execuções (CONVENTIONS §6).
    """
    return sorted({leg.k for leg in legs})


def _right_tail_slope(legs: Sequence[PayoffLeg]) -> float:
    """Inclinação da curva à direita do último strike.

    Além de todos os strikes, cada call contribui ``w`` (intrínseco cresce
    1:1) e cada put contribui 0 (virou pó). ``fsum`` em ordem de entrada.
    """
    return fsum(leg.w for leg in legs if leg.is_call)


def breakevens(legs: Sequence[PayoffLeg], offset: float = 0.0) -> tuple[float, ...]:
    """Zeros EXATOS de ``payoff(s) + offset`` em [0, ∞), em ordem crescente.

    Forma fechada por segmento: a curva é linear entre nós consecutivos
    (0, strikes); um zero interior é a solução da equação linear do
    segmento; zeros exatamente sobre nós entram pelo teste ``f == 0``
    (igualdade permitida: ramo de forma fechada). Se um platô inteiro vale
    zero, seus dois nós extremos são reportados. Cauda direita: zero além
    do último strike existe sse ``f(k_max)`` e a inclinação terminal têm
    sinais opostos.
    """
    _check_legs(legs)
    if not isfinite(offset):
        raise InvalidKernelInputError(f"offset deve ser finito; recebido {offset!r}")
    nos = [0.0, *_kinks(legs)]
    valores = [payoff(s, legs) + offset for s in nos]

    zeros: list[float] = [no for no, f in zip(nos, valores, strict=True) if f == 0.0]
    for (x0, f0), (x1, f1) in zip(
        zip(nos, valores, strict=True), zip(nos[1:], valores[1:], strict=True), strict=False
    ):
        # Apenas mudança ESTRITA de sinal: zeros sobre nós já entraram acima,
        # e re-derivá-los por interpolação os duplicaria a ulps de distância.
        if (f0 < 0.0 < f1) or (f1 < 0.0 < f0):
            zeros.append(x0 + (-f0) * (x1 - x0) / (f1 - f0))

    inclinacao = _right_tail_slope(legs)
    f_max = valores[-1]
    if (f_max < 0.0 < inclinacao) or (inclinacao < 0.0 < f_max):
        zeros.append(nos[-1] + (-f_max) / inclinacao)

    return tuple(sorted(zeros))


def payoff_extrema(
    legs: Sequence[PayoffLeg], offset: float = 0.0
) -> tuple[float | None, float | None]:
    """(máximo, mínimo) de ``payoff(s) + offset`` em [0, ∞); None = ilimitado.

    Curva piecewise-linear: os extremos finitos vivem nos nós (0 e strikes).
    A cauda direita decide os infinitos — inclinação terminal positiva torna
    o máximo ilimitado (None); negativa, o mínimo. O domínio é limitado à
    esquerda por s = 0 (ação não vale negativo): o ganho máximo de uma put
    comprada é finito e vive exatamente aí.
    """
    _check_legs(legs)
    if not isfinite(offset):
        raise InvalidKernelInputError(f"offset deve ser finito; recebido {offset!r}")
    nos = [0.0, *_kinks(legs)]
    valores = [payoff(s, legs) + offset for s in nos]
    inclinacao = _right_tail_slope(legs)
    maximo: float | None = max(valores)
    minimo: float | None = min(valores)
    if inclinacao > 0.0:
        maximo = None
    elif inclinacao < 0.0:
        minimo = None
    return maximo, minimo

"""Distribuição normal padrão — functional core, stdlib only.

Fonte única de verdade para N(x) e n(x) em todo o motor (risco A1 da análise
de riscos): nenhum outro módulo pode reimplementar a CDF normal.
"""

from math import erfc, exp, pi, sqrt

__all__ = ["norm_cdf", "norm_pdf"]

_SQRT_2 = sqrt(2.0)
_INV_SQRT_2PI = 1.0 / sqrt(2.0 * pi)


def norm_cdf(x: float) -> float:
    """CDF da normal padrão.

    Computada como ``0.5 * erfc(-x / sqrt(2))`` em vez de
    ``0.5 * (1 + erf(x / sqrt(2)))``: na cauda negativa profunda a forma com
    ``erf`` sofre cancelamento catastrófico (``1 + (-0.999...)`` perde todos
    os dígitos significativos — risco A2), enquanto ``erfc`` preserva a
    precisão *relativa* até ~1e-300. ``math.erfc`` delega à libm da
    plataforma (~1 ulp).
    """
    return 0.5 * erfc(-x / _SQRT_2)


def norm_pdf(x: float) -> float:
    """Densidade da normal padrão."""
    return _INV_SQRT_2PI * exp(-0.5 * x * x)

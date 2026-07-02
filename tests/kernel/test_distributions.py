"""V&V direto de norm_cdf/norm_pdf — valores de literatura e propriedades de cauda.

Complementa a cobertura indireta via golden-master: um erro na CDF apareceria
nos preços, mas este arquivo o localiza na função exata e cobre o regime de
cauda profunda que nenhum caso de preço exercita.
"""

import itertools
import math

import pytest

from options_engine.domain.kernel.distributions import norm_cdf, norm_pdf
from tests._tolerances import ABS_CDF_TABULATED, ABS_SELF_FLOOR, REL_SELF, assert_close

# Valores padrão de literatura (tabelas da normal, 16 dígitos), reconferidos
# nesta máquina por duas rotas de libm independentes (erf e erfc) com
# divergência <= 1 ulp.
_TABULATED = [
    (0.0, 0.5),
    (1.0, 0.8413447460685429),
    (-1.0, 0.15865525393145705),
    (2.0, 0.9772498680518208),
    (3.0, 0.9986501019683699),
    (1.96, 0.9750021048517795),
]


@pytest.mark.parametrize(("x", "expected"), _TABULATED, ids=[f"x={x}" for x, _ in _TABULATED])
def test_norm_cdf_tabulated(x: float, expected: float) -> None:
    assert_close(norm_cdf(x), expected, rel=0.0, abs_=ABS_CDF_TABULATED, label=f"N({x})")


def test_norm_pdf_at_zero() -> None:
    assert_close(
        norm_pdf(0.0), 1.0 / math.sqrt(2.0 * math.pi), rel=REL_SELF, abs_=0.0, label="n(0)"
    )


@pytest.mark.parametrize("x", [0.1, 0.5, 1.0, 2.5, 5.0, 8.0])
def test_symmetry(x: float) -> None:
    """N(x) + N(-x) = 1 — a menos de ulps de erfc."""
    assert_close(
        norm_cdf(x) + norm_cdf(-x), 1.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label=f"simetria x={x}"
    )


def test_deep_negative_tail_preserves_relative_precision() -> None:
    """A forma erfc não sofre underflow prematuro na cauda (risco A2).

    Documenta POR QUE ``0.5*erfc(-x/sqrt(2))`` foi escolhida: a forma ingênua
    ``0.5*(1 + erf(x/sqrt(2)))`` já retorna 0.0 nesta região (erf satura em
    -1.0), perdendo TODA a informação relativa.
    """
    val = norm_cdf(-37.0)
    assert 0.0 < val < 1e-290
    naive = 0.5 * (1.0 + math.erf(-37.0 / math.sqrt(2.0)))
    assert naive == 0.0  # a alternativa rejeitada de fato colapsa


def test_monotonic_nondecreasing() -> None:
    grid = [-37.0, -8.0, -3.0, -1.0, 0.0, 1.0, 3.0, 8.0, 37.0]
    values = [norm_cdf(x) for x in grid]
    assert all(a <= b for a, b in itertools.pairwise(values))

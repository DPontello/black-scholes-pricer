"""Differential testing: kernel vs reimplementação independente com scipy.

Oráculo estruturalmente independente (VV-PLAN §3): a fórmula BSM é
reimplementada aqui do zero sobre ``scipy.stats.norm`` (CDF/PDF via Cephes,
caminho de código sem NENHUMA linha em comum com o kernel) e comparada em
10.000 conjuntos de parâmetros pseudo-aleatórios com seed fixa.

Isolamento: scipy vive em ``tests/oracle/requirements.txt`` e NUNCA no
``pyproject.toml`` — o core é stdlib-only. Este arquivo não segue o padrão
``test_*.py`` de propósito: a coleta local padrão (``pytest``) o ignora, e o
job de CI ``oracle`` o invoca por caminho explícito:

    pytest -q tests/oracle/scipy_oracle.py

O que cada oráculo pega: um bug na NOSSA ``norm_cdf`` aparece aqui (CDFs
independentes); um erro de fórmula copiado para cá não aparece — por isso o
hardening pós-v1.0 adiciona QuantLib como segundo oráculo (modo de falha
distinto). Ver docs/VV-PLAN.md.
"""

import math
import random

import pytest

from options_engine.domain.kernel.black_scholes import bs_outputs
from tests._tolerances import ABS_ORACLE_FLOOR, REL_ORACLE, assert_close

_scipy_stats = pytest.importorskip(
    "scipy.stats", reason="oráculo diferencial requer scipy (job de CI dedicado)"
)
_norm = _scipy_stats.norm

N_CASES = 10_000
SEED = 20260702  # fixa e registrada: falha é reproduzível, nunca sorteio


def _oracle_outputs(
    s: float, k: float, tau: float, r: float, sigma: float, q: float, *, is_call: bool
) -> dict[str, float]:
    """BSM reimplementado sobre scipy.stats.norm — independente do kernel."""
    sqrt_tau = math.sqrt(tau)
    d1 = (math.log(s / k) + (r - q + 0.5 * sigma**2) * tau) / (sigma * sqrt_tau)
    d2 = d1 - sigma * sqrt_tau
    df_r = math.exp(-r * tau)
    df_q = math.exp(-q * tau)
    pdf_d1 = float(_norm.pdf(d1))
    if is_call:
        cdf_d1, cdf_d2 = float(_norm.cdf(d1)), float(_norm.cdf(d2))
        price = s * df_q * cdf_d1 - k * df_r * cdf_d2
        delta = df_q * cdf_d1
        theta = -(s * sigma * df_q * pdf_d1) / (2.0 * sqrt_tau) + q * s * df_q * cdf_d1
        theta -= r * k * df_r * cdf_d2
        rho = k * tau * df_r * cdf_d2
    else:
        cdf_m1, cdf_m2 = float(_norm.cdf(-d1)), float(_norm.cdf(-d2))
        price = k * df_r * cdf_m2 - s * df_q * cdf_m1
        delta = -df_q * cdf_m1
        theta = -(s * sigma * df_q * pdf_d1) / (2.0 * sqrt_tau) - q * s * df_q * cdf_m1
        theta += r * k * df_r * cdf_m2
        rho = -k * tau * df_r * cdf_m2
    return {
        "price": price,
        "delta": delta,
        "gamma": df_q * pdf_d1 / (s * sigma * sqrt_tau),
        "theta_per_year": theta,
        "vega_per_vol_unit": s * df_q * pdf_d1 * sqrt_tau,
        "rho": rho,
    }


def _draw_params(rng: random.Random) -> tuple[float, float, float, float, float, float]:
    """Domínio realista do VV-PLAN §3, com amostragem log-uniforme nas escalas."""
    s = 10.0 ** rng.uniform(-2.0, 6.0)  # S em [0.01, 1e6]
    k = s * math.exp(rng.uniform(-3.0, 3.0))
    tau = 10.0 ** rng.uniform(math.log10(1.0 / 252.0), math.log10(30.0))
    r = rng.uniform(-0.05, 0.5)  # taxa negativa de propósito
    sigma = 10.0 ** rng.uniform(-4.0, math.log10(5.0))
    q = rng.uniform(0.0, 0.12)
    return s, k, tau, r, sigma, q


def test_kernel_matches_scipy_oracle_on_10k_random_cases() -> None:
    rng = random.Random(SEED)
    for i in range(N_CASES):
        s, k, tau, r, sigma, q = _draw_params(rng)
        floor = ABS_ORACLE_FLOOR * max(s, k)
        for is_call in (True, False):
            ours = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call)
            theirs = _oracle_outputs(s, k, tau, r, sigma, q, is_call=is_call)
            for field, expected in theirs.items():
                assert_close(
                    getattr(ours, field),
                    expected,
                    rel=REL_ORACLE,
                    abs_=floor,
                    label=(
                        f"caso {i} ({'call' if is_call else 'put'}) {field}: "
                        f"s={s!r}, k={k!r}, tau={tau!r}, r={r!r}, sigma={sigma!r}, q={q!r}"
                    ),
                )

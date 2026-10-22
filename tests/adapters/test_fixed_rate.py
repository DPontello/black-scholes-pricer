"""``FixedRateAdapter`` — taxa de configuração SEMPRE como VO com compounding."""

from math import log1p

from options_engine.adapters.outbound.fixed_rate import FixedRateAdapter
from options_engine.domain.model.conventions import Compounding, RiskFreeRate


def test_devolve_o_vo_injetado() -> None:
    vo = RiskFreeRate(0.10, Compounding.CONTINUOUS)
    assert FixedRateAdapter(vo).current_rate() == vo


def test_from_cdi_annual_carrega_a_convencao_do_cdi() -> None:
    """CDI é efetiva anual base 252 — a convenção viaja com o valor
    (CONVENTIONS §3), e a conversão para contínua é do DOMÍNIO."""
    rate = FixedRateAdapter.from_cdi_annual(0.15).current_rate()
    assert rate.rate == 0.15
    assert rate.compounding is Compounding.BUSINESS_DAILY_252
    # Mesmo caminho aritmético do VO (log1p) — igualdade exata permitida.
    assert rate.as_continuous() == log1p(0.15)

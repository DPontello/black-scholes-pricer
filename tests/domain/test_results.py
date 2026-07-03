"""Greeks e PricingResult — unidades no nome e auditoria por construção."""

import pytest

from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.results import Greeks, PricingResult
from tests.domain._builders import make_snapshot


def _greeks(**overrides: float) -> Greeks:
    valores: dict[str, float] = {
        "delta": 0.64,
        "gamma": 0.019,
        "theta_per_year": -6.41,
        "vega_per_vol_unit": 37.5,
        "rho": 53.2,
    }
    valores.update(overrides)
    return Greeks(**valores)


def test_gregas_carregam_unidade_no_nome() -> None:
    """theta_per_year e vega_per_vol_unit: a convenção faz parte do campo
    (CONVENTIONS §1) — rho presente desde o dia 1 (casa com rate_shift)."""
    g = _greeks()
    assert g.theta_per_year == -6.41
    assert g.vega_per_vol_unit == 37.5
    assert g.rho == 53.2


@pytest.mark.parametrize("campo", ["delta", "gamma", "theta_per_year", "vega_per_vol_unit", "rho"])
def test_grega_nao_finita_e_irrepresentavel(campo: str) -> None:
    with pytest.raises(InvalidDomainValueError):
        _greeks(**{campo: float("nan")})


def test_pricing_result_carrega_inputs_para_auditoria() -> None:
    """Todo número do sistema é reconstruível a posteriori: o resultado
    transporta snapshot, tau e model_id junto do preço."""
    snap = make_snapshot()
    ttx = TimeToExpiry.from_days(126)
    resultado = PricingResult(
        price=2.47,
        greeks=_greeks(),
        model_id="black-scholes-v1",
        snapshot=snap,
        time_to_expiry=ttx,
    )
    assert resultado.snapshot is snap
    assert resultado.time_to_expiry.convention is DayCountConvention.BUSINESS_252
    assert resultado.model_id == "black-scholes-v1"


def test_preco_nao_finito_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        PricingResult(
            price=float("inf"),
            greeks=_greeks(),
            model_id="black-scholes-v1",
            snapshot=make_snapshot(),
            time_to_expiry=TimeToExpiry.from_days(126),
        )


def test_model_id_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        PricingResult(
            price=2.47,
            greeks=_greeks(),
            model_id="",
            snapshot=make_snapshot(),
            time_to_expiry=TimeToExpiry.from_days(126),
        )

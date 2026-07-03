"""Greeks e PricingResult — unidades no nome e auditoria por construção."""

import pytest

from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.results import Greeks, PayoffProfile, PricingResult
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


# ---------------------------------------------------------------------------
# PayoffProfile — payoff bruto vs pnl líquido, por tipo
# ---------------------------------------------------------------------------


def _perfil_com_premio() -> PayoffProfile:
    return PayoffProfile(
        spots=(24.0, 30.0, 36.0),
        payoff_at_expiry=(-2.0, 0.0, -2.0),
        pnl=(-1.0, 1.0, -1.0),
        breakevens=(27.0, 33.0),
        max_gain=1.0,
        max_loss=-1.0,
    )


def test_perfil_com_premio_carrega_pnl_e_breakevens() -> None:
    perfil = _perfil_com_premio()
    assert perfil.pnl is not None
    assert perfil.breakevens == (27.0, 33.0)


def test_perfil_sem_premio_nao_tem_pnl_nem_breakevens() -> None:
    """Decisão nº 4: sem prêmio, só o payoff bruto existe — e o tipo
    distingue 'não calculável' (None) de 'sem cruzamento' (tupla vazia)."""
    perfil = PayoffProfile(
        spots=(24.0, 30.0, 36.0),
        payoff_at_expiry=(-2.0, 0.0, -2.0),
        pnl=None,
        breakevens=None,
        max_gain=0.0,
        max_loss=-2.0,
    )
    assert perfil.pnl is None
    assert perfil.breakevens is None


def test_pnl_e_breakevens_andam_juntos() -> None:
    with pytest.raises(InvalidDomainValueError):
        PayoffProfile(
            spots=(24.0, 30.0),
            payoff_at_expiry=(0.0, 0.0),
            pnl=None,
            breakevens=(27.0,),
            max_gain=None,
            max_loss=None,
        )


def test_max_gain_none_significa_ilimitado_e_e_legal() -> None:
    perfil = PayoffProfile(
        spots=(90.0, 100.0, 110.0),
        payoff_at_expiry=(0.0, 0.0, 10.0),
        pnl=(-5.0, -5.0, 5.0),
        breakevens=(105.0,),
        max_gain=None,  # call comprada: ganho ilimitado
        max_loss=-5.0,
    )
    assert perfil.max_gain is None


def test_eixo_de_spots_fora_de_ordem_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        PayoffProfile(
            spots=(30.0, 24.0),
            payoff_at_expiry=(0.0, 0.0),
            pnl=None,
            breakevens=None,
            max_gain=0.0,
            max_loss=0.0,
        )


def test_curvas_com_comprimento_errado_sao_irrepresentaveis() -> None:
    with pytest.raises(InvalidDomainValueError):
        PayoffProfile(
            spots=(24.0, 30.0, 36.0),
            payoff_at_expiry=(0.0, 0.0),
            pnl=None,
            breakevens=None,
            max_gain=0.0,
            max_loss=0.0,
        )
    with pytest.raises(InvalidDomainValueError):
        PayoffProfile(
            spots=(24.0, 30.0),
            payoff_at_expiry=(0.0, 0.0),
            pnl=(0.0,),
            breakevens=(),
            max_gain=0.0,
            max_loss=0.0,
        )


def test_valores_nao_finitos_sao_irrepresentaveis() -> None:
    with pytest.raises(InvalidDomainValueError):
        PayoffProfile(
            spots=(24.0, 30.0),
            payoff_at_expiry=(float("nan"), 0.0),
            pnl=None,
            breakevens=None,
            max_gain=0.0,
            max_loss=0.0,
        )
    with pytest.raises(InvalidDomainValueError):
        PayoffProfile(
            spots=(24.0, 30.0),
            payoff_at_expiry=(0.0, 0.0),
            pnl=None,
            breakevens=None,
            max_gain=float("inf"),  # ilimitado se escreve None, nunca inf
            max_loss=0.0,
        )

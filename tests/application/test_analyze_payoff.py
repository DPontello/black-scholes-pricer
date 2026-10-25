"""``AnalyzeStrategyPayoffService`` — materialização do eixo + delegação ao motor."""

from options_engine.application.ports.inbound import AnalyzeStrategyPayoffUseCase
from options_engine.application.use_cases.analyze_payoff import AnalyzeStrategyPayoffService
from options_engine.domain.model.scenarios import SpotAxis
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.engine import payoff_profile
from tests.domain._builders import make_condor_legs

AXIS = SpotAxis(spot_min=20.0, spot_max=40.0, steps=41)


def _condor() -> Strategy:
    return Strategy.create("condor", make_condor_legs())


def test_service_satisfaz_o_protocol_inbound() -> None:
    assert isinstance(AnalyzeStrategyPayoffService(), AnalyzeStrategyPayoffUseCase)


def test_eixo_materializado_com_extremos_exatos() -> None:
    profile = AnalyzeStrategyPayoffService().execute(_condor(), AXIS)
    assert len(profile.spots) == AXIS.steps
    # Extremos exatos por contrato do linspace do kernel (auditoria de grid).
    assert profile.spots[0] == AXIS.spot_min
    assert profile.spots[-1] == AXIS.spot_max


def test_delegacao_identica_ao_motor_de_simulacao() -> None:
    """O service só materializa o eixo: o perfil é o do domínio, bit a bit
    (mesmo binário, mesmo caminho aritmético — igualdade exata permitida)."""
    condor = _condor()
    via_service = AnalyzeStrategyPayoffService().execute(condor, AXIS)
    via_dominio = payoff_profile(condor, via_service.spots)
    assert via_service == via_dominio


def test_condor_com_premios_expoe_pnl_e_breakevens() -> None:
    """Decisão nº 4 atravessando a camada: com prêmio em todas as legs, o
    perfil traz pnl e breakevens (forma fechada: K2-1=27, K3+1=33)."""
    profile = AnalyzeStrategyPayoffService().execute(_condor(), AXIS)
    assert profile.pnl is not None
    assert profile.breakevens == (27.0, 33.0)


def test_condor_sem_premios_entrega_apenas_payoff_bruto() -> None:
    sem_premios = Strategy.create("condor sem prêmio", make_condor_legs(premiums=None))
    profile = AnalyzeStrategyPayoffService().execute(sem_premios, AXIS)
    assert profile.pnl is None
    assert profile.breakevens is None

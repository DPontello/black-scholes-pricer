"""VOs do ranking de renda — qualidade, marcas, invariantes e ordenação (plano da fase 2 §3.3)."""

from datetime import date

import pytest

from options_engine.domain.income import IncomeStructure, cash_secured_put_metrics
from options_engine.domain.income.metrics import IncomeMetrics
from options_engine.domain.income.profile import IncomeProfile, PositionLeg, income_profile
from options_engine.domain.income.ranking import (
    CandidateLeg,
    Exclusion,
    ExclusionScope,
    IncomeCandidate,
    IncomeRanking,
    RankingCriterion,
    rank_candidates,
)
from options_engine.domain.model.chain import LegPremium, PriceQuality
from options_engine.domain.model.enums import (
    ExerciseStyle,
    OptionType,
    PricingApproximation,
    Side,
)
from options_engine.domain.model.errors import InvalidDomainValueError
from tests.income._builders import make_cdi, reference_cost_schedule

NOVEMBRO = date(2026, 11, 19)


def _metricas(premio: float, du: int = 18) -> IncomeMetrics:
    return cash_secured_put_metrics(
        strike=30.0,
        premium_per_share=premio,
        business_days=du,
        cdi=make_cdi(),
        cost_schedule=reference_cost_schedule(),
    )


def _perna(
    symbol: str = "PETRW290",
    quality: PriceQuality = PriceQuality.EXECUTAVEL,
    option_type: OptionType = OptionType.PUT,
    style: ExerciseStyle = ExerciseStyle.EUROPEAN,
    strike: float = 29.0,
) -> CandidateLeg:
    return CandidateLeg(
        symbol=symbol,
        option_type=option_type,
        side=Side.SELL,
        strike=strike,
        expiry=NOVEMBRO,
        exercise_style=style,
        premium=LegPremium(0.30, quality),
        delta=-0.25,
        exercise_probability=0.22,
        implied_vol=0.30,
        trades=40,
        volume=1200.0,
        spread_pct=0.06,
    )


def _perfil() -> IncomeProfile:
    return income_profile(
        [PositionLeg(OptionType.PUT, Side.SELL, 29.0, 0.30)],
        current_spot=30.0,
        schedule=reference_cost_schedule(),
        shares=100,
    )


def _candidato(
    *pernas: CandidateLeg, premio: float = 0.30, underlying: str = "PETR4", du: int = 18
) -> IncomeCandidate:
    return IncomeCandidate(
        underlying=underlying,
        structure=IncomeStructure.CASH_SECURED_PUT,
        expiry=NOVEMBRO,
        legs=pernas or (_perna(),),
        metrics=_metricas(premio, du),
        underlying_book_available=True,
        profile=_perfil(),
    )


def test_qualidade_e_a_da_perna_mais_fraca() -> None:
    candidato = _candidato(_perna(), _perna("PETRW280", PriceQuality.INDICATIVO, strike=28.0))
    assert candidato.quality is PriceQuality.INDICATIVO


def test_marca_de_aproximacao_so_na_call_americana() -> None:
    europeia = _perna()
    americana = _perna("PETRK320", option_type=OptionType.CALL, style=ExerciseStyle.AMERICAN)
    put_americana = _perna("PETRW300", style=ExerciseStyle.AMERICAN)
    assert europeia.approximation is None
    assert put_americana.approximation is None
    assert americana.approximation is PricingApproximation.AMERICAN_CALL_AS_EUROPEAN
    assert _candidato(europeia).approximations == ()
    assert _candidato(americana).approximations == (PricingApproximation.AMERICAN_CALL_AS_EUROPEAN,)


@pytest.mark.parametrize(("symbol", "reason"), [("", "motivo"), ("PETR4", " ")])
def test_exclusao_exige_simbolo_e_motivo(symbol: str, reason: str) -> None:
    with pytest.raises(InvalidDomainValueError):
        Exclusion(ExclusionScope.SERIES, symbol, reason)


def test_candidato_sem_perna_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError, match="ao menos uma perna"):
        IncomeCandidate(
            "PETR4",
            IncomeStructure.CASH_SECURED_PUT,
            NOVEMBRO,
            (),
            _metricas(0.3),
            True,
            _perfil(),
        )


def test_ranking_so_aceita_executavel_e_referencia_nunca_e_executavel() -> None:
    executavel = _candidato()
    indicativo = _candidato(_perna(quality=PriceQuality.INDICATIVO))
    with pytest.raises(InvalidDomainValueError, match="EXECUTAVEL"):
        IncomeRanking(RankingCriterion.NET_ANNUAL_YIELD, (indicativo,), (), (), ())
    with pytest.raises(InvalidDomainValueError, match="referências"):
        IncomeRanking(RankingCriterion.NET_ANNUAL_YIELD, (), (executavel,), (), ())


def test_ordena_pelo_criterio_com_none_por_ultimo_e_separa_referencias() -> None:
    alto, baixo = _candidato(premio=0.40), _candidato(premio=0.20)
    hoje = _candidato(premio=0.50, du=0)
    teorico = _candidato(_perna(quality=PriceQuality.TEORICO), premio=0.60)
    ranking, referencias = rank_candidates(
        [baixo, hoje, teorico, alto], RankingCriterion.NET_ANNUAL_YIELD
    )
    assert ranking == (alto, baixo, hoje)
    assert referencias == (teorico,)


def test_empate_resolvido_pelo_ativo() -> None:
    vale, petr = _candidato(underlying="VALE3"), _candidato(underlying="PETR4")
    ranking, _ = rank_candidates([vale, petr], RankingCriterion.GROSS_PERIOD_YIELD)
    assert [c.underlying for c in ranking] == ["PETR4", "VALE3"]


@pytest.mark.parametrize(
    ("criterio", "campo"),
    [
        (RankingCriterion.NET_ANNUAL_YIELD, "net_yield_annual_252"),
        (RankingCriterion.GROSS_ANNUAL_YIELD, "yield_annual_252"),
        (RankingCriterion.NET_PERIOD_YIELD, "net_yield_period"),
        (RankingCriterion.GROSS_PERIOD_YIELD, "yield_period"),
        (RankingCriterion.NET_EXCESS_OVER_CDI, "net_excess_over_cdi_annual_252"),
    ],
)
def test_cada_criterio_le_o_campo_certo(criterio: RankingCriterion, campo: str) -> None:
    metricas = _metricas(0.3)
    assert criterio.value_of(metricas) == getattr(metricas, campo)

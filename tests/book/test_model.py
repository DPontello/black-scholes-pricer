"""Item do book: invariantes, o porquê pelas métricas, a separação por qualidade e os 5 melhores."""

from dataclasses import replace
from datetime import date

import pytest

from options_engine.domain.analytics.volatility import (
    DailyVol,
    VolRegime,
    end_of_day_context,
    vol_context,
)
from options_engine.domain.book.model import (
    BookItem,
    BookLeg,
    FamilyResult,
    Metric,
    MetricUnit,
    best_per_structure,
    passes_liquidity,
)
from options_engine.domain.book.presets import BookPreset, BookSettings
from options_engine.domain.model.chain import LegPremium, PriceQuality
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.templates import Family

NOVEMBRO = date(2026, 11, 19)


def _item(
    valor: float = 0.10,
    *,
    chave: str = "put_coberta",
    ativo: str = "PETR4",
    strike: float = 28.0,
    qualidade: PriceQuality = PriceQuality.EXECUTAVEL,
    porque: str = "rende {criterio} com {premio} de prêmio",
) -> BookItem:
    return BookItem(
        family=Family.RENDA,
        template_key=chave,
        underlying=ativo,
        expiry=NOVEMBRO,
        business_days=18,
        legs=(
            BookLeg(
                "PETRW280", OptionType.PUT, strike, Side.SELL, 100, LegPremium(0.30, qualidade)
            ),
        ),
        stock=None,
        criterion=Metric("criterio", "anualizado", valor, MetricUnit.PERCENT),
        metrics=(Metric("premio", "prêmio", 0.30, MetricUnit.CURRENCY),),
        reason=porque,
    )


def test_o_porque_e_montado_com_as_metricas_formatadas_por_quem_mostra() -> None:
    texto = _item().render_reason(lambda m: f"[{m.label} {m.value}]")
    assert texto == "rende [anualizado 0.1] com [prêmio 0.3] de prêmio"


def test_porque_que_cita_metrica_inexistente_e_recusado() -> None:
    with pytest.raises(InvalidDomainValueError, match="delta"):
        _item(porque="delta de {delta}")


def test_item_sem_perna_ou_com_metrica_repetida_e_recusado() -> None:
    base = _item()
    with pytest.raises(InvalidDomainValueError, match="perna"):
        replace(base, legs=())
    with pytest.raises(InvalidDomainValueError, match="repetidas"):
        replace(base, metrics=(base.criterion,))
    with pytest.raises(InvalidDomainValueError, match="finita"):
        Metric("x", "x", float("nan"), MetricUnit.NUMBER)


def test_familia_separa_executavel_das_referencias() -> None:
    executavel, indicativo = _item(), _item(qualidade=PriceQuality.INDICATIVO)
    resultado = FamilyResult.of([indicativo, executavel])
    assert (resultado.items, resultado.references) == ((executavel,), (indicativo,))
    with pytest.raises(InvalidDomainValueError, match="EXECUTAVEL"):
        FamilyResult(items=(indicativo,))
    with pytest.raises(InvalidDomainValueError, match="referências"):
        FamilyResult(references=(executavel,))


def test_cinco_melhores_por_estrutura_com_desempate_estavel() -> None:
    puts = [_item(v / 100, strike=20.0 + v) for v in range(8)]
    empate = [_item(0.50, ativo="VALE3"), _item(0.50, ativo="ITUB4")]
    travas = [_item(0.01, chave="trava_alta_put")]

    melhores = best_per_structure([*puts, *empate, *travas])

    assert [(i.template_key, i.criterion.value, i.underlying) for i in melhores] == [
        ("put_coberta", 0.50, "ITUB4"),
        ("put_coberta", 0.50, "VALE3"),
        ("put_coberta", 0.07, "PETR4"),
        ("put_coberta", 0.06, "PETR4"),
        ("put_coberta", 0.05, "PETR4"),
        ("trava_alta_put", 0.01, "PETR4"),
    ]
    menores = best_per_structure(puts, ascending=True, limit=2)
    assert [i.criterion.value for i in menores] == [0.0, 0.01]


def test_liquidez_exige_negocios_e_spread_medido() -> None:
    moderado = BookSettings.default(BookPreset.MODERADO)
    assert passes_liquidity(10, 0.20, moderado)
    assert not passes_liquidity(9, 0.05, moderado)
    assert not passes_liquidity(50, 0.21, moderado)
    assert not passes_liquidity(50, None, moderado)


def test_contexto_de_vol_com_rank_e_sem_rank() -> None:
    historico = [0.20 + i / 1000 for i in range(100)]
    com_rank = vol_context("PETR4", 0.35, 0.30, historico)
    assert (com_rank.iv_rank, com_rank.iv_percentile) == (1.0, 1.0)
    assert (com_rank.regime, com_rank.regime_from_hv) == (VolRegime.ALTA, False)
    curto = vol_context("PETR4", 0.35, 0.30, historico[:10])
    assert (curto.iv_rank, curto.regime, curto.regime_from_hv) == (None, VolRegime.ALTA, True)


def _pregao(dia: int, iv: float | None, hv: float | None, extrapolada: bool = False) -> DailyVol:
    return DailyVol(date(2026, 10, dia), 30.0, iv, extrapolada, hv)


def test_contexto_do_fim_de_dia_e_o_ultimo_pregao_contra_os_anteriores() -> None:
    historico = [_pregao(1, 0.20, None), _pregao(2, None, None), _pregao(5, 0.40, 0.30, True)]
    contexto = end_of_day_context("PETR4", historico)
    assert contexto == vol_context("PETR4", 0.40, 0.30, [0.20], extrapolated=True)


def test_contexto_do_fim_de_dia_sem_iv_ou_hv_no_ultimo_pregao_da_o_motivo() -> None:
    assert end_of_day_context("PETR4", []) == "PETR4: sem histórico de IV"
    sem_iv = end_of_day_context("PETR4", [_pregao(5, None, 0.30)])
    assert sem_iv == "PETR4: sem IV 30 no pregão 2026-10-05 (sem smile no spot)"
    sem_hv = end_of_day_context("PETR4", [_pregao(5, 0.30, None)])
    assert sem_hv == "PETR4: sem HV 21 no pregão 2026-10-05 (histórico curto)"

"""Família Renda: o ranking da Sprint 5 vira itens do book com o critério, os números e o porquê."""

from dataclasses import replace

from options_engine.domain.analytics.volatility import vol_context
from options_engine.domain.book.model import BookItem, BookLabel, BookStock, Metric
from options_engine.domain.book.presets import BookPreset, BookSettings
from options_engine.domain.book.renda import renda_items
from options_engine.domain.income.ranking import IncomeCandidate, IncomeRanking
from options_engine.domain.model.chain import PriceQuality
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side, StockOrigin
from options_engine.domain.model.templates import Family
from tests.application._mercado_falso import NOVEMBRO, serie
from tests.book._cadeias import DEZEMBRO, MODERADO, cadeia_larga, ranking


def _texto(m: Metric) -> str:
    return f"<{m.key}={m.value:.4f}>"


def _do_ranking(r: IncomeRanking, *simbolos: str) -> IncomeCandidate:
    return next(c for c in r.ranked if tuple(leg.symbol for leg in c.legs) == simbolos)


def _item(itens: tuple[BookItem, ...], *simbolos: str) -> BookItem:
    return next(i for i in itens if tuple(leg.symbol for leg in i.legs) == simbolos)


def _simbolos(itens: tuple[BookItem, ...]) -> set[tuple[str, ...]]:
    return {tuple(leg.symbol for leg in i.legs) for i in itens}


def test_venda_coberta_vira_item_pelo_anualizado_liquido_com_o_porque() -> None:
    r = ranking(cadeia_larga())
    candidato = _do_ranking(r, "PETRK320")

    item = _item(renda_items(r, MODERADO, {}).items, "PETRK320")

    assert (item.family, item.template_key, item.underlying) == (
        Family.RENDA,
        "venda_coberta",
        "PETR4",
    )
    assert (item.expiry, item.business_days) == (NOVEMBRO, candidato.metrics.business_days)
    assert item.stock == BookStock(Side.BUY, 100, StockOrigin.COMPRA)
    assert [(leg.side, leg.quantity) for leg in item.legs] == [(Side.SELL, 100)]
    assert item.criterion.key == "anual_liquido"
    assert item.criterion.value == candidato.metrics.net_yield_annual_252
    numeros = {m.key: m.value for m in item.metrics}
    assert numeros["premio"] == candidato.metrics.premium_per_share
    assert numeros["prob_exercicio"] == candidato.legs[0].exercise_probability
    assert numeros["delta"] == candidato.legs[0].delta
    assert "iv_rank" not in numeros
    texto = item.render_reason(_texto)
    assert "PETRK320" in texto
    assert f"<anual_liquido={candidato.metrics.net_yield_annual_252:.4f}>" in texto
    assert f"<premio={candidato.metrics.premium_per_share:.4f}>" in texto


def test_trava_de_credito_vira_item_pelo_retorno_sobre_o_risco() -> None:
    r = ranking(cadeia_larga())
    candidato = _do_ranking(r, "PETRX280", "PETRX260")

    item = _item(renda_items(r, MODERADO, {}).items, "PETRX280", "PETRX260")

    assert (item.template_key, item.expiry, item.stock) == ("trava_alta_put", DEZEMBRO, None)
    assert item.criterion.key == "retorno_risco"
    assert item.criterion.value == candidato.metrics.net_yield_period
    assert "PETRX280/PETRX260" in item.render_reason(_texto)


def test_put_coberta_e_trava_de_baixa_com_call_tem_a_estrutura_certa() -> None:
    arrojado = replace(BookSettings.default(BookPreset.ARROJADO), delta_min=0.15)
    resultado = renda_items(ranking(cadeia_larga(), arrojado), arrojado, {})
    chaves = {tuple(leg.symbol for leg in i.legs): i.template_key for i in resultado.items}
    assert chaves[("PETRX280",)] == "put_coberta"
    assert chaves[("PETRK320", "PETRK340")] == "trava_baixa_call"


def test_liquidez_do_preset_filtra_sem_virar_exclusao() -> None:
    """A trava K320/K340 tem a comprada com spread de 22%, acima dos 20% do Moderado."""
    r = ranking(cadeia_larga())
    assert ("PETRK320", "PETRK340") in {tuple(leg.symbol for leg in c.legs) for c in r.ranked}

    resultado = renda_items(r, MODERADO, {})

    assert ("PETRK320", "PETRK340") not in _simbolos(resultado.items)
    assert not any("PETRK340" in e.symbol for e in resultado.exclusions)
    poucos_negocios = replace(MODERADO, min_trades=13)
    assert renda_items(r, poucos_negocios, {}).items == ()


def test_referencias_e_exclusoes_do_ranking_passam_adiante() -> None:
    sem_book = serie("PETRX260", 26.0, OptionType.PUT, DEZEMBRO, book=False)
    r = ranking(cadeia_larga(sem_book))

    resultado = renda_items(r, MODERADO, {})

    referencia = _item(resultado.references, "PETRX280", "PETRX260")
    assert referencia.quality is PriceQuality.INDICATIVO
    assert ("PETRX280", "PETRX260") not in _simbolos(resultado.items)
    assert any(e.symbol == "PETRL340/?" and "sem strike" in e.reason for e in resultado.exclusions)


def test_ate_5_itens_por_estrutura_do_melhor_para_o_pior() -> None:
    resultado = renda_items(ranking(cadeia_larga()), MODERADO, {})
    for chave in {i.template_key for i in resultado.items}:
        valores = [i.criterion.value for i in resultado.items if i.template_key == chave]
        assert len(valores) <= 5
        assert valores == sorted(valores, reverse=True)


def test_iv_rank_do_contexto_entra_nos_numeros() -> None:
    contexto = vol_context("PETR4", 0.30, 0.25, [0.20 + i / 1000 for i in range(100)])
    item = _item(
        renda_items(ranking(cadeia_larga()), MODERADO, {"PETR4": contexto}).items, "PETRK320"
    )
    assert {m.key: m.value for m in item.metrics}["iv_rank"] == contexto.iv_rank


def test_call_americana_e_rotulada() -> None:
    americana = serie("PETRK320", 32.0, estilo=ExerciseStyle.AMERICAN)
    item = _item(renda_items(ranking(cadeia_larga(americana)), MODERADO, {}).items, "PETRK320")
    assert item.labels == (BookLabel.CALL_AMERICANA_COMO_EUROPEIA,)


def test_vencimento_hoje_fica_fora_do_book() -> None:
    r = ranking(cadeia_larga())
    hoje = [
        replace(
            c,
            metrics=replace(
                c.metrics,
                business_days=0,
                yield_annual_252=None,
                excess_over_cdi_annual_252=None,
                net_yield_annual_252=None,
                net_excess_over_cdi_annual_252=None,
            ),
        )
        for c in r.ranked
    ]
    assert renda_items(replace(r, ranked=tuple(hoje)), MODERADO, {}).items == ()

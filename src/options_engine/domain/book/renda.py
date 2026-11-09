"""Família Renda do book: o ranking da Sprint 5 em itens com o critério e o porquê (spec §3.3).

O ranking chega sem os filtros de liquidez (o ``BookService`` não os passa): eles valem só para
o que entra no book, e as referências, que não têm book completo, passariam sempre por elas.
"""

from collections.abc import Mapping

from options_engine.domain.analytics.volatility import VolContext
from options_engine.domain.book.model import (
    BookExclusion,
    BookItem,
    BookLabel,
    BookLeg,
    BookStock,
    FamilyResult,
    Metric,
    MetricUnit,
    passes_liquidity,
)
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.income.metrics import IncomeStructure
from options_engine.domain.income.ranking import IncomeCandidate, IncomeRanking
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.templates import Family

__all__ = ["renda_items"]

_PORQUE = {
    "venda_coberta": (
        "Venda coberta de {serie}: o prêmio de {premio} por ação rende {anual} ao ano, com "
        "{prob_exercicio} de probabilidade de exercício em {dias_uteis}."
    ),
    "put_coberta": (
        "Put coberta de {serie}: o prêmio de {premio} por ação rende {anual} ao ano sobre o "
        "caixa reservado, com {prob_exercicio} de probabilidade de exercício em {dias_uteis}."
    ),
    "trava_alta_put": (
        "Trava de alta com put {serie}: o crédito de {premio} por ação rende {retorno_risco} "
        "sobre o risco, com {prob_exercicio} de probabilidade de exercício da vendida em "
        "{dias_uteis}."
    ),
    "trava_baixa_call": (
        "Trava de baixa com call {serie}: o crédito de {premio} por ação rende {retorno_risco} "
        "sobre o risco, com {prob_exercicio} de probabilidade de exercício da vendida em "
        "{dias_uteis}."
    ),
}


def renda_items(
    ranking: IncomeRanking, settings: BookSettings, contexts: Mapping[str, VolContext]
) -> FamilyResult:
    """Itens do ranking que passam na liquidez do preset e as referências, com vencimento a pelo
    menos 1 dia útil; as exclusões do ranking passam adiante."""
    no_book = [
        c
        for c in ranking.ranked
        if all(passes_liquidity(leg.trades, leg.spread_pct, settings) for leg in c.legs)
    ]
    candidatos = [
        _item(c, contexts.get(c.underlying))
        for c in (*no_book, *ranking.references)
        if c.metrics.business_days >= 1
    ]
    return FamilyResult.of(
        candidatos, (BookExclusion(e.symbol, e.reason) for e in ranking.exclusions)
    )


def _template_key(candidate: IncomeCandidate) -> str:
    if candidate.structure is IncomeStructure.COVERED_CALL:
        return "venda_coberta"
    if candidate.structure is IncomeStructure.CASH_SECURED_PUT:
        return "put_coberta"
    vendida = candidate.legs[0]
    return "trava_alta_put" if vendida.option_type is OptionType.PUT else "trava_baixa_call"


def _item(candidate: IncomeCandidate, context: VolContext | None) -> BookItem:
    chave = _template_key(candidate)
    metricas = candidate.metrics
    vendida = candidate.legs[0]
    if chave in ("venda_coberta", "put_coberta"):
        assert metricas.yield_annual_252 is not None  # du >= 1: há anualização
        criterio = Metric("anual", "anualizado", metricas.yield_annual_252, MetricUnit.PERCENT)
    else:
        criterio = Metric(
            "retorno_risco", "retorno sobre o risco", metricas.yield_period, MetricUnit.PERCENT
        )
    apoio = [
        Metric("premio", "prêmio por ação", metricas.premium_per_share, MetricUnit.CURRENCY),
        Metric(
            "prob_exercicio",
            "probabilidade de exercício",
            vendida.exercise_probability,
            MetricUnit.PERCENT,
        ),
        Metric("delta", "delta da vendida", vendida.delta, MetricUnit.NUMBER),
        Metric("dias_uteis", "dias úteis", float(metricas.business_days), MetricUnit.BUSINESS_DAYS),
    ]
    if context is not None and context.iv_rank is not None:
        apoio.append(Metric("iv_rank", "IV rank", context.iv_rank, MetricUnit.PERCENT))
    acoes = metricas.reference_shares
    return BookItem(
        family=Family.RENDA,
        template_key=chave,
        underlying=candidate.underlying,
        expiry=candidate.expiry,
        business_days=metricas.business_days,
        legs=tuple(
            BookLeg(leg.symbol, leg.option_type, leg.strike, leg.side, acoes, leg.premium)
            for leg in candidate.legs
        ),
        stock=(
            BookStock(Side.BUY, acoes, StockOrigin.COMPRA)
            if candidate.structure is IncomeStructure.COVERED_CALL
            else None
        ),
        criterion=criterio,
        metrics=tuple(apoio),
        reason=_PORQUE[chave].replace("{serie}", "/".join(leg.symbol for leg in candidate.legs)),
        labels=(BookLabel.CALL_AMERICANA_COMO_EUROPEIA,) if candidate.approximations else (),
    )

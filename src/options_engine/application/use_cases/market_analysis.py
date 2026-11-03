"""``MarketAnalysisService``: o smile, a estrutura a termo e a IV 30 de hoje pela cadeia do momento,
contra o histórico de fim de dia dos COTAHIST (spec da semana 3, §4).

A HV 21 de hoje é a do último pregão do histórico; sem histórico, a vol realizada que a cadeia
traz. O rank e o percentil comparam a IV 30 de hoje com as dos pregões anteriores ao de hoje.
"""

from datetime import date, tzinfo

from options_engine.application.ports.inbound import MarketAnalysis, SmileView, TermPoint
from options_engine.application.ports.outbound import MarketPort, TradingCalendar, VolHistoryPort
from options_engine.application.use_cases._freshness import least_fresh
from options_engine.application.use_cases._time import resolve_time_to_expiry
from options_engine.domain.analytics.volatility import (
    DailyVol,
    ExpiryVol,
    iv_at_horizon,
    vol_context,
)
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.errors import DomainError
from options_engine.domain.pricing.smile import SeriesMarket, build_smile

__all__ = ["MarketAnalysisService"]

_BASE = DayCountConvention.BUSINESS_252


class MarketAnalysisService:
    def __init__(
        self,
        market: MarketPort,
        vol_history: VolHistoryPort,
        calendar: TradingCalendar,
        valuation_timezone: tzinfo,
    ) -> None:
        self._market = market
        self._history = vol_history
        self._calendar = calendar
        self._tz = valuation_timezone

    def analysis(self, symbol: str) -> MarketAnalysis:
        # A fonte pode trocar no meio da consulta: vale a menos fresca, como na cadeia.
        before = self._market.health()
        chain = self._market.get_chain(symbol)
        source = least_fresh(before, self._market.health())
        snapshot = chain.underlying
        pregao = snapshot.timestamp.astimezone(self._tz).date()
        smiles, termo = self._smiles(chain, pregao)
        historico = self._history.history(symbol)
        dias = () if isinstance(historico, str) else historico
        hoje = iv_at_horizon([ExpiryVol(p.business_days, p.vol) for p in termo])
        contexto = (
            None
            if hoje is None
            else vol_context(
                symbol,
                hoje.vol,
                _hv(dias) or snapshot.volatility.value,
                [d.iv30 for d in dias if d.session < pregao and d.iv30 is not None],
                extrapolated=hoje.extrapolated,
            )
        )
        return MarketAnalysis(
            symbol=symbol,
            spot=snapshot.spot,
            cdi_annual=snapshot.risk_free_rate.rate,
            history=dias,
            history_reason=historico if isinstance(historico, str) else None,
            today=contexto,
            today_reason=(
                None
                if contexto is not None
                else f"{symbol}: sem IV 30 hoje (nenhum vencimento com smile no spot)"
            ),
            smiles=smiles,
            term_structure=termo,
            source=source,
            timestamp=snapshot.timestamp,
        )

    def _smiles(
        self, chain: OptionChain, pregao: date
    ) -> tuple[tuple[SmileView, ...], tuple[TermPoint, ...]]:
        snapshot = chain.underlying
        smiles, termo = [], []
        for vencimento in sorted({q.contract.terms.expiry for q in chain.quotes}):
            try:
                du = self._calendar.business_days_between(pregao, vencimento)
            except DomainError:  # vencido ou fora da cobertura do calendário
                continue
            if du < 1:
                continue
            tau = resolve_time_to_expiry(vencimento, pregao, self._calendar, _BASE)
            mercado = SeriesMarket(
                snapshot.spot, snapshot.risk_free_rate.as_continuous(), tau.year_fraction
            )
            do_vencimento = [q for q in chain.quotes if q.contract.terms.expiry == vencimento]
            smile = build_smile(vencimento, do_vencimento, mercado)
            smiles.append(SmileView(vencimento, du, smile.points))
            vol = smile.vol_at(snapshot.spot)
            if vol is not None:
                termo.append(TermPoint(vencimento, du, vol))
        return tuple(smiles), tuple(termo)


def _hv(history: tuple[DailyVol, ...]) -> float | None:
    for dia in reversed(history):
        if dia.hv21 is not None:
            return dia.hv21
    return None

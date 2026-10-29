"""``MarketViewService``: a lista de ativos do perfil e a cadeia com IV e delta por série."""

from collections.abc import Callable, Sequence
from datetime import date, tzinfo
from typing import Final

from options_engine.application.ports.inbound import (
    DEFAULT_CHAIN_EXPIRIES,
    ChainView,
    ExpiryBlock,
    MarketStatus,
    SeriesRow,
    WatchRow,
)
from options_engine.application.ports.outbound import (
    CadastroFreshness,
    MarketPort,
    TradingCalendar,
)
from options_engine.application.use_cases._time import resolve_time_to_expiry
from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.enums import OptionType
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.pricing.smile import SeriesMarket, VolSmile, build_smile, series_risk

__all__ = ["MarketViewService"]

_FRESHNESS: Final = {DataSource.AO_VIVO: 2, DataSource.ATRASADO: 1, DataSource.FIM_DE_DIA: 0}


def _least_fresh(first: DataSource, second: DataSource) -> DataSource:
    return first if _FRESHNESS[first] <= _FRESHNESS[second] else second


def _order(row: SeriesRow) -> tuple[float, bool, str]:
    return row.strike, row.option_type is not OptionType.CALL, row.symbol


class MarketViewService:
    def __init__(
        self,
        market: MarketPort,
        calendar: TradingCalendar,
        valuation_timezone: tzinfo,
        day_count: DayCountConvention = DayCountConvention.BUSINESS_252,
        *,
        freshness: Callable[[], CadastroFreshness | str],
        cotahist_range: Callable[[], tuple[date, date] | None],
    ) -> None:
        if day_count is not DayCountConvention.BUSINESS_252:
            raise InvalidDomainValueError(
                f"a tela de mercado usa a convenção BUSINESS_252 (B3); recebido {day_count.name}"
            )
        self._market = market
        self._calendar = calendar
        self._timezone = valuation_timezone
        self._day_count = day_count
        self._freshness = freshness
        self._cotahist_range = cotahist_range

    def follow(self, watchlist: Sequence[str], chain_symbol: str | None) -> None:
        self._market.watch(tuple(watchlist), () if chain_symbol is None else (chain_symbol,))

    def quotes(self, watchlist: Sequence[str]) -> tuple[WatchRow, ...]:
        found = self._market.get_quotes(watchlist)
        rows = []
        for symbol in watchlist:
            value = found[symbol]  # o port responde por todos os símbolos pedidos
            if isinstance(value, UnderlyingQuote):
                rows.append(WatchRow(symbol, value, None))
            else:
                rows.append(WatchRow(symbol, None, value))
        return tuple(rows)

    def chain(self, symbol: str, expiries: int = DEFAULT_CHAIN_EXPIRIES) -> ChainView:
        if expiries < 1:
            raise InvalidDomainValueError(f"vencimentos deve ser >= 1; recebido {expiries!r}")
        # A fonte pode trocar no meio da consulta e a cadeia não diz de onde veio: vale a
        # saúde menos fresca, para um dado parado nunca sair como ao vivo.
        before = self._market.health()
        chain = self._market.get_chain(symbol)
        source = _least_fresh(before, self._market.health())

        snapshot = chain.underlying
        # Data da cotação, como no ranking: preço e tau do mesmo instante.
        valuation_date = snapshot.timestamp.astimezone(self._timezone).date()
        rate = snapshot.risk_free_rate.as_continuous()
        upcoming = sorted(
            {
                q.contract.terms.expiry
                for q in chain.quotes
                if q.contract.terms.expiry >= valuation_date
            }
        )[:expiries]
        blocks = []
        for expiry in upcoming:
            tau = resolve_time_to_expiry(expiry, valuation_date, self._calendar, self._day_count)
            market = SeriesMarket(snapshot.spot, rate, tau.year_fraction)
            of_expiry = [q for q in chain.quotes if q.contract.terms.expiry == expiry]
            smile = build_smile(expiry, of_expiry, market)
            rows = sorted((_row(q, smile, market) for q in of_expiry), key=_order)
            blocks.append(
                ExpiryBlock(
                    expiry=expiry,
                    business_days=self._calendar.business_days_between(valuation_date, expiry),
                    rows=tuple(rows),
                )
            )
        return ChainView(
            symbol=symbol,
            spot=snapshot.spot,
            source=source,
            timestamp=snapshot.timestamp,
            expiries=tuple(blocks),
            rejected=chain.rejected_series,
        )

    def status(self) -> MarketStatus:
        freshness = self._freshness()
        cadastro, reason = (
            (freshness, None) if isinstance(freshness, CadastroFreshness) else (None, freshness)
        )
        return MarketStatus(
            source=self._market.health(),
            cadastro=cadastro,
            cadastro_reason=reason,
            cotahist_range=self._cotahist_range(),
        )


def _row(quote: OptionQuote, smile: VolSmile, market: SeriesMarket) -> SeriesRow:
    terms = quote.contract.terms
    risk = series_risk(quote, smile, market)
    return SeriesRow(
        symbol=quote.contract.symbol,
        option_type=terms.option_type,
        strike=terms.strike,
        exercise_style=terms.exercise_style,
        bid=quote.bid,
        ask=quote.ask,
        last=quote.last,
        trades=quote.trades,
        volume=quote.volume,
        implied_vol=None if risk is None else risk.implied_vol,
        delta=None if risk is None else risk.delta,
    )

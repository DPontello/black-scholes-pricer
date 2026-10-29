"""``MarketViewService`` — implementação do contrato ``MarketViewUseCase``.

A tela de mercado do app: a lista de ativos do perfil e a cadeia de um ativo, com vol
implícita e delta por série. Orquestração pura sobre o ``MarketPort``: quem decide entre o
Tryd ao vivo e o fim de dia da B3 é o adapter (``FallbackMarket``); aqui só se monta o que a
tela mostra.

Regras:

- Data de valoração da cadeia = data da cotação do ativo no fuso de valoração, como no
  ranking: os preços e o tau precisam ser do mesmo instante, senão a vol implícita sai de
  um prazo que não é o dos preços. No fim de dia é o pregão do arquivo; ao vivo, o dia do
  último dado do Tryd.
- Tau BUS/252 pelo calendário, por vencimento; vol implícita pelo mid só com os dois lados
  do book, e delta pela vol da série ou, sem ela, pela do smile do vencimento (o mesmo
  ``series_risk`` do ranking).
- Rótulo da cadeia: a saúde da fonte é lida antes E depois da consulta, e vale a MENOS
  fresca das duas. A fonte pode trocar no meio (ponte que cai), e a cadeia não diz de onde
  veio: no pior caso um dado ao vivo sai como "fim de dia", nunca o contrário.
"""

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

# Da mais fresca para a menos fresca.
_FRESHNESS: Final = {DataSource.AO_VIVO: 2, DataSource.ATRASADO: 1, DataSource.FIM_DE_DIA: 0}


def _least_fresh(first: DataSource, second: DataSource) -> DataSource:
    return first if _FRESHNESS[first] <= _FRESHNESS[second] else second


def _order(row: SeriesRow) -> tuple[float, bool, str]:
    return row.strike, row.option_type is not OptionType.CALL, row.symbol


class MarketViewService:
    """Monta a lista de ativos e a cadeia da tela de mercado.

    ``freshness`` devolve a idade do cadastro mais recente ou o motivo de não haver;
    ``cotahist_range`` devolve a faixa de pregões dos COTAHIST importados. Os dois são
    lidos a cada ``status`` (a biblioteca muda quando o usuário importa um arquivo).
    """

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
        before = self._market.health()
        chain = self._market.get_chain(symbol)
        source = _least_fresh(before, self._market.health())

        snapshot = chain.underlying
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

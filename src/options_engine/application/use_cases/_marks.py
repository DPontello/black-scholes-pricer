"""Marcação da carteira: o preço de zerar cada posição aberta e, quando ele falta, o teórico."""

from collections.abc import Mapping, Sequence
from datetime import tzinfo

from options_engine.application.ports.outbound import MarketPort, TradingCalendar
from options_engine.application.ports.portfolio import LegMark
from options_engine.application.use_cases._freshness import least_fresh
from options_engine.application.use_cases._time import resolve_time_to_expiry
from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.model.chain import OptionChain, OptionQuote
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.errors import DomainError
from options_engine.domain.model.quotes import UnderlyingQuote
from options_engine.domain.portfolio.model import LegRef, OptionLegRef, StockLegRef
from options_engine.domain.pricing.smile import SeriesMarket, build_smile

__all__ = ["Marker"]


class Marker:
    """Uma consulta de mercado por marcação: as cotações das séries e das ações abertas e, só
    para a série sem preço de zerar, a cadeia do ativo (spot, taxa e vol do teórico)."""

    def __init__(
        self,
        market: MarketPort,
        calendar: TradingCalendar,
        tz: tzinfo,
        refs: Sequence[LegRef],
    ) -> None:
        self._market = market
        self._calendar = calendar
        self._tz = tz
        series = sorted({r.symbol for r in refs if isinstance(r, OptionLegRef)})
        acoes = sorted({r.symbol for r in refs if isinstance(r, StockLegRef)})
        # Como na cadeia: a fonte pode trocar no meio, e vale a menos fresca.
        antes = market.health()
        self._series: Mapping[str, OptionQuote | str] = (
            market.get_option_quotes(series) if series else {}
        )
        self._acoes: Mapping[str, UnderlyingQuote | str] = market.get_quotes(acoes) if acoes else {}
        self.source = least_fresh(antes, market.health())
        self._cadeias: dict[str, OptionChain | None] = {}
        self._teoricos: dict[str, float | None] = {}

    def mark(self, ref: LegRef, side: Side, quantity: int, average_price: float) -> LegMark:
        cotacao = (self._series if isinstance(ref, OptionLegRef) else self._acoes).get(
            ref.symbol, "sem cotação"
        )
        if isinstance(cotacao, str):
            preco, motivo = None, cotacao
        else:
            # Zerar a comprada é vender no bid; zerar a vendida é recomprar no ask.
            preco = cotacao.bid if side is Side.BUY else cotacao.ask
            motivo = (
                "sem oferta de compra para zerar"
                if side is Side.BUY
                else "sem oferta de venda para zerar"
            )
        if preco is not None:
            return LegMark(preco, side.sign * (preco - average_price) * quantity)
        teorico = self._teorico(ref) if isinstance(ref, OptionLegRef) else None
        return LegMark(None, None, teorico, motivo)

    def _teorico(self, ref: OptionLegRef) -> float | None:
        if ref.symbol not in self._teoricos:
            termos = ref.terms
            # Put americana não tem fórmula fechada (ADR-0002): sem teórico, em vez de um errado.
            americana = (
                termos.option_type is OptionType.PUT
                and termos.exercise_style is ExerciseStyle.AMERICAN
            )
            cadeia = None if americana else self._cadeia(termos.underlying)
            self._teoricos[ref.symbol] = (
                None if cadeia is None else _black_scholes(cadeia, ref, self._calendar, self._tz)
            )
        return self._teoricos[ref.symbol]

    def _cadeia(self, ativo: str) -> OptionChain | None:
        if ativo not in self._cadeias:
            try:
                self._cadeias[ativo] = self._market.get_chain(ativo)
            except DomainError:
                self._cadeias[ativo] = None
        return self._cadeias[ativo]


def _black_scholes(
    cadeia: OptionChain, ref: OptionLegRef, calendar: TradingCalendar, tz: tzinfo
) -> float | None:
    """BS com a vol do smile do vencimento no strike, senão a vol de referência do ativo."""
    termos = ref.terms
    snapshot = cadeia.underlying
    hoje = snapshot.timestamp.astimezone(tz).date()
    try:
        tau = resolve_time_to_expiry(
            termos.expiry, hoje, calendar, DayCountConvention.BUSINESS_252
        ).year_fraction
    except DomainError:
        return None
    taxa = snapshot.risk_free_rate.as_continuous()
    smile = build_smile(
        termos.expiry,
        [q for q in cadeia.quotes if q.contract.terms.expiry == termos.expiry],
        SeriesMarket(snapshot.spot, taxa, tau),
    )
    sigma = smile.vol_at(termos.strike)
    return bs_price(
        snapshot.spot,
        termos.strike,
        tau,
        taxa,
        snapshot.volatility.value if sigma is None else sigma,
        is_call=termos.option_type.is_call,
    )

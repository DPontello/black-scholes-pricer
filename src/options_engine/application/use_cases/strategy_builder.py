"""``StrategyBuilderService``: a estrutura montada com os preços da cadeia e o resultado dela."""

from collections.abc import Callable, Sequence
from datetime import tzinfo
from typing import Final

from options_engine.application.ports.inbound import (
    BuilderAnalysis,
    BuilderLegView,
    BuilderRequest,
    BuilderStockInput,
    BuilderStockView,
    ExpiryPoint,
    ExpiryResult,
    LegPriceOrigin,
    TodayResult,
)
from options_engine.application.ports.outbound import MarketPort, TradingCalendar
from options_engine.application.use_cases._freshness import least_fresh
from options_engine.application.use_cases._time import resolve_time_to_expiry
from options_engine.domain.income.costs import CostSchedule, schedule_on
from options_engine.domain.income.net_result import NetResult, net_result_breakdown
from options_engine.domain.kernel.payoff import linspace
from options_engine.domain.model.chain import (
    OptionChain,
    OptionQuote,
    PriceQuality,
    executable_premium,
)
from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry, Volatility
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    UnderlyingUnavailableError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.strategy import StockLeg, Strategy, StrategyLeg
from options_engine.domain.model.templates import TEMPLATES, Template, template
from options_engine.domain.pricing.smile import (
    SeriesMarket,
    VolSmile,
    build_smile,
    series_risk,
    theoretical_premium,
)
from options_engine.domain.simulation import net_premium_cashflow
from options_engine.domain.simulation.probability import probability_of_profit
from options_engine.domain.simulation.valuation import (
    american_call_approximated,
    expiry_payoff,
    expiry_pnl,
    expiry_summary,
    has_american,
    scenario_matrix,
    structure_greeks,
    today_curve,
)

__all__ = ["StrategyBuilderService"]

_BASE: Final = DayCountConvention.BUSINESS_252
_AXIS_POINTS: Final = 101
_ORIGEM: Final = {
    PriceQuality.EXECUTAVEL: LegPriceOrigin.EXECUTAVEL,
    PriceQuality.INDICATIVO: LegPriceOrigin.INDICATIVO,
    PriceQuality.TEORICO: LegPriceOrigin.TEORICO,
}


class StrategyBuilderService:
    def __init__(
        self,
        market: MarketPort,
        calendar: TradingCalendar,
        valuation_timezone: tzinfo,
        *,
        schedules: Sequence[CostSchedule],
        lots: Callable[[str], int | None],
    ) -> None:
        self._market = market
        self._calendar = calendar
        self._timezone = valuation_timezone
        self._schedules = tuple(schedules)
        self._lots = lots

    def templates(self) -> tuple[Template, ...]:
        return TEMPLATES

    def analyze(self, request: BuilderRequest) -> BuilderAnalysis:
        if not request.legs and request.stock is None:
            raise InvalidDomainValueError("a estrutura precisa de ao menos uma perna")
        before = self._market.health()
        chain = self._market.get_chain(request.underlying)
        source = least_fresh(before, self._market.health())
        snapshot = chain.underlying
        valuation_date = snapshot.timestamp.astimezone(self._timezone).date()
        quotes = [_quote_of(chain, leg.symbol) for leg in request.legs]
        expiry = quotes[0].contract.terms.expiry if quotes else valuation_date
        tau = resolve_time_to_expiry(expiry, valuation_date, self._calendar, _BASE)
        market = SeriesMarket(
            snapshot.spot, snapshot.risk_free_rate.as_continuous(), tau.year_fraction
        )
        smile = build_smile(
            expiry, [q for q in chain.quotes if q.contract.terms.expiry == expiry], market
        )
        avisos: list[str] = []

        pernas: list[StrategyLeg] = []
        vistas: list[BuilderLegView] = []
        for pedido, quote in zip(request.legs, quotes, strict=True):
            preco, origem = _price(pedido.price, quote, pedido.side, smile, market)
            if preco is None:
                avisos.append(
                    f"{quote.contract.symbol} sem preço: sem oferta, sem negócio e sem vol para o "
                    f"teórico"
                )
            lote = self._lots(quote.contract.symbol)
            if lote is not None and pedido.quantity % lote != 0:
                avisos.append(
                    f"{quote.contract.symbol}: quantidade {pedido.quantity} fora do lote de {lote}"
                )
            termos = quote.contract.terms
            pernas.append(
                StrategyLeg(quote.contract.symbol, termos, pedido.side, pedido.quantity, preco)
            )
            vistas.append(
                BuilderLegView(
                    quote.contract.symbol,
                    termos.option_type,
                    termos.strike,
                    termos.exercise_style,
                    pedido.side,
                    pedido.quantity,
                    lote,
                    preco,
                    origem,
                )
            )
        acao, vista_acao = _stock(request.underlying, request.stock, snapshot, chain)
        estrutura = _strategy(request.template, pernas, acao)
        if has_american(estrutura):
            avisos.append(
                "opção americana: o resultado no vencimento supõe que não há exercício antecipado"
            )
        if american_call_approximated(estrutura):
            avisos.append("call americana avaliada hoje como europeia (ADR-0002)")

        held = request.stock is not None and request.stock.origin is StockOrigin.CARTEIRA
        tabela = schedule_on(self._schedules, valuation_date)
        completa = estrutura.has_premiums
        breakevens = expiry_summary(estrutura)[0] if completa else ()
        eixo = _axis(snapshot.spot, [leg.terms.strike for leg in pernas], breakevens)
        liquidos = (
            [net_result_breakdown(estrutura, s, tabela, stock_already_held=held) for s in eixo]
            if completa
            else []
        )
        curva = tuple(
            ExpiryPoint(
                s,
                expiry_payoff(estrutura, s),
                expiry_pnl(estrutura, s) if completa else None,
                liquidos[i].net if completa else None,
            )
            for i, s in enumerate(eixo)
        )
        no_vencimento = _at_expiry(estrutura, liquidos, snapshot, tau, smile) if completa else None
        hoje, sem_hoje = (
            self._today(estrutura, quotes, eixo, snapshot, tau, smile, market)
            if completa
            else (None, "falta o preço de alguma perna")
        )
        return BuilderAnalysis(
            name=estrutura.name,
            underlying=request.underlying,
            expiry=expiry,
            business_days=self._calendar.business_days_between(valuation_date, expiry),
            spot=snapshot.spot,
            source=source,
            timestamp=snapshot.timestamp,
            legs=tuple(vistas),
            stock=vista_acao,
            curve=curva,
            at_expiry=no_vencimento,
            today=hoje,
            today_unavailable=sem_hoje,
            warnings=tuple(avisos),
        )

    def _today(
        self,
        estrutura: Strategy,
        quotes: Sequence[OptionQuote],
        eixo: Sequence[float],
        snapshot: MarketSnapshot,
        tau: TimeToExpiry,
        smile: VolSmile,
        market: SeriesMarket,
    ) -> tuple[TodayResult | None, str | None]:
        if tau.year_fraction == 0.0:
            return None, "vence hoje: vale o resultado no vencimento"
        vols = []
        for quote in quotes:
            risco = series_risk(quote, smile, market)
            if risco is None or risco.vol is None:
                return None, f"{quote.contract.symbol} sem vol para a avaliação de hoje"
            vols.append(Volatility(risco.vol, _BASE))
        taxa = snapshot.risk_free_rate
        try:
            curva = today_curve(estrutura, eixo, time_to_expiry=tau, rate=taxa, vols=vols)
        except UnsupportedExerciseStyleError as erro:
            return None, str(erro)
        return (
            TodayResult(
                curve=tuple(zip(eixo, curva, strict=True)),
                greeks=structure_greeks(
                    estrutura, snapshot.spot, time_to_expiry=tau, rate=taxa, vols=vols
                ),
                grid=scenario_matrix(
                    estrutura, snapshot.spot, time_to_expiry=tau, rate=taxa, vols=vols
                ),
                american_call_approximated=american_call_approximated(estrutura),
            ),
            None,
        )


def _quote_of(chain: OptionChain, symbol: str) -> OptionQuote:
    for quote in chain.quotes:
        if quote.contract.symbol == symbol:
            return quote
    for rejeitada in chain.rejected_series:
        if rejeitada.symbol == symbol:
            raise UnderlyingUnavailableError(f"{symbol}: {rejeitada.reason}")
    raise UnderlyingUnavailableError(
        f"{symbol} fora da cadeia de {chain.underlying.underlying_symbol} (vencimento não "
        f"assinado ou série inexistente)"
    )


def _price(
    digitado: float | None,
    quote: OptionQuote,
    side: Side,
    smile: VolSmile,
    market: SeriesMarket,
) -> tuple[float | None, LegPriceOrigin | None]:
    if digitado is not None:
        return digitado, LegPriceOrigin.DIGITADO
    premio = executable_premium(quote, side) or theoretical_premium(quote, smile, market)
    if premio is None:
        return None, None
    return premio.premium, _ORIGEM[premio.quality]


def _stock(
    underlying: str,
    pedido: BuilderStockInput | None,
    snapshot: MarketSnapshot,
    chain: OptionChain,
) -> tuple[StockLeg | None, BuilderStockView | None]:
    if pedido is None:
        return None, None
    if pedido.price is not None:
        preco, origem = pedido.price, LegPriceOrigin.DIGITADO
    elif pedido.origin is StockOrigin.CARTEIRA:
        raise InvalidDomainValueError(
            "ação da carteira: informe o preço médio da posição (a carteira ainda não o fornece)"
        )
    else:
        preco = snapshot.ask if pedido.side is Side.BUY else snapshot.bid
        origem = (
            LegPriceOrigin.EXECUTAVEL
            if chain.underlying_book_available
            else LegPriceOrigin.INDICATIVO
        )
    perna = StockLeg(underlying, pedido.side, pedido.quantity, preco)
    return perna, BuilderStockView(
        underlying, pedido.side, pedido.quantity, pedido.origin, preco, origem
    )


def _strategy(chave: str | None, pernas: Sequence[StrategyLeg], acao: StockLeg | None) -> Strategy:
    acoes = [] if acao is None else [acao]
    if chave is None:
        return Strategy.create("estrutura livre", pernas, acoes)
    try:
        modelo = template(chave)
    except KeyError:
        raise InvalidDomainValueError(f"modelo desconhecido: {chave!r}") from None
    return modelo.build(pernas, acao)


def _axis(spot: float, strikes: Sequence[float], breakevens: Sequence[float]) -> tuple[float, ...]:
    # Strikes e breakevens no eixo: a curva é linear por partes e as quinas a tornam exata.
    pontos = {*linspace(0.5 * spot, 1.5 * spot, _AXIS_POINTS), *strikes, *breakevens}
    return tuple(sorted(p for p in pontos if p >= 0.0))


def _at_expiry(
    estrutura: Strategy,
    liquidos: Sequence[NetResult],
    snapshot: MarketSnapshot,
    tau: TimeToExpiry,
    smile: VolSmile,
) -> ExpiryResult:
    breakevens, maximo, minimo = expiry_summary(estrutura)
    melhor = max(liquidos, key=lambda r: r.net)
    vol = smile.vol_at(snapshot.spot) or snapshot.volatility.value
    return ExpiryResult(
        net_premium=net_premium_cashflow(estrutura),
        breakevens=breakevens,
        max_gain=maximo,
        max_loss=minimo,
        net_max_gain=None if maximo is None else melhor.net,
        net_max_loss=None if minimo is None else min(r.net for r in liquidos),
        setup_costs=liquidos[0].setup,
        income_tax_at_max_gain=None if maximo is None else melhor.income_tax,
        probability_of_profit=probability_of_profit(
            estrutura,
            snapshot.spot,
            time_to_expiry=tau,
            rate=snapshot.risk_free_rate,
            vol=Volatility(vol, _BASE),
        ),
    )

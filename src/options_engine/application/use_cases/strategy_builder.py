"""``StrategyBuilderService``: a estrutura montada com os preços da cadeia e o resultado dela."""

from collections.abc import Callable, Sequence
from datetime import date, tzinfo
from math import inf, nextafter
from typing import Final

from options_engine.application.ports.inbound import (
    BuilderAnalysis,
    BuilderLegInput,
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
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    UnderlyingUnavailableError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.strategy import StockLeg, Strategy, StrategyLeg
from options_engine.domain.model.templates import TEMPLATES, Template, suggest_strikes, template
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
_QUANTIDADE_PADRAO: Final = 100
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
        portfolio_average: Callable[[str], float | None] = lambda _symbol: None,
    ) -> None:
        self._market = market
        self._calendar = calendar
        self._timezone = valuation_timezone
        self._schedules = tuple(schedules)
        self._lots = lots
        self._portfolio_average = portfolio_average

    def templates(self) -> tuple[Template, ...]:
        return TEMPLATES

    def suggest(self, underlying: str, template_key: str, expiry: date) -> BuilderRequest:
        modelo = _template(template_key)
        chain = self._market.get_chain(underlying)
        do_vencimento = [q for q in chain.quotes if q.contract.terms.expiry == expiry]
        if not do_vencimento:
            raise UnderlyingUnavailableError(f"{underlying}: sem séries no vencimento {expiry}")
        tipos = {perna.option_type for perna in modelo.legs}
        # Straddle e collar precisam de call e put no mesmo strike: só os strikes com os dois.
        strikes = set.intersection(
            *(
                {
                    q.contract.terms.strike
                    for q in do_vencimento
                    if q.contract.terms.option_type is t
                }
                for t in tipos
            )
        )
        sugeridos = suggest_strikes(modelo, sorted(strikes), chain.underlying.spot)
        pernas = tuple(
            BuilderLegInput(
                _serie(do_vencimento, perna.option_type, strike),
                perna.side,
                _QUANTIDADE_PADRAO * perna.ratio,
            )
            for perna, strike in zip(modelo.legs, sugeridos, strict=True)
        )
        acao = (
            None
            if modelo.stock is None
            else BuilderStockInput(modelo.stock, _QUANTIDADE_PADRAO, StockOrigin.COMPRA)
        )
        return BuilderRequest(underlying, pernas, acao, template_key)

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
        acao, vista_acao = _stock(
            request.underlying, request.stock, snapshot, chain, self._portfolio_average
        )
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
        no_vencimento = (
            _at_expiry(
                estrutura,
                [
                    net_result_breakdown(estrutura, s, tabela, stock_already_held=held)
                    for s in _extreme_candidates(snapshot.spot, eixo, pernas)
                ],
                snapshot,
                tau,
                smile,
            )
            if completa
            else None
        )
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
    portfolio_average: Callable[[str], float | None],
) -> tuple[StockLeg | None, BuilderStockView | None]:
    if pedido is None:
        return None, None
    if pedido.price is not None:
        preco, origem = pedido.price, LegPriceOrigin.DIGITADO
    elif pedido.origin is StockOrigin.CARTEIRA:
        medio = portfolio_average(underlying)
        if medio is None:
            raise InvalidDomainValueError(
                f"ação da carteira: nenhuma ação livre de {underlying} no perfil; "
                "informe o preço médio"
            )
        preco, origem = medio, LegPriceOrigin.PRECO_MEDIO
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
    return _template(chave).build(pernas, acao)


def _template(chave: str) -> Template:
    try:
        return template(chave)
    except KeyError:
        raise InvalidDomainValueError(f"modelo desconhecido: {chave!r}") from None


def _serie(quotes: Sequence[OptionQuote], option_type: OptionType, strike: float) -> str:
    return min(
        q.contract.symbol
        for q in quotes
        if q.contract.terms.option_type is option_type and q.contract.terms.strike == strike
    )


def _axis(spot: float, strikes: Sequence[float], breakevens: Sequence[float]) -> tuple[float, ...]:
    # Strikes e breakevens no eixo: a curva é linear por partes e as quinas a tornam exata.
    pontos = {*linspace(0.5 * spot, 1.5 * spot, _AXIS_POINTS), *strikes, *breakevens}
    return tuple(sorted(p for p in pontos if p >= 0.0))


def _extreme_candidates(
    spot: float, eixo: Sequence[float], pernas: Sequence[StrategyLeg]
) -> tuple[float, ...]:
    """Onde o líquido pode ter extremo: o eixo, o ativo a zero, cada strike e logo acima dele (onde
    o custo de exercício entra) e a cauda depois do último strike."""
    strikes = [leg.terms.strike for leg in pernas]
    return tuple(
        sorted(
            {
                0.0,
                *eixo,
                *strikes,
                *(nextafter(k, inf) for k in strikes),
                2.0 * max([spot, *strikes]),
            }
        )
    )


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

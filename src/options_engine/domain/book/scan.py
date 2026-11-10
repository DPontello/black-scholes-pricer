"""Varredura da cadeia de fim de dia para as famílias do book.

As séries de cada vencimento com o delta do smile (``series_risk``, o mesmo do painel de renda) e o
prêmio pelo lado (ADR-0004); a estrutura avaliada no vencimento pelo mesmo cálculo do montador
(``expiry_summary``, ``expiry_pnl`` e ``probability_of_profit``), em valores brutos: sem custos nem
IR, como a corretora mostra. A put americana fica fora, como no painel de renda (ADR-0002): o
delta dela não tem a aproximação europeia.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from math import log, sqrt

from options_engine.domain.book.model import (
    BookExclusion,
    BookLabel,
    BookLeg,
    passes_liquidity,
)
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.model.chain import (
    LegPremium,
    OptionChain,
    OptionQuote,
    PriceQuality,
    executable_premium,
)
from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry, Volatility
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.strategy import StockLeg, Strategy, StrategyLeg
from options_engine.domain.model.templates import template
from options_engine.domain.pricing.smile import (
    SeriesMarket,
    VolSmile,
    build_smile,
    series_risk,
    theoretical_premium,
)
from options_engine.domain.simulation import net_premium_cashflow
from options_engine.domain.simulation.probability import probability_of_profit
from options_engine.domain.simulation.valuation import expiry_pnl, expiry_summary

__all__ = [
    "Outcome",
    "PricedLeg",
    "ScannedExpiry",
    "ScannedSeries",
    "approximation_labels",
    "book_legs",
    "evaluate",
    "keeps_liquidity",
    "price_leg",
    "scan_chain",
    "std_devs_to",
]

_BASE = DayCountConvention.BUSINESS_252


@dataclass(frozen=True, slots=True)
class ScannedSeries:
    quote: OptionQuote
    delta: float
    implied_vol: float | None

    @property
    def symbol(self) -> str:
        return self.quote.contract.symbol

    @property
    def strike(self) -> float:
        return self.quote.contract.terms.strike

    @property
    def option_type(self) -> OptionType:
        return self.quote.contract.terms.option_type

    @property
    def spread_pct(self) -> float | None:
        bid, ask = self.quote.bid, self.quote.ask
        if bid is None or ask is None:
            return None
        return (ask - bid) / ((ask + bid) / 2.0)


@dataclass(frozen=True, slots=True)
class ScannedExpiry:
    """Séries analisadas de um vencimento, por strike."""

    expiry: date
    business_days: int
    market: SeriesMarket
    smile: VolSmile
    calls: tuple[ScannedSeries, ...]
    puts: tuple[ScannedSeries, ...]

    @property
    def time_to_expiry(self) -> TimeToExpiry:
        return TimeToExpiry.from_days(self.business_days)

    def of_type(self, option_type: OptionType) -> tuple[ScannedSeries, ...]:
        return self.calls if option_type is OptionType.CALL else self.puts

    def neighbor(self, series: ScannedSeries, steps: int) -> ScannedSeries | None:
        """A série do mesmo tipo ``steps`` strikes adiante (negativo = strikes menores)."""
        lista = self.of_type(series.option_type)
        indice = lista.index(series) + steps
        return lista[indice] if 0 <= indice < len(lista) else None

    def at_the_money(self, option_type: OptionType) -> ScannedSeries | None:
        """A série do strike mais perto do spot; no empate, o menor strike."""
        lista = self.of_type(option_type)
        if not lista:
            return None
        return min(lista, key=lambda s: (abs(s.strike - self.market.spot), s.strike))

    def in_delta_range(
        self, option_type: OptionType, settings: BookSettings
    ) -> tuple[ScannedSeries, ...]:
        return tuple(
            s
            for s in self.of_type(option_type)
            if settings.delta_min <= abs(s.delta) <= settings.delta_max
        )


@dataclass(frozen=True, slots=True)
class PricedLeg:
    series: ScannedSeries
    side: Side
    quantity: int
    premium: LegPremium


def scan_chain(
    chain: OptionChain, business_days: Mapping[date, int], expiries: int
) -> tuple[tuple[ScannedExpiry, ...], tuple[BookExclusion, ...]]:
    """Os ``expiries`` próximos vencimentos com pelo menos 1 dia útil (os dias úteis vêm de quem
    chama, pelo calendário), e as séries que ficaram fora com o motivo."""
    exclusoes = [BookExclusion(r.symbol, r.reason) for r in chain.rejected_series]
    datas = sorted(
        {
            q.contract.terms.expiry
            for q in chain.quotes
            if business_days.get(q.contract.terms.expiry, 0) >= 1
        }
    )[:expiries]
    vencimentos = []
    for vencimento in datas:
        du = business_days[vencimento]
        snapshot = chain.underlying
        mercado = SeriesMarket(
            snapshot.spot,
            snapshot.risk_free_rate.as_continuous(),
            TimeToExpiry.from_days(du).year_fraction,
        )
        quotes = [q for q in chain.quotes if q.contract.terms.expiry == vencimento]
        smile = build_smile(vencimento, quotes, mercado)
        series: list[ScannedSeries] = []
        for quote in quotes:
            analisada = _scan(quote, smile, mercado)
            if isinstance(analisada, BookExclusion):
                exclusoes.append(analisada)
            else:
                series.append(analisada)
        por_strike = sorted(series, key=lambda s: (s.strike, s.symbol))
        vencimentos.append(
            ScannedExpiry(
                vencimento,
                du,
                mercado,
                smile,
                tuple(s for s in por_strike if s.option_type is OptionType.CALL),
                tuple(s for s in por_strike if s.option_type is OptionType.PUT),
            )
        )
    return tuple(vencimentos), tuple(exclusoes)


def _scan(
    quote: OptionQuote, smile: VolSmile, market: SeriesMarket
) -> ScannedSeries | BookExclusion:
    termos = quote.contract.terms
    if termos.option_type is OptionType.PUT and termos.exercise_style is ExerciseStyle.AMERICAN:
        return BookExclusion(quote.contract.symbol, "put americana não suportada (ADR-0002)")
    risco = series_risk(quote, smile, market)
    if risco is None:
        return BookExclusion(
            quote.contract.symbol, "sem delta: sem vol implícita da série nem do smile"
        )
    return ScannedSeries(quote, risco.delta, risco.implied_vol)


def price_leg(
    expiry: ScannedExpiry, series: ScannedSeries, side: Side, quantity: int
) -> PricedLeg | str:
    """Prêmio pelo lado do book, TEÓRICO se a série é elegível; senão o motivo."""
    premio = executable_premium(series.quote, side) or theoretical_premium(
        series.quote, expiry.smile, expiry.market
    )
    if premio is None:
        lado = "bid para vender" if side is Side.SELL else "ask para comprar"
        return f"perna sem preço: {series.symbol} sem {lado}"
    return PricedLeg(series, side, quantity, premio)


def keeps_liquidity(legs: Iterable[PricedLeg], settings: BookSettings) -> bool:
    """Liquidez do preset em todas as pernas, se a estrutura vai para o book; as referências (com
    alguma perna INDICATIVO ou TEORICO) não passam por ela."""
    pernas = list(legs)
    if any(leg.premium.quality is not PriceQuality.EXECUTAVEL for leg in pernas):
        return True
    return all(
        passes_liquidity(leg.series.quote.trades, leg.series.spread_pct, settings) for leg in pernas
    )


def approximation_labels(legs: Iterable[PricedLeg]) -> tuple[BookLabel, ...]:
    """A marca da ADR-0002: o delta que escolheu a call americana é o da fórmula europeia."""
    americana = any(
        leg.series.option_type is OptionType.CALL
        and leg.series.quote.contract.terms.exercise_style is ExerciseStyle.AMERICAN
        for leg in legs
    )
    return (BookLabel.CALL_AMERICANA_COMO_EUROPEIA,) if americana else ()


def book_legs(legs: Iterable[PricedLeg]) -> tuple[BookLeg, ...]:
    return tuple(
        BookLeg(
            leg.series.symbol,
            leg.series.option_type,
            leg.series.strike,
            leg.side,
            leg.quantity,
            leg.premium,
        )
        for leg in legs
    )


@dataclass(frozen=True, slots=True)
class Outcome:
    """Resultado bruto no vencimento em moeda, sem custos nem IR: ``net_premium`` > 0 é crédito;
    extremos ``None`` = ilimitado; perda como valor <= 0. ``at_target``: o resultado com o ativo no
    alvo pedido."""

    net_premium: float
    breakevens: tuple[float, ...]
    max_gain: float | None
    max_loss: float | None
    probability_of_profit: float
    at_target: float | None = None


def evaluate(
    template_key: str,
    legs: Sequence[PricedLeg],
    chain: OptionChain,
    expiry: ScannedExpiry,
    *,
    stock: StockLeg | None = None,
    target: float | None = None,
) -> Outcome:
    estrutura = _strategy(template_key, legs, stock)
    breakevens, maximo, minimo = expiry_summary(estrutura)
    spot = chain.underlying.spot
    vol = expiry.smile.vol_at(spot) or chain.underlying.volatility.value
    return Outcome(
        net_premium=net_premium_cashflow(estrutura),
        breakevens=breakevens,
        max_gain=maximo,
        max_loss=minimo,
        probability_of_profit=probability_of_profit(
            estrutura,
            spot,
            time_to_expiry=expiry.time_to_expiry,
            rate=chain.underlying.risk_free_rate,
            vol=Volatility(vol, _BASE),
        ),
        at_target=None if target is None else expiry_pnl(estrutura, target),
    )


def _strategy(template_key: str, legs: Sequence[PricedLeg], stock: StockLeg | None) -> Strategy:
    pernas = [
        StrategyLeg(
            leg.series.symbol,
            leg.series.quote.contract.terms,
            leg.side,
            leg.quantity,
            leg.premium.premium,
        )
        for leg in legs
    ]
    return template(template_key).build(pernas, stock)


def std_devs_to(level: float, spot: float, vol: float, business_days: int) -> float:
    """Distância do spot até ``level`` em desvios-padrão.

    ``|ln(level / spot)| / (vol x sqrt(du / 252))``.
    """
    return abs(log(level / spot)) / (vol * sqrt(business_days / _BASE.days_per_year))

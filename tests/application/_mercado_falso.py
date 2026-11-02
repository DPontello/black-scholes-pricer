"""``MarketPort`` em memória: cadeia de PETR4 a 30 no pregão de 23/10, séries pelo BS."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.model.chain import OptionChain, OptionQuote, RejectedSeries
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import UnknownSymbolError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from tests.domain._builders import make_contract, make_snapshot, make_terms

PREGAO = date(2026, 10, 23)
NOVEMBRO = date(2026, 11, 19)
INSTANTE = datetime(2026, 10, 23, 21, 0, tzinfo=UTC)  # 18h em São Paulo
CDI = RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252)
CALENDARIO = StaticHolidayCalendar.from_packaged_data()
SPOT = 30.0
SIGMA = 0.30


def tau(vencimento: date) -> float:
    return CALENDARIO.business_days_between(PREGAO, vencimento) / 252.0


def preco_bs(strike: float, option_type: OptionType, vencimento: date = NOVEMBRO) -> float:
    return bs_price(
        SPOT, strike, tau(vencimento), CDI.as_continuous(), SIGMA, is_call=option_type.is_call
    )


def serie(
    symbol: str,
    strike: float,
    option_type: OptionType = OptionType.CALL,
    vencimento: date = NOVEMBRO,
    *,
    estilo: ExerciseStyle = ExerciseStyle.EUROPEAN,
    book: bool = True,
    last: float | str | None = "bs",
    trades: int = 12,
) -> OptionQuote:
    preco = preco_bs(strike, option_type, vencimento)
    return OptionQuote(
        contract=make_contract(
            symbol=symbol,
            terms=make_terms(
                underlying="PETR4",
                strike=strike,
                option_type=option_type,
                expiry=vencimento,
                exercise_style=estilo,
            ),
        ),
        bid=round(preco - 0.01, 2) if book else None,
        ask=round(preco + 0.01, 2) if book else None,
        last=round(preco, 2) if last == "bs" else last,  # type: ignore[arg-type]
        trades=trades,
        volume=1200.0 * preco,
        timestamp=INSTANTE,
    )


def series_padrao() -> tuple[OptionQuote, ...]:
    return (
        serie("PETRK280", 28.0),
        serie("PETRK300", 30.0),
        serie("PETRK320", 32.0),
        serie("PETRW280", 28.0, OptionType.PUT),
        serie("PETRW300", 30.0, OptionType.PUT),
        serie("PETRW320", 32.0, OptionType.PUT),
    )


def cadeia(
    quotes: Sequence[OptionQuote] | None = None,
    *,
    rejeitadas: tuple[RejectedSeries, ...] = (),
    book_do_ativo: bool = True,
) -> OptionChain:
    return OptionChain(
        underlying=make_snapshot(
            underlying_symbol="PETR4",
            spot=SPOT,
            bid=29.99 if book_do_ativo else SPOT,
            ask=30.01 if book_do_ativo else SPOT,
            mid=SPOT,
            rate=CDI.rate,
            compounding=CDI.compounding,
            vol=0.25,
            timestamp=INSTANTE,
        ),
        quotes=tuple(series_padrao() if quotes is None else quotes),
        rejected_series=rejeitadas,
        underlying_book_available=book_do_ativo,
    )


@dataclass
class MercadoFalso:
    """``healths``: a sequência que ``health()`` devolve (a última se repete). ``quotes`` e
    ``option_quotes``: o que os painéis devolvem; o que não está ali sai "aguardando dados"."""

    chains: dict[str, OptionChain] = field(default_factory=lambda: {"PETR4": cadeia()})
    healths: list[DataSource] = field(default_factory=list)
    watched: list[tuple[tuple[str, ...], tuple[str, ...], frozenset[date] | None]] = field(
        default_factory=list
    )
    quotes: dict[str, UnderlyingQuote | str] = field(default_factory=dict)
    option_quotes: dict[str, OptionQuote | str] = field(default_factory=dict)

    def health(self) -> DataSource:
        if len(self.healths) > 1:
            return self.healths.pop(0)
        return self.healths[0] if self.healths else DataSource.AO_VIVO

    def watch(
        self,
        underlyings: Sequence[str],
        chain_symbols: Sequence[str],
        chain_expiries: Collection[date] | None = None,
        portfolio_series: Sequence[str] = (),
    ) -> None:
        escolha = None if chain_expiries is None else frozenset(chain_expiries)
        self.watched.append((tuple(underlyings), tuple(chain_symbols), escolha))

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]:
        return {s: self.quotes.get(s, "aguardando dados") for s in symbols}

    def get_option_quotes(self, symbols: Sequence[str]) -> Mapping[str, OptionQuote | str]:
        return {s: self.option_quotes.get(s, "aguardando dados") for s in symbols}

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        if underlying_symbol not in self.chains:
            raise UnknownSymbolError(f"desconhecido: {underlying_symbol!r}")
        return self.chains[underlying_symbol]

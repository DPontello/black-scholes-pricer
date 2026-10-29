"""``TrydMarketFeed`` — cotações e cadeia ao vivo do Tryd, montadas sobre o quadro e a biblioteca.

Junta peças prontas: o ``TrydBridgeClient`` (assinatura e saúde da ponte), o ``LiveBoard``
(últimos valores crus), a tradução do Tryd para o domínio e os arquivos da B3 da biblioteca
(cadastro das séries; COTAHIST para fechamentos e vol realizada). Implementa o painel de
cotações, a assinatura ao vivo e a cadeia de opções.

Regras que atravessam o módulo:

- Fonte rotulada pela saúde da ponte: ``CONECTADA`` é ``AO_VIVO``, ``ATRASADA`` é
  ``ATRASADO``. Com a ponte ``DESCONECTADA`` o que sobrou no quadro é dado parado e NÃO sai
  como cotação nem como cadeia: o feed declara ``FIM_DE_DIA`` e quem compõe (o
  ``FallbackMarket``) serve os arquivos da B3.
- Lado ausente é ``None``, nunca ``0`` (a tradução já faz isso); ativo ou série que o Tryd
  ainda não carregou não aparece, e o motivo é o ``"aguardando dados"``.
- "Ativo desconhecido" é o ticker fora do cadastro mais recente E de todos os tickers à vista
  dos COTAHIST da biblioteca. Sem nenhum dos dois arquivos não há como julgar: ninguém é
  chamado de desconhecido.

Assinatura (``watch``): os ativos (e os dos símbolos de cadeia) com ``CAMPOS_ATIVO`` e, para
cada símbolo de cadeia, as séries do cadastro dos ``VENCIMENTOS_PADRAO`` próximos vencimentos
(a partir de hoje) com strike a até ``FAIXA_STRIKES`` do spot. O spot de referência é o último
``ULT`` do Tryd; enquanto ele não chegou, o último fechamento do COTAHIST; sem nenhum dos
dois, todos os strikes. O corte em ``topic_limit`` (``LIMITE_TOPICOS``) mantém os ativos
primeiro e depois os strikes mais perto do spot, séries inteiras: nunca um campo solto.

Séries de um ativo: as que o cadastro liga a ele (``UndrlygTckrSymb1``) e, quando o cadastro
não diz o ativo-objeto, as de mesma raiz (4 primeiras letras) — SÓ se ele é o único ativo à
vista dos COTAHIST com essa raiz (PETR3 e PETR4 a dividem). Com a raiz dividida o vínculo é
ambíguo: a série não é assinada e sai em ``rejected_series`` com o motivo, como no adapter COTAHIST,
em vez de virar, em silêncio, opção do ativo errado. Os vencimentos escolhidos contam as
séries ambíguas: sem isso, um ativo cujas séries são todas ambíguas teria cadeia vazia e muda.
Série sem estilo de exercício no cadastro sai em ``rejected_series`` (obrigatório pela mesa,
nunca EUROPEAN por omissão).

Cadeia: spot = ``ULT``; bid/ask do ativo = ``OCP``/``OVD`` e, sem os dois, spot nos três
lados com ``underlying_book_available = False`` (ADR-0004); vol realizada pelos fechamentos
do COTAHIST da biblioteca ou, sem histórico, a IV da série mais perto do dinheiro; taxa pelo
CDI do perfil.

Os avisos que a tradução emite a cada consulta (book cruzado, campo ilegível) são limitados a
um por minuto para cada (ticker, motivo): o polling repetiria o mesmo a cada segundo.
"""

import logging
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Final

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.b3files.loaded import LibraryLoader, LoadedLibrary
from options_engine.adapters.outbound.cotahist.volatility import realized_volatility
from options_engine.adapters.outbound.fixed_rate import FixedRateAdapter
from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.client import BridgeHealth, TrydBridgeClient
from options_engine.adapters.outbound.tryd.settings import (
    CAMPOS_ATIVO,
    CAMPOS_OPCAO,
    FAIXA_STRIKES,
    LIMITE_TOPICOS,
    VENCIMENTOS_PADRAO,
)
from options_engine.adapters.outbound.tryd.translation import to_option_quote, to_underlying_quote
from options_engine.application.ports.outbound import Clock, TradingCalendar
from options_engine.domain.model.chain import OptionChain, OptionQuote, RejectedSeries
from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.conventions import DayCountConvention, Volatility
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import UnderlyingUnavailableError, UnknownSymbolError
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.pricing.smile import SeriesMarket, mid_implied_vol

__all__ = ["TrydMarketFeed"]

_log = logging.getLogger(__name__)

Topic = tuple[str, str]

_ROOT_LENGTH: Final = 4  # a raiz do ticker, como no adapter COTAHIST
_VOL_WINDOW: Final = 21  # retornos da vol realizada, a mesma janela do adapter COTAHIST
_WARN_INTERVAL_S: Final = 60.0

_SOURCE_OF_HEALTH: Final = {
    BridgeHealth.CONECTADA: DataSource.AO_VIVO,
    BridgeHealth.ATRASADA: DataSource.ATRASADO,
    BridgeHealth.DESCONECTADA: DataSource.FIM_DE_DIA,
}


def _root(symbol: str) -> str:
    return symbol[:_ROOT_LENGTH]


class _WarnLimiter:
    """Deixa passar o aviso de cada (ticker, motivo) no máximo uma vez por minuto."""

    def __init__(self, monotonic: Callable[[], float]) -> None:
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._last_at: dict[tuple[str, str], float] = {}

    def __call__(self, ticker: str, motivo: str, mensagem: str) -> None:
        now = self._monotonic()
        with self._lock:
            last_at = self._last_at.get((ticker, motivo))
            if last_at is not None and now - last_at < _WARN_INTERVAL_S:
                return
            self._last_at[(ticker, motivo)] = now
        _log.warning("%s: %s", ticker, mensagem)


@dataclass(frozen=True, slots=True)
class _Row:
    """Série do cadastro com termos legíveis; ``ambiguity`` é o motivo do vínculo duvidoso.

    ``owner``: sem ativo-objeto no cadastro, o único ativo à vista da raiz nos COTAHIST.
    """

    symbol: str
    option_type: OptionType
    strike: float
    expiry: date
    style: ExerciseStyle | None
    ambiguity: str | None
    owner: str | None = None


@dataclass(frozen=True, slots=True)
class _SeriesIndex:
    """Séries do cadastro por ativo-objeto declarado e, as sem ativo-objeto, por raiz."""

    by_underlying: Mapping[str, tuple[_Row, ...]]
    by_root: Mapping[str, tuple[_Row, ...]]

    def rows_of(self, ticker: str) -> tuple[_Row, ...]:
        da_raiz = (r for r in self.by_root.get(_root(ticker), ()) if r.owner in (None, ticker))
        return (*self.by_underlying.get(ticker, ()), *da_raiz)


def _build_index(loaded: LoadedLibrary) -> _SeriesIndex:
    spots_by_root: dict[str, list[str]] = {}
    for symbol in sorted(loaded.spot_symbols):
        spots_by_root.setdefault(_root(symbol), []).append(symbol)
    by_underlying: dict[str, list[_Row]] = {}
    by_root: dict[str, list[_Row]] = {}
    for info in loaded.instruments.values():
        if info.option_type is None or info.strike is None or info.expiry is None:
            continue  # sem os termos da série não há o que assinar nem cotar
        owner = None
        if info.underlying_symbol is not None:
            alvo, ambiguity = by_underlying.setdefault(info.underlying_symbol, []), None
        else:
            raiz = _root(info.symbol)
            candidatos = spots_by_root.get(raiz, [])
            ambiguity = (
                f"vínculo com o ativo-objeto ambíguo: raiz {raiz!r} em {candidatos!r} "
                "e o cadastro não informa o ativo-objeto"
                if len(candidatos) > 1
                else None
            )
            owner = candidatos[0] if len(candidatos) == 1 else None
            alvo = by_root.setdefault(raiz, [])
        alvo.append(
            _Row(
                info.symbol,
                info.option_type,
                info.strike,
                info.expiry,
                info.exercise_style,
                ambiguity,
                owner,
            )
        )

    def ordenadas(linhas: list[_Row]) -> tuple[_Row, ...]:
        return tuple(
            sorted(linhas, key=lambda r: (r.expiry, r.option_type.value, r.strike, r.symbol))
        )

    return _SeriesIndex(
        {u: ordenadas(r) for u, r in by_underlying.items()},
        {raiz: ordenadas(r) for raiz, r in by_root.items()},
    )


def _in_band(strike: float, spot: float | None) -> bool:
    return spot is None or abs(strike - spot) <= FAIXA_STRIKES * spot


class TrydMarketFeed:
    """``QuoteBoardPort``, ``LiveFeedPort`` e ``OptionChainPort`` sobre o Tryd ao vivo.

    ``client`` e ``board`` são os da composição (o cliente alimenta o quadro). ``cdi_annual``
    devolve o CDI do perfil, lido a cada consulta; ``tz`` é o fuso de valoração. ``calendar``
    conta os dias úteis da IV de referência. ``topic_limit`` e ``monotonic`` (relógio dos avisos
    limitados) existem para os testes.
    """

    def __init__(
        self,
        client: TrydBridgeClient,
        board: LiveBoard,
        library: B3FileLibrary,
        calendar: TradingCalendar,
        clock: Clock,
        cdi_annual: Callable[[], float],
        tz: tzinfo = B3_UTC_OFFSET,
        *,
        topic_limit: int = LIMITE_TOPICOS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._board = board
        self._loader = LibraryLoader(library)
        self._calendar = calendar
        self._clock = clock
        self._cdi_annual = cdi_annual
        self._tz = tz
        self._topic_limit = topic_limit
        self._warn = _WarnLimiter(monotonic)
        # Duas assinaturas concorrentes calculariam a lista e a mandariam fora de ordem: a mais
        # velha venceria a mais nova. `_index_lock` só guarda o índice de séries da foto atual.
        self._watch_lock = threading.Lock()
        self._index_lock = threading.Lock()
        self._index: tuple[LoadedLibrary, _SeriesIndex] | None = None

    # --- LiveFeedPort ---------------------------------------------------------------------------

    def health(self) -> DataSource:
        return _SOURCE_OF_HEALTH[self._client.health()]

    def watch(self, underlyings: Sequence[str], chain_symbols: Sequence[str]) -> None:
        """Assina exatamente os ativos e as séries pedidos; o que sai da lista é cancelado."""
        assets = tuple(dict.fromkeys((*underlyings, *chain_symbols)))
        with self._watch_lock:
            units: list[tuple[Topic, ...]] = [tuple((a, c) for c in CAMPOS_ATIVO) for a in assets]
            loaded = self._loader.load()
            if not isinstance(loaded, str):
                units += self._series_units(loaded, tuple(dict.fromkeys(chain_symbols)))
            self._client.ensure_subscribed(self._within_limit(units))

    # --- QuoteBoardPort -------------------------------------------------------------------------

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]:
        loaded = self._loader.load()
        source = self.health()
        now = self._now()
        result: dict[str, UnderlyingQuote | str] = {}
        for symbol in symbols:
            if not isinstance(loaded, str) and not loaded.knows(symbol):
                result[symbol] = "ativo desconhecido"
                continue
            quote = None if source is DataSource.FIM_DE_DIA else self._quote(symbol, source, now)
            result[symbol] = "aguardando dados" if quote is None else quote
        return result

    # --- OptionChainPort ------------------------------------------------------------------------

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        loaded = self._loader.load()
        if isinstance(loaded, str):
            raise UnderlyingUnavailableError(f"{underlying_symbol}: {loaded}")
        if not loaded.knows(underlying_symbol):
            raise UnknownSymbolError(
                f"subjacente desconhecido no cadastro e nos COTAHIST: {underlying_symbol!r}"
            )
        source = self.health()
        if source is DataSource.FIM_DE_DIA:
            raise UnderlyingUnavailableError(f"{underlying_symbol}: ponte do Tryd desconectada")
        now = self._now()
        quote = self._quote(underlying_symbol, source, now)
        if quote is None:
            raise UnderlyingUnavailableError(f"{underlying_symbol}: aguardando dados do Tryd")
        if quote.last is None:
            raise UnderlyingUnavailableError(f"{underlying_symbol}: sem último preço (ULT) no Tryd")
        spot = quote.last
        bid, ask = quote.bid, quote.ask
        if bid is not None and ask is not None:
            mid, book_available = (bid + ask) / 2.0, True
        else:  # bid/ask não observados nunca se passam por book real (ADR-0004)
            bid = ask = mid = spot
            book_available = False
        rate = FixedRateAdapter.from_cdi_annual(self._cdi_annual()).current_rate()
        quotes, rejected = self._series(loaded, underlying_symbol, spot, now)
        volatility = realized_volatility(
            [valor for _, valor in loaded.closes(underlying_symbol)], _VOL_WINDOW
        )
        if isinstance(volatility, str):
            atm = self._atm_implied_vol(quotes, spot, rate.as_continuous(), now.date())
            if atm is None:
                raise UnderlyingUnavailableError(
                    f"{underlying_symbol}: {volatility}; e nenhuma série com compra e venda "
                    "para estimar a vol"
                )
            volatility = atm
        snapshot = MarketSnapshot(
            underlying_symbol=underlying_symbol,
            spot=spot,
            bid=bid,
            ask=ask,
            mid=mid,
            risk_free_rate=rate,
            volatility=volatility,
            timestamp=quote.timestamp,
        )
        return OptionChain(snapshot, quotes, rejected, underlying_book_available=book_available)

    def _atm_implied_vol(
        self, quotes: Sequence[OptionQuote], spot: float, rate: float, today: date
    ) -> Volatility | None:
        base = DayCountConvention.BUSINESS_252
        candidatas: list[tuple[float, date, float]] = []
        for quote in quotes:
            termos = quote.contract.terms
            if quote.bid is None or quote.ask is None or termos.expiry <= today:
                continue
            tau = self._calendar.business_days_between(today, termos.expiry) / base.days_per_year
            sigma = mid_implied_vol(quote, SeriesMarket(spot, rate, tau))
            if sigma is not None:
                candidatas.append((abs(termos.strike - spot), termos.expiry, sigma))
        return Volatility(min(candidatas)[2], base) if candidatas else None

    # --- séries -----------------------------------------------------------------------------------

    def _series(
        self, loaded: LoadedLibrary, underlying: str, spot: float, now: datetime
    ) -> tuple[tuple[OptionQuote, ...], tuple[RejectedSeries, ...]]:
        quotes: list[OptionQuote] = []
        rejected: list[RejectedSeries] = []
        for row in self._selected_rows(loaded, underlying, spot, now.date()):
            if row.style is None:
                rejected.append(RejectedSeries(row.symbol, "sem estilo de exercício no cadastro"))
            elif row.ambiguity is not None:
                rejected.append(RejectedSeries(row.symbol, row.ambiguity))
            else:
                terms = OptionTerms(underlying, row.strike, row.expiry, row.option_type, row.style)
                found = to_option_quote(
                    OptionContract(row.symbol, terms),
                    self._board.values(row.symbol),
                    self._board.is_loaded(row.symbol),
                    now,
                )
                if isinstance(found, OptionQuote):
                    quotes.append(found)
                elif found is not None:  # série rejeitada pela tradução, com motivo
                    rejected.append(found)
        rejected.sort(key=lambda r: r.symbol)
        return tuple(quotes), tuple(rejected)

    def _selected_rows(
        self, loaded: LoadedLibrary, ticker: str, spot: float | None, today: date
    ) -> list[_Row]:
        """Séries dos ``VENCIMENTOS_PADRAO`` próximos vencimentos (>= hoje) dentro da faixa.

        Os vencimentos saem de TODAS as séries candidatas, as de vínculo ambíguo inclusive: o
        vencimento existe para o ativo mesmo quando não se sabe de quem é cada série, e é por
        ele que as ambíguas chegam a ``rejected_series`` (senão a cadeia sairia vazia e muda).
        """
        rows = self._index_of(loaded).rows_of(ticker)
        expiries = sorted({r.expiry for r in rows if r.expiry >= today})
        chosen = set(expiries[:VENCIMENTOS_PADRAO])
        return [r for r in rows if r.expiry in chosen and _in_band(r.strike, spot)]

    def _series_units(
        self, loaded: LoadedLibrary, chain_symbols: Sequence[str]
    ) -> list[tuple[Topic, ...]]:
        """Tópicos de cada série a assinar, das mais perto do spot para as mais longe."""
        now = self._now()
        nearest: dict[str, tuple[float, date]] = {}
        for ticker in chain_symbols:
            spot = self._reference_spot(loaded, ticker, now)
            for row in self._selected_rows(loaded, ticker, spot, now.date()):
                if row.ambiguity is None:  # série de vínculo duvidoso não se assina
                    distance = 0.0 if spot is None else abs(row.strike - spot) / spot
                    nearest.setdefault(row.symbol, (distance, row.expiry))
        ordered = sorted(nearest, key=lambda s: (nearest[s][0], nearest[s][1], s))
        return [tuple((symbol, campo) for campo in CAMPOS_OPCAO) for symbol in ordered]

    def _reference_spot(self, loaded: LoadedLibrary, ticker: str, now: datetime) -> float | None:
        """Último ``ULT`` do Tryd; senão o último fechamento do COTAHIST; senão nenhum."""
        # O rótulo da fonte não sai daqui: só o último preço serve de referência para a faixa.
        quote = self._quote(ticker, DataSource.ATRASADO, now)
        if quote is not None and quote.last is not None:
            return quote.last
        closes = loaded.closes(ticker)
        return closes[-1][1] if closes else None

    def _within_limit(self, units: Sequence[tuple[Topic, ...]]) -> frozenset[Topic]:
        topics: list[Topic] = []
        for unit in units:
            if len(topics) + len(unit) > self._topic_limit:
                break
            topics.extend(unit)
        return frozenset(topics)

    def _index_of(self, loaded: LoadedLibrary) -> _SeriesIndex:
        with self._index_lock:
            if self._index is None or self._index[0] is not loaded:
                self._index = (loaded, _build_index(loaded))
            return self._index[1]

    # --- quadro -----------------------------------------------------------------------------------

    def _quote(self, ticker: str, source: DataSource, now: datetime) -> UnderlyingQuote | None:
        return to_underlying_quote(
            ticker,
            self._board.values(ticker),
            self._board.is_loaded(ticker),
            source,
            now,
            warn=self._warn,
        )

    def _now(self) -> datetime:
        return self._clock.now().astimezone(self._tz)

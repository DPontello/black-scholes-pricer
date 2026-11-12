"""Histórico de IV de 30 dias úteis e HV de 21 por pregão, pelos COTAHIST da biblioteca (spec da
semana 3, §2).

Cada arquivo é lido em fluxo, guardando só a raiz do ativo pedido. A IV de um vencimento é a do
mesmo smile da cadeia de fim de dia (meio do book, séries com os dois lados) no spot; o vínculo e
as rejeições de série são os do adapter COTAHIST. O estilo de exercício não é exigido: ele não
muda a IV (o smile usa a fórmula europeia em todas as séries) e as séries vencidas não estão no
cadastro do dia.

Cache ``vol_history.sqlite`` na raiz da biblioteca, por arquivo (caminho, tamanho e mtime), ativo
e CDI: um diário importado é o único arquivo lido, e trocar o CDI recalcula. Banco ilegível vira
recálculo, e um arquivo que não é sqlite nunca é sobrescrito.
"""

import hashlib
import json
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Final

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.b3files.loaded import NO_COTAHIST_REASON, LibraryLoader
from options_engine.adapters.outbound.cotahist.errors import SourceFileError
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo
from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_CALL,
    MARKET_PUT,
    MARKET_SPOT,
    CotahistRecord,
    iter_cotahist,
)
from options_engine.adapters.outbound.cotahist.series_rules import (
    link_underlying,
    record_rejection,
    series_root,
)
from options_engine.adapters.outbound.cotahist.volatility import realized_volatility
from options_engine.application.ports.outbound import TradingCalendar
from options_engine.domain.analytics.volatility import (
    HORIZON_BUSINESS_DAYS,
    MIN_EXPIRY_BUSINESS_DAYS,
    DailyVol,
    ExpiryVol,
    HorizonVol,
    iv_at_horizon,
)
from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.conventions import Compounding, RiskFreeRate, TimeToExpiry
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import DomainError
from options_engine.domain.pricing.smile import SeriesMarket, build_smile

__all__ = ["VOL_HISTORY_CACHE_NAME", "CotahistVolHistory"]

VOL_HISTORY_CACHE_NAME: Final = "vol_history.sqlite"
_CACHE_FORMAT: Final = 1
_HV_WINDOW: Final = 21
_END_OF_SESSION: Final = time(18, 0)
_OPTION_TYPES: Final = {MARKET_CALL: OptionType.CALL, MARKET_PUT: OptionType.PUT}


@dataclass(frozen=True, slots=True)
class _Session:
    session: date
    close: float
    iv30: float | None
    extrapolated: bool


class CotahistVolHistory:
    """``VolHistoryPort`` sobre a biblioteca; o CDI do perfil vale para todo o histórico."""

    def __init__(
        self, loader: LibraryLoader, calendar: TradingCalendar, cdi_annual: Callable[[], float]
    ) -> None:
        self._loader = loader
        self._calendar = calendar
        self._cdi_annual = cdi_annual
        self._lock = threading.Lock()

    def history(self, symbol: str) -> tuple[DailyVol, ...] | str:
        loaded = self._loader.load()
        if isinstance(loaded, str):
            return loaded
        if not loaded.cotahist_paths:
            return NO_COTAHIST_REASON
        rate = RiskFreeRate(self._cdi_annual(), Compounding.BUSINESS_DAILY_252)
        cache = loaded.cache_path.with_name(VOL_HISTORY_CACHE_NAME)
        sessions: dict[date, _Session] = {}
        try:
            with self._lock:
                for path in loaded.cotahist_paths:
                    for row in self._file_sessions(path, symbol, rate, loaded.instruments, cache):
                        sessions.setdefault(row.session, row)
        except (SourceFileError, OSError) as erro:
            return f"arquivos da B3 ilegíveis: {erro}"
        if not sessions:
            return f"{symbol}: sem fechamento nos COTAHIST da biblioteca"
        return _with_hv([sessions[d] for d in sorted(sessions)])

    def _file_sessions(
        self,
        path: Path,
        symbol: str,
        rate: RiskFreeRate,
        instruments: Mapping[str, InstrumentInfo],
        cache: Path,
    ) -> tuple[_Session, ...]:
        key = _cache_key(path, symbol, rate)
        cached = _read_cache(cache, key)
        if cached is not None:
            return cached
        computed = tuple(self._compute(path, symbol, rate, instruments))
        _write_cache(cache, key, computed)
        return computed

    def _compute(
        self,
        path: Path,
        symbol: str,
        rate: RiskFreeRate,
        instruments: Mapping[str, InstrumentInfo],
    ) -> Iterator[_Session]:
        root = series_root(symbol)
        by_session: dict[date, dict[str, CotahistRecord]] = defaultdict(dict)
        divergent: dict[date, set[str]] = defaultdict(set)
        for record in iter_cotahist(path):
            if series_root(record.symbol) != root:
                continue
            if by_session[record.session].setdefault(record.symbol, record) != record:
                divergent[record.session].add(record.symbol)
        for day in sorted(by_session):
            row = self._session(day, by_session[day], divergent[day], symbol, rate, instruments)
            if row is not None:
                yield row

    def _session(
        self,
        day: date,
        records: Mapping[str, CotahistRecord],
        divergent: set[str],
        symbol: str,
        rate: RiskFreeRate,
        instruments: Mapping[str, InstrumentInfo],
    ) -> _Session | None:
        spots = {s: r for s, r in records.items() if r.market == MARKET_SPOT}
        underlying = spots.get(symbol)
        if underlying is None or underlying.last <= 0.0 or symbol in divergent:
            return None
        series = [
            r
            for s, r in records.items()
            if r.market in _OPTION_TYPES
            and s not in divergent
            and link_underlying(r, spots, instruments) == symbol
            and record_rejection(r, day) is None
        ]
        iv = self._iv30(day, underlying.last, symbol, series, rate)
        return _Session(
            day, underlying.last, None if iv is None else iv.vol, iv is not None and iv.extrapolated
        )

    def _iv30(
        self,
        day: date,
        spot: float,
        symbol: str,
        series: Sequence[CotahistRecord],
        rate: RiskFreeRate,
    ) -> HorizonVol | None:
        by_expiry: dict[date, list[CotahistRecord]] = defaultdict(list)
        for record in series:
            by_expiry[record.expiry].append(record)
        days: dict[date, int] = {}
        for expiry in by_expiry:
            try:
                days[expiry] = self._calendar.business_days_between(day, expiry)
            except DomainError:  # vencimento fora da cobertura do calendário
                continue
        usable = [e for e in days if days[e] >= MIN_EXPIRY_BUSINESS_DAYS]
        before = sorted(
            (e for e in usable if days[e] <= HORIZON_BUSINESS_DAYS), key=days.__getitem__
        )
        after = sorted(
            (e for e in usable if days[e] >= HORIZON_BUSINESS_DAYS), key=days.__getitem__
        )
        # Só o vencimento mais perto do prazo, de cada lado, com vol no spot entra na
        # interpolação: calcular o smile dos outros não mudaria o resultado.
        points: dict[date, ExpiryVol] = {}
        for side in (reversed(before), after):
            for expiry in side:
                vol = _vol_at_spot(day, expiry, days[expiry], spot, symbol, by_expiry[expiry], rate)
                if vol is not None:
                    points[expiry] = ExpiryVol(days[expiry], vol)
                    break
        return iv_at_horizon(tuple(points.values()))


def _vol_at_spot(
    day: date,
    expiry: date,
    business_days: int,
    spot: float,
    symbol: str,
    records: Sequence[CotahistRecord],
    rate: RiskFreeRate,
) -> float | None:
    market = SeriesMarket(
        spot, rate.as_continuous(), TimeToExpiry.from_days(business_days).year_fraction
    )
    instant = datetime.combine(day, _END_OF_SESSION, tzinfo=B3_UTC_OFFSET)
    quotes = [_quote(r, symbol, instant) for r in records if r.best_bid > 0.0 and r.best_ask > 0.0]
    return build_smile(expiry, quotes, market).vol_at(spot)


def _quote(record: CotahistRecord, symbol: str, instant: datetime) -> OptionQuote:
    terms = OptionTerms(
        underlying=symbol,
        strike=record.strike,
        expiry=record.expiry,
        option_type=_OPTION_TYPES[record.market],
        exercise_style=ExerciseStyle.EUROPEAN,
    )
    return OptionQuote(
        contract=OptionContract(symbol=record.symbol, terms=terms),
        bid=record.best_bid,
        ask=record.best_ask,
        last=record.last if record.last > 0.0 else None,
        trades=record.trades,
        volume=record.volume,
        timestamp=instant,
    )


def _with_hv(sessions: Sequence[_Session]) -> tuple[DailyVol, ...]:
    closes = [s.close for s in sessions]
    result = []
    for i, s in enumerate(sessions):
        hv = realized_volatility(closes[: i + 1], _HV_WINDOW)
        result.append(
            DailyVol(
                s.session,
                s.close,
                s.iv30,
                s.extrapolated,
                None if isinstance(hv, str) else hv.value,
            )
        )
    return tuple(result)


def _cache_key(path: Path, symbol: str, rate: RiskFreeRate) -> str:
    status = path.stat()
    raw = json.dumps(
        {
            "formato": _CACHE_FORMAT,
            "arquivo": [str(path.resolve()), status.st_size, status.st_mtime_ns],
            "ativo": symbol,
            "cdi": rate.rate,
        }
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache(cache: Path, key: str) -> tuple[_Session, ...] | None:
    if not cache.exists():
        return None
    try:
        with closing(sqlite3.connect(cache)) as conexao:
            linha = conexao.execute(
                "SELECT payload FROM historicos WHERE chave = ?", (key,)
            ).fetchone()
    except sqlite3.Error:
        return None
    if linha is None:
        return None
    try:
        return tuple(
            _Session(date.fromisoformat(d), float(close), iv, bool(extrapolada))
            for d, close, iv, extrapolada in json.loads(linha[0])
        )
    except (ValueError, TypeError):
        return None


def _write_cache(cache: Path, key: str, sessions: Sequence[_Session]) -> None:
    payload = json.dumps(
        [[s.session.isoformat(), s.close, s.iv30, s.extrapolated] for s in sessions]
    )
    try:
        with closing(sqlite3.connect(cache)) as conexao, conexao:
            conexao.execute(
                "CREATE TABLE IF NOT EXISTS historicos "
                "(chave TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            conexao.execute(
                "INSERT OR REPLACE INTO historicos (chave, payload) VALUES (?, ?)", (key, payload)
            )
    except sqlite3.Error:
        return

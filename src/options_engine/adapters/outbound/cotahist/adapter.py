"""``CotahistOptionChainAdapter`` — o ``OptionChainPort`` de fim de dia da fase 1 (ADR-0006).

Arquivos LOCAIS, baixados manualmente: COTAHIST (diário, mensal ou anual;
vários, mesclados por pregão) e o Cadastro de Instrumentos do mesmo pregão.
Tudo é lido e validado no construtor; a consulta ao port só monta a cadeia
em memória e só levanta erros de domínio.

Ativo-objeto (registro à vista TPMERC 010 do pregão):

- ticker ausente de todo o conjunto de arquivos -> ``UnknownSymbolError``;
- presente, mas sem registro no pregão ou com fechamento zero ->
  ``UnderlyingUnavailableError("sem fechamento no pregão")``;
- spot = fechamento (PREULT). Com as duas ofertas > 0 e coerentes, bid/ask
  são as ofertas e mid a média; senão (decisão da mesa, ADR-0004)
  ``bid = ask = mid = spot`` e a cadeia sai com
  ``underlying_book_available = False``;
- vol realizada: desvio-padrão amostral dos log-retornos fechamento a
  fechamento dos últimos ``realized_vol_window`` retornos até o pregão
  (inclusive), vezes sqrt(252), em BUSINESS_252. Histórico insuficiente ou
  vol zero -> ``UnderlyingUnavailableError`` com o motivo e o mínimo, nunca
  um número inventado. Limitação: o COTAHIST não ajusta fechamentos por
  proventos nem desdobramentos — um evento na janela distorce a vol.

Séries (calls TPMERC 070 e puts 080 do pregão): pertencem ao ativo-objeto
cuja raiz (4 primeiras letras do ticker) é a raiz da série. Com mais de um
ativo-objeto da mesma raiz no pregão (PETR3 e PETR4), desempata a classe da
especificação (primeiro termo do ESPECI: ON, PN, UNT...); quando o cadastro
traz ``UndrlygTckrSymb1``, ele prevalece. Vínculo ambíguo -> rejeitada.
Regra de vínculo e conteúdo do ESPECI das opções: premissas a conferir com
um arquivo real.

Cada série vira ``OptionQuote`` — zero da fonte vira ``None`` em bid, ask e
last (ADR-0003); TOTNEG -> ``trades``; VOLTOT -> ``volume`` financeiro — ou
``RejectedSeries`` com motivo: registros divergentes do ticker no pregão,
ausente do cadastro ou sem estilo de exercício nele (obrigatório pela mesa,
nunca EUROPEAN por omissão), strike corrigido por índice (INDOPC != 0),
vencimento anterior ao pregão, book cruzado na fonte, strike zero.

Timestamps: ``datetime(pregão, 18:00, fuso de valoração)`` — marcador de fim
de pregão; só a data importa.
"""

import itertools
import math
import statistics
from collections.abc import Sequence
from datetime import date, datetime, time, tzinfo
from pathlib import Path

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo, load_instruments
from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_CALL,
    MARKET_PUT,
    MARKET_SPOT,
    CotahistRecord,
)
from options_engine.adapters.outbound.cotahist.session import SessionData, load_session_data
from options_engine.domain.model.chain import OptionChain, OptionQuote, RejectedSeries
from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.conventions import DayCountConvention, RiskFreeRate, Volatility
from options_engine.domain.model.enums import OptionType
from options_engine.domain.model.errors import UnderlyingUnavailableError, UnknownSymbolError
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["CotahistOptionChainAdapter"]

_END_OF_SESSION = time(18, 0)
_ROOT_LENGTH = 4
_OPTION_TYPES = {MARKET_CALL: OptionType.CALL, MARKET_PUT: OptionType.PUT}


def _raiz(simbolo: str) -> str:
    return simbolo[:_ROOT_LENGTH]


def _classe(especificacao: str) -> str:
    """Primeiro termo do ESPECI (``"PN N2"`` -> ``"PN"``); vazio se não houver."""
    termos = especificacao.split()
    return termos[0].upper() if termos else ""


def _ou_none(valor: float) -> float | None:
    """Zero da fonte é lado ausente (ADR-0003), nunca preço."""
    return valor if valor > 0.0 else None


class CotahistOptionChainAdapter:
    """``OptionChainPort`` sobre arquivos COTAHIST e o Cadastro de Instrumentos.

    Construção com DI explícita (nada de ambiente). Arquivo ausente
    (``OSError``) ou fora do layout (``CotahistFormatError``,
    ``InstrumentsFileError``) falham AQUI, na carga.
    """

    def __init__(
        self,
        *,
        session_date: date,
        cotahist_paths: Sequence[Path],
        instruments_path: Path,
        risk_free_rate: RiskFreeRate,
        realized_vol_window: int = 21,
        cache_path: Path | None = None,
        valuation_timezone: tzinfo = B3_UTC_OFFSET,
    ) -> None:
        if realized_vol_window < 2:
            raise ValueError(
                f"realized_vol_window deve ser >= 2 retornos (desvio-padrão amostral); "
                f"recebido {realized_vol_window!r}"
            )
        if not cotahist_paths:
            raise ValueError("ao menos um arquivo COTAHIST é obrigatório")
        self._session = session_date
        self._rate = risk_free_rate
        self._window = realized_vol_window
        self._timestamp = datetime.combine(session_date, _END_OF_SESSION, tzinfo=valuation_timezone)
        self._data, self._from_cache = load_session_data(
            tuple(cotahist_paths), session_date, cache_path
        )
        self._instruments = load_instruments(instruments_path)
        self._spot_records = {r.symbol: r for r in self._data.records if r.market == MARKET_SPOT}

    @property
    def loaded_from_cache(self) -> bool:
        """Se a carga veio do cache sqlite (diagnóstico e testes)."""
        return self._from_cache

    @property
    def session_data(self) -> SessionData:
        return self._data

    # ------------------------------------------------------------------
    # Port
    # ------------------------------------------------------------------

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        if underlying_symbol not in self._data.known_spot_symbols:
            raise UnknownSymbolError(
                f"subjacente desconhecido nos arquivos COTAHIST: {underlying_symbol!r}"
            )
        snapshot, book_observado = self._snapshot(underlying_symbol)
        quotes: list[OptionQuote] = []
        rejeitadas: list[RejectedSeries] = []
        for registro in self._data.records:
            if registro.market not in _OPTION_TYPES:
                continue
            if _raiz(registro.symbol) != _raiz(underlying_symbol):
                continue
            vinculo = self._vinculo(registro)
            if isinstance(vinculo, RejectedSeries):
                # Ambígua entre ativos da raiz: o pedido é um deles (tem registro
                # no pregão, senão _snapshot já teria levantado), e a rejeição
                # aparece na cadeia de cada candidato.
                rejeitadas.append(vinculo)
                continue
            if vinculo != underlying_symbol:
                continue
            serie = self._serie(registro, underlying_symbol)
            if isinstance(serie, RejectedSeries):
                rejeitadas.append(serie)
            else:
                quotes.append(serie)
        quotes.sort(
            key=lambda q: (
                q.contract.terms.expiry,
                q.contract.terms.option_type.value,
                q.contract.terms.strike,
                q.contract.symbol,
            )
        )
        rejeitadas.sort(key=lambda r: r.symbol)
        return OptionChain(
            underlying=snapshot,
            quotes=tuple(quotes),
            rejected_series=tuple(rejeitadas),
            underlying_book_available=book_observado,
        )

    # ------------------------------------------------------------------
    # Ativo-objeto
    # ------------------------------------------------------------------

    def _indisponivel(self, simbolo: str, motivo: str) -> UnderlyingUnavailableError:
        return UnderlyingUnavailableError(f"{simbolo} em {self._session.isoformat()}: {motivo}")

    def _snapshot(self, simbolo: str) -> tuple[MarketSnapshot, bool]:
        if simbolo in self._data.divergent_symbols:
            raise self._indisponivel(simbolo, "registros divergentes do ativo-objeto no pregão")
        registro = self._spot_records.get(simbolo)
        if registro is None or registro.last <= 0.0:
            raise self._indisponivel(simbolo, "sem fechamento no pregão")
        spot = registro.last
        bid, ask = registro.best_bid, registro.best_ask
        book_observado = bid > 0.0 and ask > 0.0 and bid <= ask
        if book_observado:
            mid = (bid + ask) / 2.0
        else:
            bid = ask = mid = spot
        return (
            MarketSnapshot(
                underlying_symbol=simbolo,
                spot=spot,
                bid=bid,
                ask=ask,
                mid=mid,
                risk_free_rate=self._rate,
                volatility=self._vol_realizada(simbolo),
                timestamp=self._timestamp,
            ),
            book_observado,
        )

    def _vol_realizada(self, simbolo: str) -> Volatility:
        fechamentos = [valor for _, valor in self._data.closes.get(simbolo, ())]
        exigidos = self._window + 1
        if len(fechamentos) < exigidos:
            raise self._indisponivel(
                simbolo,
                f"histórico insuficiente para a vol realizada: {len(fechamentos)} fechamentos "
                f"até o pregão, mínimo {exigidos} ({self._window} retornos)",
            )
        janela = fechamentos[-exigidos:]
        retornos = [math.log(b / a) for a, b in itertools.pairwise(janela)]
        desvio = statistics.stdev(retornos)
        if not desvio > 0.0:
            raise self._indisponivel(
                simbolo, f"vol realizada zero nos últimos {self._window} retornos"
            )
        base = DayCountConvention.BUSINESS_252
        return Volatility(desvio * math.sqrt(base.days_per_year), base)

    # ------------------------------------------------------------------
    # Séries
    # ------------------------------------------------------------------

    def _candidatos(self, registro: CotahistRecord) -> list[str]:
        """Ativos-objeto do pregão com a raiz da série, em ordem alfabética."""
        return sorted(s for s in self._spot_records if _raiz(s) == _raiz(registro.symbol))

    def _vinculo(self, registro: CotahistRecord) -> str | RejectedSeries:
        """Ativo-objeto da série: cadastro, raiz única ou classe do ESPECI; senão rejeitada."""
        info = self._instruments.get(registro.symbol)
        if info is not None and info.underlying_symbol is not None:
            return info.underlying_symbol
        candidatos = self._candidatos(registro)
        if len(candidatos) == 1:
            return candidatos[0]
        classe = _classe(registro.specification)
        mesma_classe = [
            c for c in candidatos if _classe(self._spot_records[c].specification) == classe
        ]
        if len(mesma_classe) == 1:
            return mesma_classe[0]
        return RejectedSeries(
            registro.symbol,
            f"vínculo com o ativo-objeto ambíguo: raiz {_raiz(registro.symbol)!r} em "
            f"{candidatos!r} e especificação {registro.specification!r}",
        )

    def _serie(self, registro: CotahistRecord, simbolo: str) -> OptionQuote | RejectedSeries:
        info = self._instruments.get(registro.symbol)
        estilo = info.exercise_style if info is not None else None
        motivo = self._motivo_de_rejeicao(registro, info)
        if motivo is not None or estilo is None:
            return RejectedSeries(registro.symbol, motivo or "sem estilo de exercício")
        termos = OptionTerms(
            underlying=simbolo,
            strike=registro.strike,
            expiry=registro.expiry,
            option_type=_OPTION_TYPES[registro.market],
            exercise_style=estilo,
        )
        return OptionQuote(
            contract=OptionContract(symbol=registro.symbol, terms=termos),
            bid=_ou_none(registro.best_bid),
            ask=_ou_none(registro.best_ask),
            last=_ou_none(registro.last),
            trades=registro.trades,
            volume=registro.volume,
            timestamp=self._timestamp,
        )

    def _motivo_de_rejeicao(
        self, registro: CotahistRecord, info: InstrumentInfo | None
    ) -> str | None:
        if registro.symbol in self._data.divergent_symbols:
            return "registros divergentes do ticker no pregão (CODNEG duplicado)"
        if info is None:
            return "série ausente do cadastro de instrumentos"
        if info.exercise_style is None:
            return "sem estilo de exercício no cadastro (OptnStyle vazio ou desconhecido)"
        if registro.strike_correction != 0:
            return f"strike corrigido por índice (INDOPC={registro.strike_correction})"
        if registro.expiry < self._session:
            return f"vencimento {registro.expiry.isoformat()} anterior ao pregão"
        if (
            registro.best_bid > 0.0
            and registro.best_ask > 0.0
            and registro.best_bid > registro.best_ask
        ):
            return (
                f"book cruzado na fonte: oferta de compra {registro.best_bid} > "
                f"venda {registro.best_ask}"
            )
        if registro.strike <= 0.0:
            return "strike zero na fonte"
        return None

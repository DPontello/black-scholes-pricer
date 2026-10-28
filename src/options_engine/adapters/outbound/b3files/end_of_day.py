"""``EndOfDayMarket`` — cotações e cadeia do último pregão da biblioteca de arquivos da B3.

O mercado sem fonte ao vivo: o último pregão dos COTAHIST e o cadastro mais recente da
``B3FileLibrary``, sempre rotulado ``FIM_DE_DIA``. Recarrega sozinho quando a biblioteca muda
(arquivo novo importado). Implementa o painel de cotações e a cadeia de opções; a assinatura
ao vivo (``watch``) não faz nada, e a saúde é sempre ``FIM_DE_DIA``.

Cotação do ativo (registro à vista do pregão): ``last`` é o fechamento (PREULT); ``bid`` e
``ask`` são as melhores ofertas, ausentes (``None``) quando zeradas (ADR-0003) ou quando o
book veio cruzado na fonte (o mesmo critério do adapter COTAHIST: oferta que não foi
observada não vira lado do book); ``previous_close`` é o fechamento do pregão anterior em que
o ativo negociou. Sem registro, fechamento zero ou registros divergentes no pregão, o motivo
sai no lugar da cotação.

Sem cadastro ou sem COTAHIST na biblioteca (ou arquivo que não abre), cada símbolo recebe o
motivo e a cadeia levanta ``UnderlyingUnavailableError`` com ele: nunca exceção crua.
A cadeia é a do ``CotahistOptionChainAdapter`` sobre esses arquivos, com a taxa pelo CDI do
perfil na hora da consulta.
"""

import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, time, tzinfo

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.b3files.library import B3FileLibrary, ImportedFile
from options_engine.adapters.outbound.b3files.loaded import LibraryLoader, LoadedLibrary
from options_engine.adapters.outbound.cotahist import CotahistOptionChainAdapter
from options_engine.adapters.outbound.cotahist.errors import SourceFileError
from options_engine.adapters.outbound.fixed_rate import FixedRateAdapter
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.errors import UnderlyingUnavailableError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote

__all__ = ["EndOfDayMarket"]

_END_OF_SESSION = time(18, 0)  # o marcador de fim de pregão do adapter COTAHIST


def _ou_none(valor: float) -> float | None:
    """Zero da fonte é lado ausente (ADR-0003), nunca preço."""
    return valor if valor > 0.0 else None


class EndOfDayMarket:
    """``QuoteBoardPort``, ``LiveFeedPort`` e ``OptionChainPort`` sobre os arquivos da B3."""

    def __init__(
        self,
        library: B3FileLibrary,
        cdi_annual: Callable[[], float],
        tz: tzinfo = B3_UTC_OFFSET,
    ) -> None:
        self._loader = LibraryLoader(library)
        self._cdi_annual = cdi_annual
        self._tz = tz
        # O adapter é caro de montar (relê o cadastro): vale para a mesma foto da biblioteca e o
        # mesmo CDI. As consultas dele são só leitura, então a trava cobre apenas a montagem.
        self._lock = threading.Lock()
        self._built: (
            tuple[tuple[tuple[ImportedFile, ...], float], CotahistOptionChainAdapter] | None
        )
        self._built = None

    # --- QuoteBoardPort -------------------------------------------------------------------------

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]:
        loaded = self._loader.load()
        if isinstance(loaded, str):
            return {symbol: loaded for symbol in symbols}
        return {symbol: self._quote(loaded, symbol) for symbol in symbols}

    # --- LiveFeedPort ---------------------------------------------------------------------------

    def watch(self, underlyings: Sequence[str], chain_symbols: Sequence[str]) -> None:
        """Sem fonte ao vivo para assinar."""

    def health(self) -> DataSource:
        return DataSource.FIM_DE_DIA

    # --- OptionChainPort ------------------------------------------------------------------------

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        loaded = self._loader.load()
        if isinstance(loaded, str):
            raise UnderlyingUnavailableError(f"{underlying_symbol}: {loaded}")
        return self._adapter_for(loaded, underlying_symbol).get_chain(underlying_symbol)

    # --- internos -------------------------------------------------------------------------------

    def _adapter_for(self, loaded: LoadedLibrary, symbol: str) -> CotahistOptionChainAdapter:
        cdi = self._cdi_annual()
        key = (loaded.files, cdi)
        with self._lock:
            if self._built is None or self._built[0] != key:
                try:
                    adapter = CotahistOptionChainAdapter(
                        session_date=loaded.session,
                        cotahist_paths=loaded.cotahist_paths,
                        instruments_path=loaded.instruments_path,
                        risk_free_rate=FixedRateAdapter.from_cdi_annual(cdi).current_rate(),
                        cache_path=loaded.cache_path,
                        valuation_timezone=self._tz,
                    )
                except (OSError, SourceFileError) as erro:
                    raise UnderlyingUnavailableError(
                        f"{symbol}: arquivos da B3 ilegíveis: {erro}"
                    ) from erro
                self._built = (key, adapter)
            return self._built[1]

    def _quote(self, loaded: LoadedLibrary, symbol: str) -> UnderlyingQuote | str:
        if not loaded.knows(symbol):
            return "ativo desconhecido"
        pregao = loaded.session.isoformat()
        if symbol in loaded.data.divergent_symbols:
            return f"registros divergentes do ativo no pregão de {pregao}"
        registro = loaded.spot_records.get(symbol)
        if registro is None or not registro.last > 0.0:
            return f"sem fechamento no pregão de {pregao}"
        bid, ask = _ou_none(registro.best_bid), _ou_none(registro.best_ask)
        if bid is not None and ask is not None and not (bid <= ask):
            bid = ask = None  # book cruzado na fonte: oferta não observada, não lado do book
        anteriores = [c for dia, c in loaded.data.closes.get(symbol, ()) if dia < loaded.session]
        return UnderlyingQuote(
            symbol=symbol,
            last=registro.last,
            bid=bid,
            ask=ask,
            previous_close=anteriores[-1] if anteriores else None,
            trades=registro.trades,
            volume=registro.volume,
            timestamp=datetime.combine(loaded.session, _END_OF_SESSION, tzinfo=self._tz),
            source=DataSource.FIM_DE_DIA,
        )

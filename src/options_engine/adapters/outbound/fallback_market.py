"""``FallbackMarket`` — o mercado ao vivo enquanto a ponte do Tryd responde, o fim de dia se cai.

Compõe o ``TrydMarketFeed`` e o ``EndOfDayMarket`` sob os mesmos ports. A escolha é feita a cada
consulta pela saúde da ponte: com ``live.health()`` em ``FIM_DE_DIA`` (ponte desconectada) as
cotações e a cadeia vêm dos arquivos da B3, rotuladas ``FIM_DE_DIA``; senão vêm do ao vivo, com o
rótulo ``AO_VIVO`` ou ``ATRASADO`` da própria ponte. O quadro que sobrou de uma ponte caída nunca
passa por ao vivo, e o app abre mesmo com o Tryd fechado.

Não há mistura por ativo: se o ao vivo ainda espera o dado de um ativo, a resposta é o motivo
dele (``"aguardando dados"``), não a cotação de ontem ao lado das de agora.

``watch`` vai sempre ao ao vivo, mesmo desconectado: a assinatura fica guardada e vale quando a
ponte voltar.
"""

from collections.abc import Mapping, Sequence

from options_engine.adapters.outbound.b3files.end_of_day import EndOfDayMarket
from options_engine.adapters.outbound.tryd.feed import TrydMarketFeed
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote

__all__ = ["FallbackMarket"]


class FallbackMarket:
    """``MarketPort`` que recua para o fim de dia quando a fonte ao vivo está desconectada."""

    def __init__(self, live: TrydMarketFeed, end_of_day: EndOfDayMarket) -> None:
        self._live = live
        self._end_of_day = end_of_day

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]:
        return self._active().get_quotes(symbols)

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        return self._active().get_chain(underlying_symbol)

    def watch(self, underlyings: Sequence[str], chain_symbols: Sequence[str]) -> None:
        self._live.watch(underlyings, chain_symbols)

    def health(self) -> DataSource:
        return self._live.health()

    def _active(self) -> TrydMarketFeed | EndOfDayMarket:
        return self._end_of_day if self._live.health() is DataSource.FIM_DE_DIA else self._live

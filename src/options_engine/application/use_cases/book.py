"""``BookService``: o book das quatro famílias sobre a cadeia de fim de dia (spec da semana 3, §3).

A cadeia é sempre a do fim de dia, mesmo com o Tryd aberto: o limite de tópicos da ponte não
comporta várias cadeias ao vivo. O contexto de vol vem do histórico dos COTAHIST; a posição da
Proteção, das ações compradas da carteira do perfil (``holdings``), senão 100 hipotéticas.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date, tzinfo

from options_engine.application.ports.book import (
    BookEntry,
    BookFamilyView,
    BookOutcome,
    BookView,
    UnderlyingVol,
)
from options_engine.application.ports.inbound import (
    BuilderLegInput,
    BuilderRequest,
    BuilderStockInput,
    RankIncomeCommand,
    RankIncomeOpportunitiesUseCase,
    StrategyBuilderUseCase,
)
from options_engine.application.ports.outbound import (
    OptionChainPort,
    TradingCalendar,
    VolHistoryPort,
)
from options_engine.domain.analytics.volatility import VolContext, end_of_day_context
from options_engine.domain.book.direcionais import (
    DirectionalView,
    cheap_options,
    directional_items,
)
from options_engine.domain.book.model import BookExclusion, BookItem, FamilyResult
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.book.protecao import (
    HYPOTHETICAL_SHARES,
    ProtectedPosition,
    protection_items,
)
from options_engine.domain.book.renda import renda_items
from options_engine.domain.book.volatilidade import volatility_items
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import (
    DomainError,
    UnderlyingUnavailableError,
    UnknownSymbolError,
)
from options_engine.domain.model.quotes import DataSource
from options_engine.domain.model.templates import Family
from options_engine.domain.portfolio.positions import AssetTotal

__all__ = ["BookService"]

_Familia = Callable[[OptionChain, VolContext, BookSettings, Mapping[date, int]], FamilyResult]


class BookService:
    def __init__(
        self,
        end_of_day: OptionChainPort,
        vol_history: VolHistoryPort,
        income: RankIncomeOpportunitiesUseCase,
        holdings: Callable[[], Sequence[AssetTotal]],
        calendar: TradingCalendar,
        valuation_timezone: tzinfo,
        *,
        builder: StrategyBuilderUseCase | None = None,
    ) -> None:
        self._eod = end_of_day
        self._history = vol_history
        self._income = income
        self._holdings = holdings
        self._calendar = calendar
        self._tz = valuation_timezone
        self._builder = builder

    def book(self, settings: BookSettings, underlyings: Sequence[str]) -> BookView:
        chains: dict[str, OptionChain] = {}
        indisponiveis = []
        for simbolo in underlyings:
            try:
                chains[simbolo] = self._eod.get_chain(simbolo)
            except (UnknownSymbolError, UnderlyingUnavailableError) as erro:
                indisponiveis.append(BookExclusion(simbolo, str(erro)))
        contextos = {s: self._context(s) for s in chains}
        posicoes = self._positions()
        partes: dict[Family, list[FamilyResult]] = {f: [] for f in Family}
        if chains:
            partes[Family.RENDA].append(self._renda(settings, chains, contextos))
        for simbolo, chain in chains.items():
            dias = self._expiries(chain)
            contexto = contextos[simbolo]
            por_contexto: tuple[tuple[Family, _Familia], ...] = (
                (Family.VOLATILIDADE, volatility_items),
                (Family.DIRECIONAIS, cheap_options),
            )
            for familia, varrer in por_contexto:
                if isinstance(contexto, str):
                    partes[familia].append(
                        FamilyResult(exclusions=(BookExclusion(simbolo, contexto),))
                    )
                else:
                    partes[familia].append(varrer(chain, contexto, settings, dias))
            posicao = posicoes.get(simbolo) or ProtectedPosition(
                simbolo, HYPOTHETICAL_SHARES, None, hypothetical=True
            )
            partes[Family.PROTECAO].append(protection_items(chain, posicao, settings, dias))
        sessoes = [self._session(chain) for chain in chains.values()]
        return BookView(
            session=max(sessoes) if sessoes else None,
            source=DataSource.FIM_DE_DIA,
            contexts=tuple(
                UnderlyingVol(s, None, c) if isinstance(c, str) else UnderlyingVol(s, c, None)
                for s, c in contextos.items()
            ),
            families={f: self._view(FamilyResult.combine(*p)) for f, p in partes.items()},
            unavailable=tuple(indisponiveis),
        )

    def directional(self, settings: BookSettings, view: DirectionalView) -> BookFamilyView:
        chain = self._eod.get_chain(view.underlying)
        resultado = directional_items(chain, view, settings, self._expiries(chain))
        return self._view(resultado)

    def _renda(
        self,
        settings: BookSettings,
        chains: Mapping[str, OptionChain],
        contextos: Mapping[str, VolContext | str],
    ) -> FamilyResult:
        # Sem os filtros de liquidez: no book eles valem só para o que é EXECUTAVEL (renda.py).
        ranking = self._income.execute(
            RankIncomeCommand(
                tuple(chains),
                delta_min=settings.delta_min,
                delta_max=settings.delta_max,
                expiries=settings.expiries,
            )
        )
        validos = {s: c for s, c in contextos.items() if not isinstance(c, str)}
        return renda_items(ranking, settings, validos)

    def _context(self, symbol: str) -> VolContext | str:
        historico = self._history.history(symbol)
        if isinstance(historico, str):
            return historico
        return end_of_day_context(symbol, historico)

    def _positions(self) -> dict[str, ProtectedPosition]:
        return {
            total.symbol: ProtectedPosition(
                total.symbol, total.quantity, total.average_price, hypothetical=False
            )
            for total in self._holdings()
            if total.side is Side.BUY
        }

    def _session(self, chain: OptionChain) -> date:
        return chain.underlying.timestamp.astimezone(self._tz).date()

    def _expiries(self, chain: OptionChain) -> dict[date, int]:
        pregao = self._session(chain)
        dias = {}
        for vencimento in {q.contract.terms.expiry for q in chain.quotes}:
            if vencimento < pregao:
                continue
            try:
                dias[vencimento] = self._calendar.business_days_between(pregao, vencimento)
            except DomainError:  # vencimento fora da cobertura do calendário
                continue
        return dias

    def _view(self, resultado: FamilyResult) -> BookFamilyView:
        return BookFamilyView(
            items=tuple(self._entry(i, analisar=True) for i in resultado.items),
            references=tuple(self._entry(i, analisar=False) for i in resultado.references),
            exclusions=resultado.exclusions,
        )

    def _entry(self, item: BookItem, *, analisar: bool) -> BookEntry:
        acao = (
            None
            if item.stock is None
            else BuilderStockInput(item.stock.side, item.stock.quantity, item.stock.origin)
        )
        pedido = BuilderRequest(
            underlying=item.underlying,
            legs=tuple(BuilderLegInput(leg.symbol, leg.side, leg.quantity) for leg in item.legs),
            stock=acao,
            template=item.template_key,
        )
        # Referência não é recomendação: só o que é executável ganha resultado.
        return BookEntry(item, pedido, self._outcome(pedido) if analisar else None)

    def _outcome(self, pedido: BuilderRequest) -> BookOutcome | None:
        if self._builder is None:
            return None
        try:
            analise = self._builder.analyze(pedido)
        except DomainError:  # série sem preço, vencimento fora do calendário...
            return None
        no_vencimento = analise.at_expiry
        if no_vencimento is None:
            return None
        perda = no_vencimento.max_loss
        # ``max_loss`` é o pior resultado (negativo na perda); pior caso com lucro vira perda 0,
        # nunca o lucro como perda.
        return BookOutcome(
            no_vencimento.max_gain,
            None if perda is None else max(0.0, -perda),
            no_vencimento.probability_of_profit,
        )

"""``BookService`` sobre a cadeia falsa de fim de dia (PETR4 e VALE3 a 30, vol 30%)."""

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.application.use_cases.book import BookService
from options_engine.application.use_cases.rank_income import RankIncomeOpportunitiesService
from options_engine.domain.analytics.volatility import DailyVol
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.errors import UnderlyingUnavailableError
from options_engine.domain.portfolio.positions import AssetTotal
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from tests.application._mercado_falso import CALENDARIO, PREGAO, MercadoFalso
from tests.book._cadeias import TABELA, cadeia_larga

Historicos = dict[str, tuple[DailyVol, ...] | str]


def cadeia_de(ativo: str, chain: OptionChain) -> OptionChain:
    """A mesma cadeia com outro ativo-objeto (VALE3 a 30, séries VALEK300...)."""
    raiz = ativo[:4]
    return replace(
        chain,
        underlying=replace(chain.underlying, underlying_symbol=ativo),
        quotes=tuple(
            replace(
                q,
                contract=replace(
                    q.contract,
                    symbol=raiz + q.contract.symbol[4:],
                    terms=replace(q.contract.terms, underlying=ativo),
                ),
            )
            for q in chain.quotes
        ),
    )


def historico(iv_hoje: float, hv_hoje: float) -> tuple[DailyVol, ...]:
    """100 pregões com IV de 31% a 40% e o de hoje com ``iv_hoje`` (rank 0 se abaixo de 31%)."""
    inicio = date(2026, 5, 1)
    antes = tuple(
        DailyVol(inicio + timedelta(days=i), 30.0, 0.31 + i / 1000, False, None) for i in range(100)
    )
    return (*antes, DailyVol(PREGAO, 30.0, iv_hoje, False, hv_hoje))


@dataclass
class HistoricosFalsos:
    por_ativo: Historicos = field(default_factory=dict)

    def history(self, symbol: str) -> tuple[DailyVol, ...] | str:
        return self.por_ativo.get(symbol, f"{symbol}: sem histórico")


class MercadoDoBook(MercadoFalso):
    """ITUB4 sem fechamento no COTAHIST."""

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        if underlying_symbol == "ITUB4":
            raise UnderlyingUnavailableError("ITUB4: sem fechamento no COTAHIST")
        return super().get_chain(underlying_symbol)


def mercado_do_book() -> MercadoDoBook:
    base = cadeia_larga()
    return MercadoDoBook(chains={"PETR4": base, "VALE3": cadeia_de("VALE3", base)})


def servico_do_book(
    historicos: Historicos | None = None,
    carteira: Sequence[AssetTotal] = (),
    mercado: MercadoFalso | None = None,
) -> BookService:
    mercado = mercado or mercado_do_book()
    renda = RankIncomeOpportunitiesService(
        chains=mercado,
        calendar=CALENDARIO,
        model=BlackScholesPricingModel(),
        cost_schedules=(TABELA,),
        valuation_timezone=B3_UTC_OFFSET,
    )
    padrao: Historicos = {"PETR4": historico(0.30, 0.40), "VALE3": historico(0.30, 0.40)}
    return BookService(
        mercado,
        HistoricosFalsos(padrao if historicos is None else historicos),
        renda,
        lambda: carteira,
        CALENDARIO,
        B3_UTC_OFFSET,
        (TABELA,),
    )

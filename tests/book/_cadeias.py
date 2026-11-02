"""Cadeias do book: a PETR4 a 30 do mercado falso (vol 30%), com mais strikes."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import date

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.application.ports.inbound import RankIncomeCommand
from options_engine.application.use_cases.rank_income import RankIncomeOpportunitiesService
from options_engine.domain.book.presets import BookPreset, BookSettings
from options_engine.domain.income.ranking import IncomeRanking
from options_engine.domain.model.chain import OptionChain, OptionQuote
from options_engine.domain.model.enums import OptionType
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from tests.application._mercado_falso import CALENDARIO, NOVEMBRO, PREGAO, cadeia, serie
from tests.income._builders import reference_cost_schedule

MODERADO = BookSettings.default(BookPreset.MODERADO)
TABELA = replace(reference_cost_schedule(), valid_from=date(2025, 8, 1))
DEZEMBRO = date(2026, 12, 18)
STRIKES = (26.0, 28.0, 30.0, 32.0, 34.0)


def du(vencimento: date) -> int:
    return CALENDARIO.business_days_between(PREGAO, vencimento)


def series_do_vencimento(
    vencimento: date = NOVEMBRO, strikes: Sequence[float] = STRIKES, **campos: object
) -> list[OptionQuote]:
    letra = {NOVEMBRO: ("K", "W"), DEZEMBRO: ("L", "X")}[vencimento]
    return [
        serie(f"PETR{letra[i]}{int(k * 10)}", k, tipo, vencimento, **campos)  # type: ignore[arg-type]  # justificativa: kwargs de teste
        for k in strikes
        for i, tipo in enumerate((OptionType.CALL, OptionType.PUT))
    ]


def cadeia_larga(*trocas: OptionQuote, sem: Sequence[str] = ()) -> OptionChain:
    """Novembro e dezembro, strikes de 26 a 34; ``trocas`` substituem as séries de mesmo ticker."""
    por_simbolo = {
        q.contract.symbol: q
        for q in (*series_do_vencimento(), *series_do_vencimento(DEZEMBRO), *trocas)
    }
    return cadeia([q for simbolo, q in por_simbolo.items() if simbolo not in sem])


class Cadeias:
    def __init__(self, chains: dict[str, OptionChain]) -> None:
        self.chains = chains

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        return self.chains[underlying_symbol]


def ranking(chain: OptionChain, settings: BookSettings = MODERADO) -> IncomeRanking:
    servico = RankIncomeOpportunitiesService(
        chains=Cadeias({"PETR4": chain}),
        calendar=CALENDARIO,
        model=BlackScholesPricingModel(),
        cost_schedules=(TABELA,),
        valuation_timezone=B3_UTC_OFFSET,
    )
    return servico.execute(
        RankIncomeCommand(
            ("PETR4",),
            delta_min=settings.delta_min,
            delta_max=settings.delta_max,
            expiries=settings.expiries,
        )
    )

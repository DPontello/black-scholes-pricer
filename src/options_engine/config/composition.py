"""Composition root — wiring manual, sem framework de DI (ARCH §1).

Único módulo autorizado a conhecer adapters E application E domínio ao mesmo
tempo: instanciação explícita, dependências visíveis linha a linha. Trocar o
mock por um feed real é trocar UMA linha aqui — nenhum use case, port ou
teste muda (é a tese da Sprint 3).

A instalação default é a do MVP: mock GBM de PETR4, CDI flat, calendário B3
empacotado, valoração no fuso da B3 em base BUSINESS_252.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET, StaticHolidayCalendar
from options_engine.adapters.outbound.clock import SystemClock
from options_engine.adapters.outbound.cost_schedules import StaticCostScheduleTable
from options_engine.adapters.outbound.cotahist import CotahistOptionChainAdapter
from options_engine.adapters.outbound.fixed_rate import FixedRateAdapter
from options_engine.adapters.outbound.mock_orderbook import MockOrderBookAdapter
from options_engine.adapters.outbound.seeded_random import SeededRandomSource
from options_engine.application.ports.inbound import (
    AnalyzeStrategyPayoffUseCase,
    PriceOptionUseCase,
    RankIncomeOpportunitiesUseCase,
    StressTestUseCase,
)
from options_engine.application.ports.outbound import Clock
from options_engine.application.use_cases.analyze_payoff import AnalyzeStrategyPayoffService
from options_engine.application.use_cases.price_option import PriceOptionService
from options_engine.application.use_cases.rank_income import RankIncomeOpportunitiesService
from options_engine.application.use_cases.stress_test import StressTestService
from options_engine.domain.model.conventions import DayCountConvention, Volatility
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel

__all__ = ["Application", "build_application", "build_income_panel"]

# Instalação default do MVP — nomeada aqui para o smoke e os testes citarem
# a mesma fonte, nunca números mágicos espalhados.
DEFAULT_UNDERLYING = "PETR4"
DEFAULT_INITIAL_SPOT = 30.0
DEFAULT_DRIFT = 0.10
DEFAULT_VOLATILITY = 0.25
DEFAULT_CDI_ANNUAL = 0.15
DEFAULT_DAY_COUNT = DayCountConvention.BUSINESS_252


@dataclass(frozen=True, slots=True)
class Application:
    """Os três contratos inbound prontos para uso.

    A borda (CLI hoje, FastAPI na Sprint 4) recebe ESTE objeto e depende
    apenas dos Protocols — nenhum tipo concreto de adapter vaza daqui. Sem
    campo de feed: expor o ``MarketDataPort`` na borda convidaria um
    consumidor a chamá-lo direto, pulando a política de valoração (fuso,
    day count, guarda de vencida) que os use cases existem para aplicar.
    """

    price_option: PriceOptionUseCase
    analyze_payoff: AnalyzeStrategyPayoffUseCase
    stress_test: StressTestUseCase


def build_application(*, seed: int, clock: Clock | None = None) -> Application:
    """Monta a aplicação default do MVP.

    ``seed`` é OBRIGATÓRIA (CONVENTIONS §7): quem monta a aplicação decide o
    fluxo de aleatoriedade — não existe default escondido. ``clock`` aceita
    injeção (``FixedClock`` no smoke e em reprocessamento auditável); default
    é o relógio de produção.
    """
    resolved_clock: Clock = clock if clock is not None else SystemClock()
    market_data = MockOrderBookAdapter(
        underlying_symbol=DEFAULT_UNDERLYING,
        initial_spot=DEFAULT_INITIAL_SPOT,
        drift=DEFAULT_DRIFT,
        volatility=Volatility(DEFAULT_VOLATILITY, DEFAULT_DAY_COUNT),
        risk_free_rate=FixedRateAdapter.from_cdi_annual(DEFAULT_CDI_ANNUAL).current_rate(),
        random_source=SeededRandomSource(seed),
        clock=resolved_clock,
    )
    calendar = StaticHolidayCalendar.from_packaged_data()
    return Application(
        price_option=PriceOptionService(
            model=BlackScholesPricingModel(),
            market_data=market_data,
            clock=resolved_clock,
            calendar=calendar,
            valuation_timezone=B3_UTC_OFFSET,
            day_count=DEFAULT_DAY_COUNT,
        ),
        analyze_payoff=AnalyzeStrategyPayoffService(),
        stress_test=StressTestService(
            market_data=market_data,
            clock=resolved_clock,
            calendar=calendar,
            valuation_timezone=B3_UTC_OFFSET,
            day_count=DEFAULT_DAY_COUNT,
        ),
    )


def build_income_panel(
    *,
    session_date: date,
    cotahist_paths: Sequence[Path],
    instruments_path: Path,
    cdi_annual: float = DEFAULT_CDI_ANNUAL,
    cache_path: Path | None = None,
    realized_vol_window: int = 21,
) -> RankIncomeOpportunitiesUseCase:
    """Monta o Painel de Renda sobre arquivos COTAHIST locais (ADR-0006).

    Mesma disciplina do ``build_application``: wiring manual, linha a linha.
    Os arquivos são lidos AQUI (construtor do adapter): ausente ->
    ``OSError``; fora do layout -> ``SourceFileError``. ``cdi_annual`` é o
    CDI efetivo anual em decimal (0.15 == 15% a.a.).
    """
    chains = CotahistOptionChainAdapter(
        session_date=session_date,
        cotahist_paths=cotahist_paths,
        instruments_path=instruments_path,
        risk_free_rate=FixedRateAdapter.from_cdi_annual(cdi_annual).current_rate(),
        realized_vol_window=realized_vol_window,
        cache_path=cache_path,
        valuation_timezone=B3_UTC_OFFSET,
    )
    return RankIncomeOpportunitiesService(
        chains=chains,
        calendar=StaticHolidayCalendar.from_packaged_data(),
        model=BlackScholesPricingModel(),
        cost_schedules=StaticCostScheduleTable.from_packaged_data().schedules,
        valuation_timezone=B3_UTC_OFFSET,
        day_count=DEFAULT_DAY_COUNT,
    )

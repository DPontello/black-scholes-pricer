"""``PriceOptionService`` — implementação do contrato ``PriceOptionUseCase``.

Orquestração pura (ARCH §4.2): snapshot via port, tau resolvido pelo helper
único de tempo, precificação delegada ao ``PricingModel``. Nenhuma
matemática aqui — quem calcula é o domínio.
"""

from datetime import tzinfo

from options_engine.application.ports.inbound import PriceOptionCommand
from options_engine.application.ports.outbound import Clock, MarketDataPort, TradingCalendar
from options_engine.application.use_cases._time import resolve_time_to_expiry, valuation_date
from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.errors import UnsupportedExerciseStyleError
from options_engine.domain.model.results import PricingResult
from options_engine.domain.pricing.model import PricingModel, PricingRequest, price_one

__all__ = ["PriceOptionService"]


class PriceOptionService:
    """Precifica uma opção com o modelo e os ports injetados.

    ``day_count`` e ``valuation_timezone`` vivem no CONSTRUTOR, não no
    command: são política de valoração da instalação (B3 = BUSINESS_252,
    UTC-3), decididas no composition root — o chamador de borda pede um
    preço, não escolhe convenção a cada request.
    """

    def __init__(
        self,
        model: PricingModel,
        market_data: MarketDataPort,
        clock: Clock,
        calendar: TradingCalendar,
        *,
        valuation_timezone: tzinfo,
        day_count: DayCountConvention = DayCountConvention.BUSINESS_252,
    ) -> None:
        self._model = model
        self._market_data = market_data
        self._clock = clock
        self._calendar = calendar
        self._valuation_timezone = valuation_timezone
        self._day_count = day_count

    def execute(self, command: PriceOptionCommand) -> PricingResult:
        terms = command.terms
        # Falha ANTES de tocar I/O: um estilo não suportado não merece uma
        # ida ao feed de mercado (ARCH §3 — supports() existe para isto).
        # Uma aproximação aceita (ADR-0002) passa e volta marcada no
        # resultado pelo próprio modelo — o service não a reinterpreta.
        if not self._model.supports(terms):
            raise UnsupportedExerciseStyleError(
                f"modelo {self._model.model_id!r} não precifica estes termos "
                f"({terms.option_type.value} com exercício {terms.exercise_style.value!r} — "
                f"decisão nº 2 emendada pela ADR-0002: call americana só como aproximação "
                f"europeia; put americana segue rejeitada)"
            )
        snapshot = self._market_data.get_snapshot(terms.underlying)
        as_of = valuation_date(self._clock, self._valuation_timezone)
        time_to_expiry = resolve_time_to_expiry(
            terms.expiry, as_of, self._calendar, self._day_count
        )
        request = PricingRequest(terms=terms, snapshot=snapshot, time_to_expiry=time_to_expiry)
        return price_one(self._model, request)

"""Modelo Black-Scholes-Merton atrás do contrato ``PricingModel``.

Implementação de referência do MVP: um loop sobre ``bs_outputs`` (kernel).
Vetorizar amanhã é trocar o interior de ``price_many`` — o contrato
batch-first existe exatamente para que essa troca não toque em nenhum use
case, adapter ou teste (ARCH §3).

Sem dividendos no MVP: o ``q`` do kernel permanece no default 0.0 — o seam
existe na assinatura desde a Sprint 1 e entra pelo modelo na Fase 5.
"""

from collections.abc import Sequence

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import ExerciseStyle
from options_engine.domain.model.errors import UnsupportedExerciseStyleError
from options_engine.domain.model.results import Greeks, PricingResult
from options_engine.domain.pricing.model import PricingRequest

__all__ = ["BlackScholesPricingModel"]


class BlackScholesPricingModel:
    """Modelo europeu analítico — ``supports()`` = exercício EUROPEAN.

    ``price_many`` REJEITA requests não suportados com
    ``UnsupportedExerciseStyleError``: o modelo nunca precifica errado em
    silêncio (decisão nº 2). ``supports()`` existe para o chamador falhar
    cedo; a rejeição aqui é defesa em profundidade, no mesmo espírito das
    guardas do kernel.
    """

    @property
    def model_id(self) -> str:
        return "black-scholes-v1"

    def supports(self, terms: OptionTerms) -> bool:
        return terms.exercise_style is ExerciseStyle.EUROPEAN

    def price_many(self, requests: Sequence[PricingRequest]) -> tuple[PricingResult, ...]:
        """Um resultado por request, na mesma ordem — loop puro sobre o kernel."""
        return tuple(self._price_single(request) for request in requests)

    def _price_single(self, request: PricingRequest) -> PricingResult:
        if not self.supports(request.terms):
            raise UnsupportedExerciseStyleError(
                f"{self.model_id} não precifica exercício "
                f"{request.terms.exercise_style.value!r} (decisão nº 2 — americano entra na "
                f"Fase 6 via binomial)"
            )
        out = bs_outputs(
            request.snapshot.spot,
            request.terms.strike,
            request.time_to_expiry.year_fraction,
            request.snapshot.risk_free_rate.as_continuous(),
            request.snapshot.volatility.value,
            is_call=request.terms.option_type.is_call,
        )
        return PricingResult(
            price=out.price,
            greeks=Greeks(
                delta=out.delta,
                gamma=out.gamma,
                theta_per_year=out.theta_per_year,
                vega_per_vol_unit=out.vega_per_vol_unit,
                rho=out.rho,
            ),
            model_id=self.model_id,
            snapshot=request.snapshot,
            time_to_expiry=request.time_to_expiry,
        )

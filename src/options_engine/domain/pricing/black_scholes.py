"""Modelo Black-Scholes-Merton atrás do contrato ``PricingModel``.

Implementação de referência do MVP: um loop sobre ``bs_outputs`` (kernel).
Vetorizar amanhã é trocar o interior de ``price_many`` — o contrato
batch-first existe exatamente para que essa troca não toque em nenhum use
case, adapter ou teste (ARCH §3).

Sem dividendos no MVP: o ``q`` do kernel permanece no default 0.0 — o seam
existe na assinatura desde a Sprint 1 e entra pelo modelo na Fase 5.

Escopo de exercício (decisão nº 2, emendada pela ADR-0002): europeias são
precificadas exatamente; calls americanas de ação são aceitas como
aproximação europeia com ``q = 0`` e ``r >= 0`` e saem MARCADAS no
resultado; puts americanas seguem rejeitadas — o exercício antecipado da put
pode ser ótimo mesmo sem dividendos, e a aproximação europeia não é
defensável para elas. Com taxa contínua negativa o mesmo vale para a call: o
preço europeu cai abaixo do intrínseco ``S - K`` que o exercício imediato
garante, e a call americana com ``r < 0`` também é rejeitada.
"""

from collections.abc import Sequence

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import ExerciseStyle, OptionType, PricingApproximation
from options_engine.domain.model.errors import UnsupportedExerciseStyleError
from options_engine.domain.model.results import Greeks, PricingResult
from options_engine.domain.pricing.model import PricingRequest

__all__ = ["BlackScholesPricingModel"]


def _is_american_call(terms: OptionTerms) -> bool:
    """Termos aceitos pela ADR-0002 como aproximação europeia.

    Fonte única da regra: ``supports()`` e a marca do resultado leem daqui,
    para que aceitar e marcar nunca divirjam. A comparação explícita com
    AMERICAN (em vez de "não europeu") impede que um estilo futuro herde a
    aproximação por omissão.
    """
    return terms.exercise_style is ExerciseStyle.AMERICAN and terms.option_type is OptionType.CALL


class BlackScholesPricingModel:
    """Modelo europeu analítico — ``supports()`` = EUROPEAN ou CALL AMERICAN.

    A call americana usa EXATAMENTE o mesmo cálculo da call europeia
    equivalente (``q = 0``); a única diferença no resultado é a marca
    ``PricingApproximation.AMERICAN_CALL_AS_EUROPEAN`` (ADR-0002), que
    impede a aproximação de viajar como preço exato.

    ``price_many`` REJEITA requests não suportados (put americana) com
    ``UnsupportedExerciseStyleError``: o modelo nunca precifica errado em
    silêncio. ``supports()`` existe para o chamador falhar cedo; a rejeição
    aqui é defesa em profundidade, no mesmo espírito das guardas do kernel.

    A condição ``r >= 0`` da call americana depende do mercado, não dos
    termos: ``supports()`` não a vê, e ``price_many`` rejeita o request com
    taxa contínua negativa com o mesmo erro.
    """

    @property
    def model_id(self) -> str:
        return "black-scholes-v1"

    def supports(self, terms: OptionTerms) -> bool:
        return terms.exercise_style is ExerciseStyle.EUROPEAN or _is_american_call(terms)

    def price_many(self, requests: Sequence[PricingRequest]) -> tuple[PricingResult, ...]:
        """Um resultado por request, na mesma ordem — loop puro sobre o kernel."""
        return tuple(self._price_single(request) for request in requests)

    def _price_single(self, request: PricingRequest) -> PricingResult:
        terms = request.terms
        if not self.supports(terms):
            raise UnsupportedExerciseStyleError(
                f"{self.model_id} não precifica {terms.option_type.value} com exercício "
                f"{terms.exercise_style.value!r} (ADR-0002: só a call americana é aceita, "
                f"como aproximação europeia; put americana entra na Fase 6 via binomial)"
            )
        approximation = (
            PricingApproximation.AMERICAN_CALL_AS_EUROPEAN if _is_american_call(terms) else None
        )
        r = request.snapshot.risk_free_rate.as_continuous()
        if approximation is not None and r < 0.0:
            raise UnsupportedExerciseStyleError(
                f"{self.model_id} não precifica call americana com taxa contínua negativa "
                f"(r={r!r}): com r < 0 o exercício antecipado pode ser ótimo e o preço "
                f"europeu fica abaixo do intrínseco — a aproximação da ADR-0002 exige r >= 0"
            )
        out = bs_outputs(
            request.snapshot.spot,
            terms.strike,
            request.time_to_expiry.year_fraction,
            r,
            request.snapshot.volatility.value,
            is_call=terms.option_type.is_call,
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
            approximation=approximation,
        )

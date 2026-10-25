"""``BlackScholesPricingModel`` — paridade com o kernel, golden e fronteiras.

O modelo é um shim fino sobre ``bs_outputs``: o teste central é a paridade
EXATA com o kernel (mesmo binário, mesmo caminho aritmético — igualdade
permitida pela política do CONVENTIONS §6). O golden do Hull re-verifica a
ponta a ponta VOs → kernel com a tolerância do oráculo (metade da última
casa publicada).
"""

import pytest

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    TimeToExpiry,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import UnsupportedExerciseStyleError
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from options_engine.domain.pricing.model import PricingRequest
from tests._tolerances import ABS_BOOK_2DP, assert_close
from tests.domain._builders import make_snapshot, make_terms

MODEL = BlackScholesPricingModel()


def _request_hull(option_type: OptionType) -> PricingRequest:
    """Hull, Example 15.6: S=42, K=40, r=10% contínua, sigma=20%, T=0.5 ano."""
    return PricingRequest(
        terms=make_terms(strike=40.0, option_type=option_type),
        snapshot=make_snapshot(
            spot=42.0,
            bid=41.95,
            ask=42.05,
            mid=42.0,
            rate=0.10,
            compounding=Compounding.CONTINUOUS,
            vol=0.20,
            vol_base=DayCountConvention.CALENDAR_365,
        ),
        time_to_expiry=TimeToExpiry(0.5, DayCountConvention.CALENDAR_365),
    )


class TestGoldenHull:
    def test_call_hull_15_6(self) -> None:
        resultado = MODEL.price_many([_request_hull(OptionType.CALL)])[0]
        assert_close(resultado.price, 4.76, rel=0.0, abs_=ABS_BOOK_2DP, label="call Hull 15.6")

    def test_put_hull_15_6(self) -> None:
        resultado = MODEL.price_many([_request_hull(OptionType.PUT)])[0]
        assert_close(resultado.price, 0.81, rel=0.0, abs_=ABS_BOOK_2DP, label="put Hull 15.6")


class TestParidadeComKernel:
    """O modelo NÃO refaz matemática: preço e 5 gregas idênticos ao kernel."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    @pytest.mark.parametrize("strike", [20.0, 30.0, 45.0])
    @pytest.mark.parametrize("tau", [0.0, 0.05, 1.5])
    def test_preco_e_gregas_iguais_ao_kernel(
        self, option_type: OptionType, strike: float, tau: float
    ) -> None:
        snapshot = make_snapshot()
        ttx = TimeToExpiry(tau, DayCountConvention.BUSINESS_252)
        request = PricingRequest(
            terms=make_terms(strike=strike, option_type=option_type),
            snapshot=snapshot,
            time_to_expiry=ttx,
        )
        resultado = MODEL.price_many([request])[0]
        esperado = bs_outputs(
            snapshot.spot,
            strike,
            tau,
            snapshot.risk_free_rate.as_continuous(),
            snapshot.volatility.value,
            is_call=option_type.is_call,
        )
        # Igualdade exata permitida: o modelo delega ao kernel sem nenhuma
        # aritmética própria — qualquer divergência é bug de fronteira.
        assert resultado.price == esperado.price
        assert resultado.greeks.delta == esperado.delta
        assert resultado.greeks.gamma == esperado.gamma
        assert resultado.greeks.theta_per_year == esperado.theta_per_year
        assert resultado.greeks.vega_per_vol_unit == esperado.vega_per_vol_unit
        assert resultado.greeks.rho == esperado.rho


class TestContratoBatch:
    def test_lote_preserva_ordem_e_tamanho(self) -> None:
        requests = [
            _request_hull(OptionType.CALL),
            _request_hull(OptionType.PUT),
        ]
        resultados = MODEL.price_many(requests)
        assert len(resultados) == 2
        individuais = [MODEL.price_many([r])[0] for r in requests]
        assert list(resultados) == individuais

    def test_lote_vazio_devolve_vazio(self) -> None:
        assert MODEL.price_many([]) == ()

    def test_resultado_carrega_inputs_e_model_id(self) -> None:
        """Auditoria (ARCH §2.1): todo número é reconstruível a posteriori."""
        request = _request_hull(OptionType.CALL)
        resultado = MODEL.price_many([request])[0]
        assert resultado.model_id == "black-scholes-v1"
        assert resultado.snapshot == request.snapshot
        assert resultado.time_to_expiry == request.time_to_expiry


class TestFronteiras:
    def test_supports_europeu_e_recusa_americano(self) -> None:
        assert MODEL.supports(make_terms(exercise_style=ExerciseStyle.EUROPEAN))
        assert not MODEL.supports(make_terms(exercise_style=ExerciseStyle.AMERICAN))

    def test_americano_no_lote_falha_alto(self) -> None:
        """Decisão nº 2: nunca precificar americano em silêncio."""
        request = PricingRequest(
            terms=make_terms(exercise_style=ExerciseStyle.AMERICAN),
            snapshot=make_snapshot(),
            time_to_expiry=TimeToExpiry(0.5, DayCountConvention.BUSINESS_252),
        )
        with pytest.raises(UnsupportedExerciseStyleError, match="black-scholes-v1"):
            MODEL.price_many([request])

"""``BlackScholesPricingModel`` — paridade com o kernel, golden e fronteiras.

O modelo é um shim fino sobre ``bs_outputs``: o teste central é a paridade
EXATA com o kernel (mesmo binário, mesmo caminho aritmético — igualdade
permitida pela política do CONVENTIONS §6). O golden do Hull re-verifica a
ponta a ponta VOs → kernel com a tolerância do oráculo (metade da última
casa publicada).

Escopo de exercício (ADR-0002, emenda à decisão nº 2): call americana é
aceita como aproximação europeia e sai marcada; put americana segue
rejeitada. O oráculo da call americana é a call europeia equivalente — o
modelo não refaz matemática, então a igualdade é exata em todo campo exceto
a marca.
"""

import math
from dataclasses import replace

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.kernel.black_scholes import bs_outputs
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    TimeToExpiry,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType, PricingApproximation
from options_engine.domain.model.errors import UnsupportedExerciseStyleError
from options_engine.domain.model.results import PricingResult
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from options_engine.domain.pricing.model import PricingRequest
from tests._tolerances import ABS_BOOK_2DP, assert_close
from tests.domain._builders import make_snapshot, make_terms

MODEL = BlackScholesPricingModel()


def _request_hull(
    option_type: OptionType,
    exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN,
) -> PricingRequest:
    """Hull, Example 15.6: S=42, K=40, r=10% contínua, sigma=20%, T=0.5 ano."""
    return PricingRequest(
        terms=make_terms(strike=40.0, option_type=option_type, exercise_style=exercise_style),
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
    """Decisão nº 2 emendada pela ADR-0002: só a put americana fica de fora."""

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_supports_europeia_de_ambos_os_tipos(self, option_type: OptionType) -> None:
        assert MODEL.supports(
            make_terms(option_type=option_type, exercise_style=ExerciseStyle.EUROPEAN)
        )

    def test_supports_call_americana_como_aproximacao(self) -> None:
        assert MODEL.supports(
            make_terms(option_type=OptionType.CALL, exercise_style=ExerciseStyle.AMERICAN)
        )

    def test_supports_recusa_put_americana(self) -> None:
        assert not MODEL.supports(
            make_terms(option_type=OptionType.PUT, exercise_style=ExerciseStyle.AMERICAN)
        )

    def test_put_americana_no_lote_falha_alto(self) -> None:
        """ADR-0002: o exercício antecipado da put pode ser ótimo mesmo sem
        dividendos — nunca precificá-la como europeia em silêncio."""
        request = _request_hull(OptionType.PUT, ExerciseStyle.AMERICAN)
        with pytest.raises(UnsupportedExerciseStyleError, match=r"black-scholes-v1.*ADR-0002"):
            MODEL.price_many([request])

    def test_put_americana_no_meio_do_lote_falha_o_lote_inteiro(self) -> None:
        """Contrato batch: request não suportado é exceção tipada, nunca
        resultado parcial silencioso com os itens válidos do lote."""
        requests = [
            _request_hull(OptionType.CALL),
            _request_hull(OptionType.PUT, ExerciseStyle.AMERICAN),
            _request_hull(OptionType.CALL, ExerciseStyle.AMERICAN),
        ]
        with pytest.raises(UnsupportedExerciseStyleError):
            MODEL.price_many(requests)


def _sem_marca(resultado: PricingResult) -> PricingResult:
    """O resultado sem a marca de aproximação — o que sobra deve ser a europeia."""
    return replace(resultado, approximation=None)


@st.composite
def _pares_de_calls(draw: st.DrawFn) -> tuple[PricingRequest, PricingRequest]:
    """(call europeia, call americana) com termos e mercado idênticos.

    Inclui os ramos fechados do kernel (tau = 0, sigma = 0) e taxa negativa:
    a identidade tem de valer em todo o domínio, não só no miolo da fórmula.
    """
    spot = draw(st.floats(1.0, 500.0))
    strike = spot * math.exp(draw(st.floats(-1.5, 1.5)))
    tau = draw(st.one_of(st.just(0.0), st.floats(1.0 / 252.0, 5.0)))
    vol = draw(st.one_of(st.just(0.0), st.floats(1e-3, 2.0)))
    rate = draw(st.floats(-0.02, 0.30))
    snapshot = make_snapshot(
        spot=spot,
        bid=spot,
        ask=spot,
        mid=spot,
        rate=rate,
        compounding=Compounding.CONTINUOUS,
        vol=vol,
    )
    ttx = TimeToExpiry(tau, DayCountConvention.BUSINESS_252)

    def _request(style: ExerciseStyle) -> PricingRequest:
        terms = make_terms(strike=strike, option_type=OptionType.CALL, exercise_style=style)
        return PricingRequest(terms=terms, snapshot=snapshot, time_to_expiry=ttx)

    return _request(ExerciseStyle.EUROPEAN), _request(ExerciseStyle.AMERICAN)


class TestCallAmericanaComoEuropeia:
    """ADR-0002: call americana = call europeia (q = 0) + marca de aproximação."""

    def test_hull_call_americana_vale_a_europeia_e_sai_marcada(self) -> None:
        europeia, americana = MODEL.price_many(
            [
                _request_hull(OptionType.CALL),
                _request_hull(OptionType.CALL, ExerciseStyle.AMERICAN),
            ]
        )
        assert americana.approximation is PricingApproximation.AMERICAN_CALL_AS_EUROPEAN
        assert_close(americana.price, 4.76, rel=0.0, abs_=ABS_BOOK_2DP, label="call am. Hull 15.6")
        # Igualdade exata permitida: mesmo request a menos do estilo, mesmo
        # caminho aritmético no kernel — qualquer diferença é bug de fronteira.
        assert _sem_marca(americana) == europeia

    @given(par=_pares_de_calls())
    def test_preco_e_gregas_identicos_aos_da_call_europeia(
        self, par: tuple[PricingRequest, PricingRequest]
    ) -> None:
        request_europeia, request_americana = par
        europeia = MODEL.price_many([request_europeia])[0]
        americana = MODEL.price_many([request_americana])[0]
        assert americana.approximation is PricingApproximation.AMERICAN_CALL_AS_EUROPEAN
        # Igualdade exata permitida: o modelo delega ao kernel com os MESMOS
        # floats; o estilo só decide a marca (CONVENTIONS §6).
        assert _sem_marca(americana) == europeia

    @pytest.mark.parametrize("option_type", [OptionType.CALL, OptionType.PUT])
    def test_europeia_sai_sem_marca(self, option_type: OptionType) -> None:
        resultado = MODEL.price_many([_request_hull(option_type)])[0]
        assert resultado.approximation is None

    def test_lote_misto_preserva_ordem_e_marca_por_item(self) -> None:
        requests = [
            _request_hull(OptionType.CALL),
            _request_hull(OptionType.CALL, ExerciseStyle.AMERICAN),
            _request_hull(OptionType.PUT),
        ]
        resultados = MODEL.price_many(requests)
        assert [r.approximation for r in resultados] == [
            None,
            PricingApproximation.AMERICAN_CALL_AS_EUROPEAN,
            None,
        ]
        assert list(resultados) == [MODEL.price_many([r])[0] for r in requests]

"""Invariantes do ``PricingRequest`` e derivação do açúcar escalar.

O VO de request torna irrepresentável o par de "falsos bugs" mais caro do
pricing: snapshot de um subjacente precificando termos de outro, e vol/tau
em bases de anualização distintas (CONVENTIONS §2).
"""

import pytest

from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    MixedAnnualizationBaseError,
)
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from options_engine.domain.pricing.model import PricingModel, PricingRequest, price_one
from tests.domain._builders import make_snapshot, make_terms

TTX_252 = TimeToExpiry(0.5, DayCountConvention.BUSINESS_252)


def make_request(
    terms: OptionTerms | None = None,
    snapshot: MarketSnapshot | None = None,
    time_to_expiry: TimeToExpiry = TTX_252,
) -> PricingRequest:
    return PricingRequest(
        terms=terms if terms is not None else make_terms(),
        snapshot=snapshot if snapshot is not None else make_snapshot(),
        time_to_expiry=time_to_expiry,
    )


class TestPricingRequestInvariantes:
    def test_request_valido_constroi(self) -> None:
        request = make_request()
        assert request.terms.underlying == request.snapshot.underlying_symbol

    def test_subjacente_divergente_e_irrepresentavel(self) -> None:
        with pytest.raises(InvalidDomainValueError, match="subjacente"):
            make_request(
                terms=make_terms(underlying="PETR4"),
                snapshot=make_snapshot(underlying_symbol="VALE3"),
            )

    def test_bases_de_anualizacao_mistas_sao_irrepresentaveis(self) -> None:
        with pytest.raises(MixedAnnualizationBaseError):
            make_request(
                snapshot=make_snapshot(vol_base=DayCountConvention.BUSINESS_252),
                time_to_expiry=TimeToExpiry(0.5, DayCountConvention.CALENDAR_365),
            )

    def test_request_e_imutavel(self) -> None:
        request = make_request()
        with pytest.raises(AttributeError):
            request.terms = make_terms()  # type: ignore[misc]


class TestContratoEstruturais:
    def test_black_scholes_satisfaz_o_protocol_em_runtime(self) -> None:
        assert isinstance(BlackScholesPricingModel(), PricingModel)

    def test_price_one_e_derivado_do_batch(self) -> None:
        model = BlackScholesPricingModel()
        request = make_request()
        escalar = price_one(model, request)
        lote = model.price_many([request])
        assert len(lote) == 1
        # Igualdade exata permitida: mesmo binário, mesmo caminho aritmético
        # (price_one delega a price_many por definição).
        assert escalar == lote[0]

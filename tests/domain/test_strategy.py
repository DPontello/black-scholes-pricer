"""StrategyLeg e agregado Strategy — o anti-inversão-de-P&L estrutural.

A modelagem de sinal/direção é o maior risco do projeto (ROADMAP Sprint 2):
estes testes congelam a defesa de tipo (quantity > 0 + Side) e as
invariantes ratificadas do agregado (decisão nº 6).
"""

from datetime import date

import pytest

from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import (
    EmptyStrategyError,
    InvalidDomainValueError,
    MixedExpiryError,
    MixedUnderlyingError,
)
from options_engine.domain.model.strategy import Strategy
from tests.domain._builders import make_leg, make_terms

# ---------------------------------------------------------------------------
# StrategyLeg
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("quantity", [0, -1, -10])
def test_quantidade_nao_positiva_e_irrepresentavel(quantity: int) -> None:
    """SELL/-10 é a ambiguidade que inverte P&L em silêncio — o tipo a mata."""
    with pytest.raises(InvalidDomainValueError):
        make_leg(quantity=quantity)


def test_exposicao_assinada_deriva_do_side() -> None:
    assert make_leg(side=Side.BUY, quantity=10).signed_quantity == 10
    assert make_leg(side=Side.SELL, quantity=10).signed_quantity == -10


def test_premio_e_opcional_decisao_4() -> None:
    assert make_leg().premium is None
    assert make_leg(premium=1.25).premium == 1.25
    assert make_leg(premium=0.0).premium == 0.0  # deep OTM pode custar ~0


@pytest.mark.parametrize("premium", [-0.01, float("nan"), float("inf")])
def test_premio_ilegal_e_irrepresentavel(premium: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        make_leg(premium=premium)


def test_symbol_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        make_leg(symbol="")


def test_mirrored_inverte_apenas_o_lado() -> None:
    leg = make_leg(side=Side.SELL, quantity=7, premium=2.5)
    espelhada = leg.mirrored()
    assert espelhada.side is Side.BUY
    assert espelhada.signed_quantity == -leg.signed_quantity
    assert (espelhada.symbol, espelhada.terms, espelhada.quantity, espelhada.premium) == (
        leg.symbol,
        leg.terms,
        leg.quantity,
        leg.premium,
    )


# ---------------------------------------------------------------------------
# Strategy — invariantes do agregado (decisão nº 6)
# ---------------------------------------------------------------------------


def test_estrutura_sem_legs_e_irrepresentavel() -> None:
    with pytest.raises(EmptyStrategyError):
        Strategy.create("vazia", [])


def test_opcao_seca_e_estrutura_valida() -> None:
    """O Composite é raso e uniforme: 1 leg é tão estrutura quanto 4."""
    seca = Strategy.create("call seca", [make_leg()])
    assert len(seca.legs) == 1
    assert seca.underlying == "PETR4"


def test_subjacentes_misturados_sao_rejeitados() -> None:
    with pytest.raises(MixedUnderlyingError):
        Strategy.create(
            "cross-asset",
            [
                make_leg(terms=make_terms(underlying="PETR4")),
                make_leg(symbol="VALEA640", terms=make_terms(underlying="VALE3", strike=64.0)),
            ],
        )


def test_vencimentos_misturados_sao_rejeitados() -> None:
    with pytest.raises(MixedExpiryError):
        Strategy.create(
            "calendar",
            [
                make_leg(terms=make_terms(expiry=date(2026, 12, 18))),
                make_leg(symbol="PETRA301", terms=make_terms(expiry=date(2027, 1, 15))),
            ],
        )


def test_nome_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        Strategy.create("", [make_leg()])


def test_create_normaliza_sequencia_para_tupla() -> None:
    estrutura = Strategy.create("dupla", [make_leg(), make_leg(symbol="PETRA310")])
    assert isinstance(estrutura.legs, tuple)


def test_has_premiums_exige_todas_as_legs() -> None:
    """Prêmio parcial não habilita pnl: ou todas as legs têm, ou nenhuma conta."""
    completa = Strategy.create(
        "com prêmio", [make_leg(premium=1.0), make_leg(symbol="PETRA310", premium=2.0)]
    )
    parcial = Strategy.create(
        "prêmio parcial", [make_leg(premium=1.0), make_leg(symbol="PETRA310")]
    )
    assert completa.has_premiums is True
    assert parcial.has_premiums is False


def test_estrutura_espelhada_inverte_todas_as_legs() -> None:
    original = Strategy.create(
        "vendida",
        [make_leg(side=Side.SELL), make_leg(symbol="PETRA310", side=Side.BUY)],
    )
    espelhada = original.mirrored()
    assert [leg.side for leg in espelhada.legs] == [Side.BUY, Side.SELL]
    assert espelhada.underlying == original.underlying
    assert espelhada.expiry == original.expiry

"""``SeededRandomSource`` — determinismo por seed e guardas de entrada."""

import pytest

from options_engine.adapters.outbound.seeded_random import SeededRandomSource
from options_engine.application.ports.outbound import RandomSource
from options_engine.domain.model.errors import InvalidDomainValueError


def test_satisfaz_o_protocol_em_runtime() -> None:
    assert isinstance(SeededRandomSource(seed=1), RandomSource)


def test_mesma_seed_produz_sequencia_bit_a_bit_identica() -> None:
    # Igualdade exata deliberada: o contrato é determinismo bit a bit
    # (CONVENTIONS §7), não igualdade aproximada.
    assert SeededRandomSource(seed=7).gaussians(100) == SeededRandomSource(seed=7).gaussians(100)


def test_seeds_distintas_produzem_sequencias_distintas() -> None:
    assert SeededRandomSource(seed=7).gaussians(100) != SeededRandomSource(seed=8).gaussians(100)


def test_instancias_sao_fluxos_independentes() -> None:
    """Consumir uma fonte não desloca a outra — sem estado compartilhado."""
    a = SeededRandomSource(seed=7)
    b = SeededRandomSource(seed=7)
    a.gaussians(50)
    assert b.gaussians(1) == SeededRandomSource(seed=7).gaussians(1)


def test_gaussians_zero_e_legal_e_vazio() -> None:
    assert SeededRandomSource(seed=1).gaussians(0) == ()


def test_gaussians_negativo_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        SeededRandomSource(seed=1).gaussians(-1)


def test_uniform_respeita_os_extremos() -> None:
    fonte = SeededRandomSource(seed=1)
    for _ in range(100):
        amostra = fonte.uniform(2.0, 3.0)
        assert 2.0 <= amostra <= 3.0


def test_uniform_com_extremos_invertidos_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        SeededRandomSource(seed=1).uniform(3.0, 2.0)


def test_uniform_com_extremo_nao_finito_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        SeededRandomSource(seed=1).uniform(0.0, float("inf"))

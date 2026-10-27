"""Catálogo de exceções do domínio — contrato estrutural.

O mapeamento HTTP da Sprint 4 captura ``DomainError`` na borda e converte
para 422 estruturado; se uma exceção do catálogo deixar de herdar da raiz,
ela atravessa como 500 opaco. Este teste congela esse contrato.
"""

import pytest

from options_engine.domain.model import errors
from options_engine.domain.model.errors import DomainError

# Todas as folhas do catálogo canônico (docs/ARCHITECTURE.md §6).
_CATALOGO: list[type[DomainError]] = [
    errors.InvalidKernelInputError,
    errors.InvalidDomainValueError,
    errors.EmptyStrategyError,
    errors.ExpiredOptionError,
    errors.MixedUnderlyingError,
    errors.MixedExpiryError,
    errors.InvalidStrategyError,
    errors.UnsupportedExerciseStyleError,
    errors.MissingPremiumError,
    errors.MixedAnnualizationBaseError,
    errors.UnknownSymbolError,
    errors.UnderlyingUnavailableError,
]


@pytest.mark.parametrize("exc", _CATALOGO, ids=lambda e: str(e.__name__))
def test_toda_excecao_do_catalogo_deriva_de_domain_error(exc: type[DomainError]) -> None:
    assert issubclass(exc, DomainError)
    assert issubclass(exc, Exception)


@pytest.mark.parametrize("exc", _CATALOGO, ids=lambda e: str(e.__name__))
def test_excecao_nao_e_value_error_nem_key_error(exc: type[DomainError]) -> None:
    """Exceções cruas não atravessam a fronteira do domínio — nem por herança."""
    assert not issubclass(exc, ValueError)
    assert not issubclass(exc, KeyError)


def test_catalogo_completo_esta_exportado() -> None:
    """``__all__`` é o catálogo canônico: nada a mais, nada a menos."""
    exportadas = {nome for nome in errors.__all__ if nome != "DomainError"}
    assert exportadas == {exc.__name__ for exc in _CATALOGO}

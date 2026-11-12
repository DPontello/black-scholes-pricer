"""Profile, ProfileEntry e normalize_ticker — invariantes dos VOs de perfil."""

import math
from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.domain.model.errors import (
    DomainError,
    DuplicateProfileError,
    InvalidDomainValueError,
    NoActiveProfileError,
    ProfileFolderUnavailableError,
    ProfileLockedError,
    UnknownProfileError,
)
from options_engine.domain.model.profile import Profile, ProfileEntry, normalize_ticker


def test_ticker_normalizado_e_lista_sem_repeticao() -> None:
    assert normalize_ticker(" petr4 ") == "PETR4"
    with pytest.raises(InvalidDomainValueError):
        normalize_ticker("PETR 4")
    with pytest.raises(InvalidDomainValueError):
        Profile("Hugo", ("PETR4", "PETR4"), 0.15)
    with pytest.raises(InvalidDomainValueError):
        Profile("Hugo", ("petr4",), 0.15)


@pytest.mark.parametrize("bruto", ["", "   ", "PETR-4", "PETR4.SA", "PÉTR4", "PETR\n4"])
def test_ticker_vazio_ou_nao_alfanumerico_e_rejeitado(bruto: str) -> None:
    with pytest.raises(InvalidDomainValueError, match="ticker"):
        normalize_ticker(bruto)


def test_ticker_invalido_na_watchlist_e_rejeitado() -> None:
    with pytest.raises(InvalidDomainValueError):
        Profile("Hugo", ("PETR4", "VALE 3"), 0.15)
    with pytest.raises(InvalidDomainValueError):
        Profile("Hugo", ("",), 0.15)


def test_perfil_valido_guarda_os_campos() -> None:
    perfil = Profile("Hugo", ("PETR4", "VALE3"), 0.1475)
    assert perfil.name == "Hugo"
    assert perfil.watchlist == ("PETR4", "VALE3")
    assert perfil.cdi_annual == 0.1475
    with pytest.raises(FrozenInstanceError):
        perfil.name = "Outro"  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste


def test_watchlist_vazia_e_legal() -> None:
    assert Profile("Hugo", (), 0.15).watchlist == ()


def test_cdi_fora_da_faixa_e_nome_vazio_sao_rejeitados() -> None:
    for cdi in (-0.01, 1.0, math.nan):
        with pytest.raises(InvalidDomainValueError):
            Profile("Hugo", (), cdi)
    with pytest.raises(InvalidDomainValueError):
        Profile("  ", (), 0.15)


@pytest.mark.parametrize("cdi", [math.inf, -math.inf, 1.5])
def test_cdi_infinito_ou_acima_de_um_e_rejeitado(cdi: float) -> None:
    with pytest.raises(InvalidDomainValueError, match="cdi_annual"):
        Profile("Hugo", (), cdi)


@pytest.mark.parametrize("cdi", [0.0, 0.9999])
def test_cdi_nas_pontas_da_faixa_e_legal(cdi: float) -> None:
    assert Profile("Hugo", (), cdi).cdi_annual == cdi


@pytest.mark.parametrize("nome", ["", " ", " Hugo", "Hugo ", "\tHugo", "x" * 41])
def test_nome_vazio_com_espaco_nas_pontas_ou_longo_e_rejeitado(nome: str) -> None:
    with pytest.raises(InvalidDomainValueError, match="nome"):
        Profile(nome, (), 0.15)


def test_nome_com_exatamente_quarenta_caracteres_e_legal() -> None:
    nome = "x" * 40
    assert Profile(nome, (), 0.15).name == nome


def test_entrada_de_perfil_e_imutavel() -> None:
    entrada = ProfileEntry("Hugo", "/dados/Hugo")
    assert (entrada.name, entrada.folder) == ("Hugo", "/dados/Hugo")
    with pytest.raises(FrozenInstanceError):
        entrada.folder = "/outra"  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste


def test_perfil_travado_guarda_pc_e_horario_e_cita_os_dois() -> None:
    desde = datetime(2026, 10, 28, 14, 5, tzinfo=B3_UTC_OFFSET)
    erro = ProfileLockedError("NOTE-DO-HUGO", desde)
    assert erro.machine == "NOTE-DO-HUGO"
    assert erro.since == desde
    assert "NOTE-DO-HUGO" in str(erro)
    assert "14:05" in str(erro)
    assert "28/10/2026" in str(erro)


@pytest.mark.parametrize(
    "exc",
    [
        ProfileFolderUnavailableError,
        ProfileLockedError,
        DuplicateProfileError,
        UnknownProfileError,
        NoActiveProfileError,
    ],
)
def test_excecoes_de_perfil_sao_domain_error(exc: type[DomainError]) -> None:
    assert issubclass(exc, DomainError)

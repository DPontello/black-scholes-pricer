"""``ProfileService`` — orquestração de perfis com repositório falso e com o JSON real."""

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.storage.profiles import JsonProfileRepository
from options_engine.application.ports.inbound import ProfileUseCase
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.domain.model.errors import (
    DuplicateProfileError,
    InvalidDomainValueError,
    NoActiveProfileError,
    ProfileLockedError,
    UnknownProfileError,
)
from options_engine.domain.model.profile import Profile, ProfileEntry
from tests.application._fakes import FakeProfileRepository

AGORA = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)  # 09:00 em Brasília


def make_service(
    repo: FakeProfileRepository | None = None, machine_name: str = "PC-SALA"
) -> tuple[ProfileService, FakeProfileRepository]:
    repo = repo if repo is not None else FakeProfileRepository()
    return ProfileService(repo, FixedClock(AGORA), machine_name), repo


def make_service_with_profiles(*names: str) -> tuple[ProfileService, FakeProfileRepository]:
    service, repo = make_service()
    for name in names:
        service.create(name, f"/pastas/{name}")
    return service, repo


def test_service_satisfaz_o_protocol_inbound() -> None:
    service, _ = make_service()
    assert isinstance(service, ProfileUseCase)


def test_list_e_create_delegam_ao_repositorio() -> None:
    service, _ = make_service()
    assert service.list() == ()
    criado = service.create("Hugo", "/pastas/hugo")
    assert criado == Profile("Hugo", ("PETR4", "VALE3"), 0.15)
    assert service.list() == (ProfileEntry("Hugo", "/pastas/hugo"),)


def test_create_com_nome_registrado_propaga_duplicado() -> None:
    service, _ = make_service_with_profiles("Hugo")
    with pytest.raises(DuplicateProfileError):
        service.create("Hugo", "/outra")


def test_create_nao_abre_o_perfil_nem_trava() -> None:
    service, repo = make_service_with_profiles("Hugo")
    with pytest.raises(NoActiveProfileError):
        service.active()
    assert repo.acquired == []


def test_open_define_o_perfil_ativo_e_trava_com_o_nome_do_pc() -> None:
    service, repo = make_service_with_profiles("Hugo")
    aberto = service.open("Hugo")
    assert aberto == Profile("Hugo", ("PETR4", "VALE3"), 0.15)
    assert service.active() == aberto
    assert repo.acquired == [("Hugo", "PC-SALA", AGORA, False)]


def test_open_grava_o_instante_da_trava_no_fuso_de_brasilia() -> None:
    service, repo = make_service_with_profiles("Hugo")
    service.open("Hugo")
    _, _, desde, _ = repo.acquired[0]
    assert desde == AGORA  # mesmo instante...
    assert desde.utcoffset() == timedelta(hours=-3)  # ...visto de Brasília
    assert desde.hour == 9


def test_fuso_padrao_da_trava_coincide_com_o_da_b3() -> None:
    # `application` não importa `adapters`: o fuso é replicado e este teste prende a cópia.
    service, repo = make_service_with_profiles("Hugo")
    service.open("Hugo")
    assert repo.acquired[0][2].utcoffset() == B3_UTC_OFFSET.utcoffset(None)


def test_fuso_da_trava_pode_ser_injetado() -> None:
    repo = FakeProfileRepository()
    fuso = timezone(timedelta(hours=1))
    service = ProfileService(repo, FixedClock(AGORA), "PC-SALA", lock_timezone=fuso)
    service.create("Hugo", "/p")
    service.open("Hugo")
    assert repo.acquired[0][2].utcoffset() == timedelta(hours=1)


def test_open_repassa_force() -> None:
    service, repo = make_service_with_profiles("Hugo")
    service.open("Hugo", force=True)
    assert repo.acquired[0][3] is True


def test_open_de_perfil_nao_registrado_nao_trava_nada() -> None:
    service, repo = make_service_with_profiles("Hugo")
    with pytest.raises(UnknownProfileError):
        service.open("Fantasma")
    assert repo.acquired == []
    with pytest.raises(NoActiveProfileError):
        service.active()


def test_open_travado_por_outro_pc_propaga_e_mantem_o_perfil_anterior() -> None:
    service, repo = make_service_with_profiles("Hugo", "Mãe")
    service.open("Hugo")
    repo.lock_error = ProfileLockedError("AURORA", AGORA.astimezone(B3_UTC_OFFSET))
    with pytest.raises(ProfileLockedError) as erro:
        service.open("Mãe")
    assert erro.value.machine == "AURORA"
    assert service.active().name == "Hugo"
    assert repo.released == []


def test_open_travado_cede_com_force() -> None:
    service, repo = make_service_with_profiles("Hugo")
    repo.lock_error = ProfileLockedError("AURORA", AGORA.astimezone(B3_UTC_OFFSET))
    service.open("Hugo", force=True)
    assert service.active().name == "Hugo"


def test_open_de_outro_perfil_solta_a_trava_do_anterior() -> None:
    service, repo = make_service_with_profiles("Hugo", "Mãe")
    service.open("Hugo")
    service.open("Mãe")
    assert service.active().name == "Mãe"
    assert repo.released == [("Hugo", "PC-SALA")]


def test_reabrir_o_mesmo_perfil_nao_solta_a_trava() -> None:
    service, repo = make_service_with_profiles("Hugo")
    service.open("Hugo")
    service.open("Hugo")
    assert repo.released == []
    assert len(repo.acquired) == 2


def test_active_sem_open_levanta_sem_perfil_ativo() -> None:
    service, _ = make_service_with_profiles("Hugo")
    with pytest.raises(NoActiveProfileError):
        service.active()


def test_set_watchlist_normaliza_remove_repetidos_e_grava() -> None:
    service, repo = make_service_with_profiles("Hugo")
    service.open("Hugo")
    novo = service.set_watchlist(["petr4 ", "PETR4", "vale3"])
    assert novo.watchlist == ("PETR4", "VALE3")
    assert novo == Profile("Hugo", ("PETR4", "VALE3"), 0.15)
    assert service.active() == novo
    assert repo.saved == [("Hugo", novo)]


def test_set_watchlist_mantem_a_ordem_da_primeira_ocorrencia() -> None:
    service, _ = make_service_with_profiles("Hugo")
    service.open("Hugo")
    assert service.set_watchlist(["vale3", "bbas3", "VALE3", "petr4", "BBAS3"]).watchlist == (
        "VALE3",
        "BBAS3",
        "PETR4",
    )


def test_set_watchlist_mantem_nome_e_cdi_do_perfil() -> None:
    service, repo = make_service_with_profiles("Hugo")
    repo.profiles["Hugo"] = Profile("Hugo", ("PETR4",), 0.1075)
    service.open("Hugo")
    assert service.set_watchlist(["itub4"]) == Profile("Hugo", ("ITUB4",), 0.1075)


def test_set_watchlist_aceita_lista_vazia() -> None:
    service, _ = make_service_with_profiles("Hugo")
    service.open("Hugo")
    assert service.set_watchlist([]).watchlist == ()


def test_set_watchlist_com_ticker_invalido_nao_grava_nem_muda_o_ativo() -> None:
    service, repo = make_service_with_profiles("Hugo")
    ativo = service.open("Hugo")
    with pytest.raises(InvalidDomainValueError, match="PE-TR4"):
        service.set_watchlist(["vale3", "PE-TR4"])
    assert repo.saved == []
    assert service.active() == ativo


def test_set_watchlist_sem_perfil_aberto_levanta() -> None:
    service, repo = make_service_with_profiles("Hugo")
    with pytest.raises(NoActiveProfileError):
        service.set_watchlist(["PETR4"])
    assert repo.saved == []


def test_close_solta_a_trava_e_limpa_o_perfil_ativo() -> None:
    service, repo = make_service_with_profiles("Hugo")
    service.open("Hugo")
    service.close()
    assert repo.released == [("Hugo", "PC-SALA")]
    with pytest.raises(NoActiveProfileError):
        service.active()


def test_close_sem_perfil_aberto_nao_faz_nada() -> None:
    service, repo = make_service_with_profiles("Hugo")
    service.close()
    service.open("Hugo")
    service.close()
    service.close()
    assert repo.released == [("Hugo", "PC-SALA")]


def test_save_e_close_usam_a_chave_do_open_e_nao_o_nome_dentro_do_perfil() -> None:
    # Repositório que devolve, para "Mãe", um perfil com o nome de outro cadastro.
    service, repo = make_service_with_profiles("Hugo", "Mãe")
    repo.profiles["Mãe"] = Profile("Hugo", ("PETR4",), 0.15)
    service.open("Mãe")
    service.set_watchlist(["itub4"])
    assert [chave for chave, _ in repo.saved] == ["Mãe"]
    service.close()
    assert repo.released == [("Mãe", "PC-SALA")]


def test_troca_de_perfil_solta_a_trava_da_chave_anterior_mesmo_com_nome_igual_no_perfil() -> None:
    service, repo = make_service_with_profiles("Hugo", "Mãe")
    repo.profiles["Mãe"] = Profile("Hugo", ("PETR4",), 0.15)
    service.open("Mãe")
    service.open("Hugo")
    assert repo.released == [("Mãe", "PC-SALA")]


# --- com o repositório JSON real: mensagem da trava em horário de Brasília ---------------------


def test_trava_de_outro_pc_aparece_com_o_horario_de_brasilia(tmp_path: Path) -> None:
    pasta = tmp_path / "nuvem"
    pasta.mkdir()
    config_sala, config_aurora = tmp_path / "sala.json", tmp_path / "aurora.json"
    sala = ProfileService(JsonProfileRepository(config_sala), FixedClock(AGORA), "PC-SALA")
    aurora = ProfileService(
        JsonProfileRepository(config_aurora),
        FixedClock(AGORA + timedelta(minutes=30)),
        "AURORA",
    )
    sala.create("Hugo", str(pasta))
    sala.open("Hugo")
    aurora.create("qualquer", str(pasta))  # adota o perfil que está na pasta
    with pytest.raises(ProfileLockedError, match=r"'PC-SALA' desde 03/11/2026 às 09:00"):
        aurora.open("Hugo")
    aurora.open("Hugo", force=True)
    sala.close()  # a trava já é da AURORA: o PC-SALA não a remove
    assert (pasta / "perfil.lock").exists()
    aurora.close()
    assert not (pasta / "perfil.lock").exists()


def test_arquivo_com_nome_de_outro_perfil_nao_abre_nem_escreve_na_pasta_do_outro(
    tmp_path: Path,
) -> None:
    repo = JsonProfileRepository(tmp_path / "config.json")
    service = ProfileService(repo, FixedClock(AGORA), "PC-SALA")
    pasta_hugo, pasta_mae = tmp_path / "pasta_hugo", tmp_path / "pasta_mae"
    for nome, pasta in (("Hugo", pasta_hugo), ("Mãe", pasta_mae)):
        pasta.mkdir()
        service.create(nome, str(pasta))
    (pasta_mae / "perfil.json").write_text(
        '{"versao": 1, "nome": "Hugo", "ativos": [], "cdi_anual": 0.15}', encoding="utf-8"
    )
    hugo_antes = (pasta_hugo / "perfil.json").read_bytes()
    with pytest.raises(InvalidDomainValueError, match="'Mãe'"):
        service.open("Mãe")
    with pytest.raises(NoActiveProfileError):
        service.set_watchlist(["itub4"])
    service.close()
    assert (pasta_hugo / "perfil.json").read_bytes() == hugo_antes
    assert not (pasta_hugo / "perfil.lock").exists()
    assert not (pasta_mae / "perfil.lock").exists()


@dataclass(slots=True)
class _RepositorioQueSegura(FakeProfileRepository):
    """Segura o ``save`` até ``liberar`` ser acionado, avisando quando entrou nele."""

    entrou: threading.Event = field(default_factory=threading.Event)
    liberar: threading.Event = field(default_factory=threading.Event)

    def save(self, name: str, profile: Profile) -> None:
        self.entrou.set()
        assert self.liberar.wait(5.0), "o teste esqueceu de liberar o save"
        FakeProfileRepository.save(self, name, profile)


def test_leitura_do_perfil_ativo_espera_a_edicao_em_curso_de_outra_thread() -> None:
    repo = _RepositorioQueSegura()
    service, _ = make_service(repo)
    service.create("Hugo", "/pastas/hugo")
    service.open("Hugo")
    editor = threading.Thread(target=service.set_watchlist, args=(["BOVA11"],))
    editor.start()
    assert repo.entrou.wait(5.0)
    lido: list[Profile] = []
    leitor = threading.Thread(target=lambda: lido.append(service.active()))
    leitor.start()
    leitor.join(0.2)
    assert leitor.is_alive(), "a leitura não esperou a edição terminar"
    repo.liberar.set()
    editor.join(5.0)
    leitor.join(5.0)
    assert lido == [Profile("Hugo", ("BOVA11",), 0.15)]

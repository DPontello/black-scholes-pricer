"""``JsonProfileRepository`` — perfis em JSON, pasta escolhida pelo usuário, trava entre PCs."""

import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.storage.profiles import (
    DEFAULT_PROFILE_CDI_ANNUAL,
    JsonProfileRepository,
)
from options_engine.application.ports.outbound import ProfileRepository
from options_engine.config.composition import DEFAULT_CDI_ANNUAL
from options_engine.domain.model.errors import (
    DuplicateProfileError,
    InvalidDomainValueError,
    ProfileFolderUnavailableError,
    ProfileLockedError,
    UnknownProfileError,
)
from options_engine.domain.model.profile import Profile, ProfileEntry

T0 = datetime(2026, 11, 3, 9, 0, tzinfo=B3_UTC_OFFSET)


def make_repo(tmp_path: Path, nome: str = "Hugo") -> tuple[JsonProfileRepository, Path]:
    """Repositório com um perfil criado numa pasta própria."""
    pasta = tmp_path / "pasta_perfil"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json")
    repo.create(nome, str(pasta))
    return repo, pasta


def test_satisfaz_o_protocol_do_port(tmp_path: Path) -> None:
    assert isinstance(JsonProfileRepository(tmp_path / "config.json"), ProfileRepository)


def test_cdi_padrao_do_adapter_e_o_mesmo_da_composicao() -> None:
    # `adapters` não importa `config`: o valor é replicado e este teste prende a cópia.
    assert DEFAULT_PROFILE_CDI_ANNUAL == DEFAULT_CDI_ANNUAL


# --- criação, leitura e formato dos arquivos --------------------------------------------------


def test_cria_e_relê_o_perfil_na_pasta_escolhida(tmp_path: Path) -> None:
    pasta = tmp_path / "drive_hugo"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json")
    criado = repo.create("Hugo", str(pasta))
    assert criado == Profile("Hugo", ("PETR4", "VALE3"), 0.15)
    assert JsonProfileRepository(tmp_path / "config.json").load("Hugo") == criado
    assert not list(pasta.glob("*.tmp"))


def test_formato_dos_arquivos_em_disco(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path, "Mãe")
    assert json.loads((pasta / "perfil.json").read_text(encoding="utf-8")) == {
        "versao": 1,
        "nome": "Mãe",
        "ativos": ["PETR4", "VALE3"],
        "cdi_anual": 0.15,
    }
    assert json.loads((tmp_path / "config.json").read_text(encoding="utf-8")) == {
        "versao": 1,
        "perfis": [{"nome": "Mãe", "pasta": str(pasta)}],
    }
    assert repo.list_profiles() == (ProfileEntry("Mãe", str(pasta)),)


def test_cdi_padrao_na_criacao_vem_do_construtor(tmp_path: Path) -> None:
    pasta = tmp_path / "p"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json", default_cdi_annual=0.1075)
    assert repo.create("Hugo", str(pasta)).cdi_annual == 0.1075


def test_sem_configuracao_nao_ha_perfis(tmp_path: Path) -> None:
    assert JsonProfileRepository(tmp_path / "config.json").list_profiles() == ()


def test_lista_os_perfis_na_ordem_de_criacao(tmp_path: Path) -> None:
    repo = JsonProfileRepository(tmp_path / "config.json")
    for nome in ("Hugo", "Mãe"):
        pasta = tmp_path / nome
        pasta.mkdir()
        repo.create(nome, str(pasta))
    assert [entrada.name for entrada in repo.list_profiles()] == ["Hugo", "Mãe"]


def test_cria_a_pasta_da_configuracao_se_ela_nao_existe(tmp_path: Path) -> None:
    pasta = tmp_path / "p"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config" / "painel-opcoes" / "config.json")
    repo.create("Hugo", str(pasta))
    assert repo.list_profiles() == (ProfileEntry("Hugo", str(pasta)),)


def test_nome_do_perfil_nao_vira_nome_de_arquivo_nem_pasta(tmp_path: Path) -> None:
    pasta = tmp_path / "escolhida"
    pasta.mkdir()
    JsonProfileRepository(tmp_path / "config.json").create("../Hugo: *?", str(pasta))
    assert sorted(p.name for p in pasta.iterdir()) == ["perfil.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["config.json", "escolhida"]


def test_nome_invalido_nao_grava_nada(tmp_path: Path) -> None:
    pasta = tmp_path / "p"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json")
    with pytest.raises(InvalidDomainValueError, match="nome do perfil"):
        repo.create(" Hugo ", str(pasta))
    assert not list(pasta.iterdir())
    assert repo.list_profiles() == ()


def test_nome_ja_registrado_e_duplicado_e_nao_mexe_em_nada(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    outra = tmp_path / "outra"
    outra.mkdir()
    with pytest.raises(DuplicateProfileError, match="Hugo"):
        repo.create("Hugo", str(outra))
    assert not list(outra.iterdir())
    assert repo.list_profiles() == (ProfileEntry("Hugo", str(pasta)),)


def test_adotar_perfil_com_nome_ja_registrado_e_duplicado(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path, "Mãe")
    outra = tmp_path / "outra"
    outra.mkdir()
    JsonProfileRepository(tmp_path / "pc2.json").create("Mãe", str(outra))
    with pytest.raises(DuplicateProfileError, match="Mãe"):
        repo.create("qualquer", str(outra))
    assert [entrada.name for entrada in repo.list_profiles()] == ["Mãe"]


# --- pasta indisponível -----------------------------------------------------------------------


def test_pasta_indisponivel_nao_cria_nada_nem_muda_a_configuracao(tmp_path: Path) -> None:
    repo = JsonProfileRepository(tmp_path / "config.json")
    with pytest.raises(ProfileFolderUnavailableError, match="nuvem_desmontada"):
        repo.create("Mãe", str(tmp_path / "nuvem_desmontada"))
    assert not (tmp_path / "nuvem_desmontada").exists()
    assert repo.list_profiles() == ()


def test_pasta_que_e_um_arquivo_e_indisponivel(tmp_path: Path) -> None:
    arquivo = tmp_path / "nao_e_pasta"
    arquivo.write_text("x", encoding="utf-8")
    with pytest.raises(ProfileFolderUnavailableError, match="nao_e_pasta"):
        JsonProfileRepository(tmp_path / "config.json").create("Hugo", str(arquivo))


def test_pasta_some_depois_do_cadastro_e_load_save_e_trava_acusam_com_o_caminho(
    tmp_path: Path,
) -> None:
    repo, pasta = make_repo(tmp_path)
    perfil = repo.load("Hugo")
    shutil.rmtree(pasta)
    with pytest.raises(ProfileFolderUnavailableError, match="pasta_perfil"):
        repo.load("Hugo")
    with pytest.raises(ProfileFolderUnavailableError, match="pasta_perfil"):
        repo.save("Hugo", perfil)
    with pytest.raises(ProfileFolderUnavailableError, match="pasta_perfil"):
        repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    assert not pasta.exists()  # nada foi recriado no lugar


def test_soltar_a_trava_com_a_pasta_fora_do_ar_nao_levanta(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    shutil.rmtree(pasta)
    repo.release_lock("Hugo", "PC-SALA")  # nuvem caiu com o app aberto: fechar tem que funcionar


def test_pasta_vazia_sem_perfil_json_e_indisponivel_e_nao_recria(tmp_path: Path) -> None:
    # Ponto de montagem da nuvem que existe mas ainda não sincronizou.
    repo, pasta = make_repo(tmp_path)
    (pasta / "perfil.json").unlink()
    with pytest.raises(ProfileFolderUnavailableError, match=r"perfil\.json"):
        repo.load("Hugo")
    assert not list(pasta.iterdir())


# --- adoção -----------------------------------------------------------------------------------


def test_adota_perfil_existente_na_pasta(tmp_path: Path) -> None:
    pasta = tmp_path / "onedrive_mae"
    pasta.mkdir()
    JsonProfileRepository(tmp_path / "pc1.json").create("Mãe", str(pasta))
    adotado = JsonProfileRepository(tmp_path / "pc2.json").create("qualquer", str(pasta))
    assert adotado.name == "Mãe"


def test_adocao_preserva_o_conteudo_e_registra_o_nome_do_arquivo(tmp_path: Path) -> None:
    repo1, pasta = make_repo(tmp_path, "Mãe")
    repo1.save("Mãe", Profile("Mãe", ("ITUB4",), 0.1075))
    repo2 = JsonProfileRepository(tmp_path / "pc2.json")
    adotado = repo2.create("qualquer", str(pasta))
    assert adotado == Profile("Mãe", ("ITUB4",), 0.1075)
    assert repo2.list_profiles() == (ProfileEntry("Mãe", str(pasta)),)
    assert repo2.load("Mãe") == adotado


# --- save -------------------------------------------------------------------------------------


def test_save_grava_e_load_relê(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    novo = Profile("Hugo", ("BBAS3", "PETR4"), 0.1)
    repo.save("Hugo", novo)
    assert repo.load("Hugo") == novo
    assert json.loads((pasta / "perfil.json").read_text(encoding="utf-8"))["ativos"] == [
        "BBAS3",
        "PETR4",
    ]
    assert not list(pasta.glob("*.tmp"))


def test_save_com_nome_diferente_do_registrado_e_recusado(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    with pytest.raises(InvalidDomainValueError, match="Outro"):
        repo.save("Hugo", Profile("Outro", (), 0.15))
    assert repo.load("Hugo").name == "Hugo"


def test_nome_nao_registrado_e_desconhecido(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    with pytest.raises(UnknownProfileError, match="Fantasma"):
        repo.load("Fantasma")
    with pytest.raises(UnknownProfileError, match="Fantasma"):
        repo.save("Fantasma", Profile("Fantasma", (), 0.15))
    with pytest.raises(UnknownProfileError, match="Fantasma"):
        repo.acquire_lock("Fantasma", "PC-SALA", T0, force=False)
    with pytest.raises(UnknownProfileError, match="Fantasma"):
        repo.release_lock("Fantasma", "PC-SALA")


# --- arquivos ilegíveis -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("conteudo", "motivo"),
    [
        ("{não é json", "JSON"),
        ("[1, 2]", "objeto"),
        ('{"versao": 2, "nome": "Hugo", "ativos": [], "cdi_anual": 0.15}', "versão"),
        ('{"versao": 1, "ativos": [], "cdi_anual": 0.15}', "nome"),
        ('{"versao": 1, "nome": "Hugo", "ativos": "PETR4", "cdi_anual": 0.15}', "ativos"),
        ('{"versao": 1, "nome": "Hugo", "ativos": [], "cdi_anual": "15%"}', "cdi_anual"),
        ('{"versao": 1, "nome": "Hugo", "ativos": [], "cdi_anual": true}', "cdi_anual"),
        ('{"versao": 1, "nome": "Hugo", "ativos": [], "cdi_anual": 1.5}', "fração anual"),
        ('{"versao": 1, "nome": "Hugo", "ativos": ["PE-TR4"], "cdi_anual": 0.15}', "ticker"),
        ('{"versao": 1, "nome": "Hugo", "ativos": ["A", "A"], "cdi_anual": 0.15}', "repete"),
    ],
)
def test_perfil_json_ilegivel_acusa_com_o_caminho_no_load_e_na_adocao(
    tmp_path: Path, conteudo: str, motivo: str
) -> None:
    repo, pasta = make_repo(tmp_path)
    (pasta / "perfil.json").write_text(conteudo, encoding="utf-8")
    padrao = f"{re.escape(str(pasta / 'perfil.json'))}.*{motivo}"
    with pytest.raises(InvalidDomainValueError, match=padrao):
        repo.load("Hugo")
    with pytest.raises(InvalidDomainValueError, match=padrao):
        JsonProfileRepository(tmp_path / "pc2.json").create("Hugo", str(pasta))


def test_tickers_do_arquivo_editado_a_mao_sao_normalizados_na_leitura(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    (pasta / "perfil.json").write_text(
        '{"versao": 1, "nome": "Hugo", "ativos": [" petr4", "vale3"], "cdi_anual": 0}',
        encoding="utf-8",
    )
    assert repo.load("Hugo") == Profile("Hugo", ("PETR4", "VALE3"), 0.0)


@pytest.mark.parametrize(
    "conteudo",
    [
        "{não é json",
        '{"versao": 9, "perfis": []}',
        '{"versao": 1, "perfis": "x"}',
        '{"versao": 1, "perfis": [{"nome": "Hugo"}]}',
    ],
)
def test_configuracao_ilegivel_acusa_com_o_caminho(tmp_path: Path, conteudo: str) -> None:
    config = tmp_path / "config.json"
    config.write_text(conteudo, encoding="utf-8")
    with pytest.raises(InvalidDomainValueError, match=r"config\.json"):
        JsonProfileRepository(config).list_profiles()


# --- trava ------------------------------------------------------------------------------------


def test_trava_de_outro_pc_bloqueia_expira_em_12h_e_cede_ao_forcar(tmp_path: Path) -> None:
    pasta = tmp_path / "p"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json")
    repo.create("Hugo", str(pasta))
    t0 = datetime(2026, 11, 3, 9, 0, tzinfo=B3_UTC_OFFSET)
    repo.acquire_lock("Hugo", "PC-SALA", t0, force=False)
    with pytest.raises(ProfileLockedError) as erro:
        repo.acquire_lock("Hugo", "AURORA", t0 + timedelta(hours=1), force=False)
    assert (erro.value.machine, erro.value.since) == ("PC-SALA", t0)
    repo.acquire_lock("Hugo", "AURORA", t0 + timedelta(hours=1), force=True)
    repo.release_lock("Hugo", "PC-SALA")  # trava de outro PC: não remove
    assert (pasta / "perfil.lock").exists()
    repo.release_lock("Hugo", "AURORA")
    assert not (pasta / "perfil.lock").exists()
    repo.acquire_lock("Hugo", "PC-SALA", t0, force=False)
    repo.acquire_lock("Hugo", "AURORA", t0 + timedelta(hours=13), force=False)  # velha: ignorada


def test_formato_da_trava_em_disco_guarda_pc_e_instante_com_fuso(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    assert json.loads((pasta / "perfil.lock").read_text(encoding="utf-8")) == {
        "pc": "PC-SALA",
        "desde": "2026-11-03T09:00:00-03:00",
    }
    assert not list(pasta.glob("*.tmp"))


def test_mensagem_da_trava_mostra_a_hora_do_fuso_em_que_foi_gravada(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    with pytest.raises(ProfileLockedError, match=r"03/11/2026 às 09:00"):
        repo.acquire_lock("Hugo", "AURORA", T0 + timedelta(minutes=5), force=False)


def test_trava_do_proprio_pc_e_renovada_sem_erro(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    repo.acquire_lock("Hugo", "PC-SALA", T0 + timedelta(hours=1), force=False)
    assert json.loads((pasta / "perfil.lock").read_text(encoding="utf-8"))["desde"] == (
        "2026-11-03T10:00:00-03:00"
    )


def test_trava_vale_ate_12h_e_so_expira_depois(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    with pytest.raises(ProfileLockedError):
        repo.acquire_lock("Hugo", "AURORA", T0 + timedelta(hours=12), force=False)
    repo.acquire_lock("Hugo", "AURORA", T0 + timedelta(hours=12, seconds=1), force=False)


def test_trava_em_outro_fuso_compara_pelo_instante(tmp_path: Path) -> None:
    repo, _ = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)  # 12:00 UTC
    with pytest.raises(ProfileLockedError) as erro:
        repo.acquire_lock("Hugo", "AURORA", datetime(2026, 11, 3, 13, 0, tzinfo=UTC), force=False)
    assert erro.value.since == T0


@pytest.mark.parametrize(
    "conteudo",
    [
        "{não é json",
        "[1]",
        '{"pc": "PC-SALA"}',
        '{"pc": 7, "desde": "2026-11-03T09:00:00-03:00"}',
        '{"pc": "PC-SALA", "desde": "ontem"}',
        '{"pc": "PC-SALA", "desde": "2026-11-03T09:00:00"}',
    ],
)
def test_trava_ilegivel_e_ignorada_e_sobrescrita(tmp_path: Path, conteudo: str) -> None:
    # Sem o nome do PC e o horário não há o que mostrar ao usuário: a trava não vale.
    repo, pasta = make_repo(tmp_path)
    (pasta / "perfil.lock").write_text(conteudo, encoding="utf-8")
    repo.acquire_lock("Hugo", "AURORA", T0, force=False)
    assert json.loads((pasta / "perfil.lock").read_text(encoding="utf-8"))["pc"] == "AURORA"


def test_instante_sem_fuso_na_trava_e_recusado(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    with pytest.raises(InvalidDomainValueError, match="fuso"):
        repo.acquire_lock("Hugo", "PC-SALA", datetime(2026, 11, 3, 9, 0), force=False)
    assert not (pasta / "perfil.lock").exists()


def test_soltar_trava_inexistente_ou_ilegivel_nao_levanta_nem_apaga(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    repo.release_lock("Hugo", "PC-SALA")
    (pasta / "perfil.lock").write_text("{não é json", encoding="utf-8")
    repo.release_lock("Hugo", "PC-SALA")
    assert (pasta / "perfil.lock").exists()


# --- chave do cadastro x nome do arquivo ------------------------------------------------------


def make_dois_perfis(tmp_path: Path) -> tuple[JsonProfileRepository, Path, Path]:
    repo = JsonProfileRepository(tmp_path / "config.json")
    pasta_hugo, pasta_mae = tmp_path / "pasta_hugo", tmp_path / "pasta_mae"
    for nome, pasta in (("Hugo", pasta_hugo), ("Mãe", pasta_mae)):
        pasta.mkdir()
        repo.create(nome, str(pasta))
    return repo, pasta_hugo, pasta_mae


def test_load_recusa_arquivo_com_nome_diferente_do_cadastro(tmp_path: Path) -> None:
    # perfil.json da Mãe editado à mão (ou pasta trocada) com o nome do Hugo.
    repo, pasta_hugo, pasta_mae = make_dois_perfis(tmp_path)
    (pasta_mae / "perfil.json").write_text(
        '{"versao": 1, "nome": "Hugo", "ativos": [], "cdi_anual": 0.15}', encoding="utf-8"
    )
    hugo_antes = (pasta_hugo / "perfil.json").read_bytes()
    with pytest.raises(InvalidDomainValueError) as erro:
        repo.load("Mãe")
    mensagem = str(erro.value)
    assert str(pasta_mae / "perfil.json") in mensagem
    assert "'Hugo'" in mensagem
    assert "'Mãe'" in mensagem
    assert repo.load("Hugo").name == "Hugo"
    assert (pasta_hugo / "perfil.json").read_bytes() == hugo_antes


# --- erros do sistema operacional nos arquivos do perfil --------------------------------------

_MODULO_JSON = "options_engine.adapters.outbound.storage.json_files"


def quebrar_replace(m: pytest.MonkeyPatch, erro: OSError) -> None:
    def replace(*_args: object, **_kwargs: object) -> NoReturn:
        raise erro

    m.setattr(f"{_MODULO_JSON}.os.replace", replace)


def quebrar_metodo_de_path(m: pytest.MonkeyPatch, metodo: str, nome_do_arquivo: str) -> None:
    """Faz ``Path.<metodo>`` levantar ``PermissionError`` só para o arquivo de nome dado."""
    original = getattr(Path, metodo)

    def quebrado(self: Path, *args: Any, **kwargs: Any) -> Any:
        if self.name == nome_do_arquivo:
            raise PermissionError("arquivo em uso pela nuvem")
        return original(self, *args, **kwargs)

    m.setattr(Path, metodo, quebrado)


_ERROS_DE_GRAVACAO = pytest.mark.parametrize(
    "erro",
    [PermissionError("arquivo em uso pela nuvem"), FileNotFoundError("a pasta sumiu")],
    ids=["permissao", "pasta_sumiu"],
)


@_ERROS_DE_GRAVACAO
def test_erro_de_so_ao_gravar_o_perfil_vira_pasta_indisponivel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erro: OSError
) -> None:
    repo, pasta = make_repo(tmp_path)
    antes = (pasta / "perfil.json").read_bytes()
    with monkeypatch.context() as m:
        quebrar_replace(m, erro)
        with pytest.raises(ProfileFolderUnavailableError, match=r"perfil\.json"):
            repo.save("Hugo", Profile("Hugo", ("ITUB4",), 0.15))
    assert (pasta / "perfil.json").read_bytes() == antes
    assert not list(pasta.glob("*.tmp"))


@_ERROS_DE_GRAVACAO
def test_erro_de_so_ao_gravar_a_trava_vira_pasta_indisponivel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erro: OSError
) -> None:
    repo, pasta = make_repo(tmp_path)
    with monkeypatch.context() as m:
        quebrar_replace(m, erro)
        with pytest.raises(ProfileFolderUnavailableError, match=r"perfil\.lock"):
            repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    assert not (pasta / "perfil.lock").exists()
    assert not list(pasta.glob("*.tmp"))


@_ERROS_DE_GRAVACAO
def test_erro_de_so_ao_criar_nao_muda_a_configuracao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, erro: OSError
) -> None:
    pasta = tmp_path / "p"
    pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json")
    with monkeypatch.context() as m:
        quebrar_replace(m, erro)
        with pytest.raises(ProfileFolderUnavailableError, match=r"perfil\.json"):
            repo.create("Hugo", str(pasta))
    assert repo.list_profiles() == ()
    assert not list(pasta.iterdir())


def test_perfil_json_que_e_diretorio_vira_pasta_indisponivel(tmp_path: Path) -> None:
    repo, pasta = make_repo(tmp_path)
    (pasta / "perfil.json").unlink()
    (pasta / "perfil.json").mkdir()
    padrao = r"perfil\.json"
    with pytest.raises(ProfileFolderUnavailableError, match=padrao):
        repo.load("Hugo")
    with pytest.raises(ProfileFolderUnavailableError, match=padrao):
        repo.save("Hugo", Profile("Hugo", (), 0.15))
    with pytest.raises(ProfileFolderUnavailableError, match=padrao):
        JsonProfileRepository(tmp_path / "pc2.json").create("Hugo", str(pasta))
    assert not list(pasta.glob("*.tmp"))


def test_perfil_lock_que_e_diretorio_vira_pasta_indisponivel_e_soltar_nao_levanta(
    tmp_path: Path,
) -> None:
    repo, pasta = make_repo(tmp_path)
    (pasta / "perfil.lock").mkdir()
    with pytest.raises(ProfileFolderUnavailableError, match=r"perfil\.lock"):
        repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    repo.release_lock("Hugo", "PC-SALA")


def test_erro_de_permissao_ao_ler_a_trava_acusa_ao_travar_e_nao_levanta_ao_soltar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _ = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    with monkeypatch.context() as m:
        quebrar_metodo_de_path(m, "read_text", "perfil.lock")
        with pytest.raises(ProfileFolderUnavailableError, match=r"perfil\.lock"):
            repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
        repo.release_lock("Hugo", "PC-SALA")


def test_erro_de_permissao_ao_apagar_a_trava_nao_levanta_ao_soltar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, pasta = make_repo(tmp_path)
    repo.acquire_lock("Hugo", "PC-SALA", T0, force=False)
    with monkeypatch.context() as m:
        quebrar_metodo_de_path(m, "unlink", "perfil.lock")
        repo.release_lock("Hugo", "PC-SALA")  # fechar o app tem que funcionar
    assert (pasta / "perfil.lock").exists()  # sobra a trava do próprio PC: renova ou expira

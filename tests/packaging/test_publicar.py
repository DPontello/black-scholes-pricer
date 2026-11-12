"""Versão e notas do release (packaging/publicar.py), sem rede, sem GitHub e sem git de verdade."""

import importlib.util
import re
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "packaging" / "publicar.py"


def _p() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_publicar_release", SCRIPT)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize(
    ("pyproject", "linha"),
    [("0.5.0.dev0", (0, 5)), ("0.5.0", (0, 5)), ("1.0.0", (1, 0)), ("1.12", (1, 12))],
)
def test_linha_sao_os_dois_primeiros_numeros(pyproject: str, linha: tuple[int, int]) -> None:
    assert _p().linha(pyproject) == linha


def test_linha_sem_numeros_e_recusada() -> None:
    with pytest.raises(ValueError, match="sem números"):
        _p().linha("dev")


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("v0.5.0", (0, 5, 0)),
        ("0.5.10", (0, 5, 10)),
        ("v0.5.0-rc1", None),
        ("0.5.0.dev0", None),
        ("v0.5", None),
        ("nada", None),
    ],
)
def test_numeros_aceita_so_tres_numeros(texto: str, esperado: tuple[int, int, int] | None) -> None:
    assert _p().numeros(texto) == esperado


@pytest.mark.parametrize(
    ("pyproject", "tags", "esperada"),
    [
        ("0.5.0.dev0", ["v0.2.0", "v0.3.0", "v0.4.0"], "0.5.0"),
        ("0.5.0.dev0", ["v0.4.0", "v0.5.0", "v0.5.3", "v0.5.1"], "0.5.4"),
        ("0.5.0", ["v0.5.9", "v0.5.10"], "0.5.11"),
        ("1.0.0", ["v0.5.7"], "1.0.0"),
        ("0.5.0", ["v0.5.0-rc1", "nada", "v0.5.0"], "0.5.1"),
    ],
)
def test_proxima_versao(pyproject: str, tags: list[str], esperada: str) -> None:
    assert _p().proxima_versao(pyproject, tags) == esperada


def test_linha_menor_que_a_do_ultimo_release_falha() -> None:
    with pytest.raises(ValueError, match="menor"):
        _p().proxima_versao("0.4.0", ["v0.5.2"])


def test_tag_anterior_e_a_maior_versao_numerica() -> None:
    assert _p().tag_anterior(["v0.4.0", "v0.10.0", "v0.9.1", "x"]) == "v0.10.0"
    assert _p().tag_anterior([]) is None


MSG = "Merge pull request #{n} from DPontello/{ramo}\n\n{titulo}\n"


def test_notas_tiram_prefixo_e_filtram_o_que_nao_e_para_ela() -> None:
    msgs = [
        MSG.format(n=17, ramo="feat/montador-simples", titulo="Montador simples: cadeia enxuta"),
        MSG.format(n=15, ramo="docs/x", titulo="docs(app): desenho do Montador"),
        MSG.format(n=14, ramo="feat/s5", titulo="feat(app): acabamento da semana 5"),
        MSG.format(n=12, ramo="fix/t", titulo="fix(testes): isola a configuração"),
        MSG.format(n=20, ramo="development", titulo="Release"),
        "Merge branch 'development'\n",
        MSG.format(n=9, ramo="chore/x", titulo="chore: limpa"),
        MSG.format(n=8, ramo="feat/y", titulo="feat(app): acabamento da semana 5"),
    ]
    assert _p().notas(msgs) == "- Montador simples: cadeia enxuta\n- Acabamento da semana 5"


def test_notas_sem_nada_para_ela_dizem_ajustes_internos() -> None:
    assert _p().notas(["Merge branch 'development'\n"]) == "- Ajustes internos"
    assert _p().notas([]) == "- Ajustes internos"


def test_notas_deixam_de_fora_o_pr_da_master_e_os_outros_tipos_internos() -> None:
    msgs = [
        MSG.format(n=30, ramo="master", titulo="feat: não conta"),
        MSG.format(n=29, ramo="t/x", titulo="test(app): cobre o caso"),
        MSG.format(n=28, ramo="c/x", titulo="ci: muda o workflow"),
        MSG.format(n=27, ramo="f/x", titulo="feat!: quebra a compatibilidade"),
        "Merge pull request #26 from DPontello/f/y\n\n\nfix(app): corrige o zoom\n\ncorpo do PR\n",
    ]
    assert _p().notas(msgs) == "- Quebra a compatibilidade\n- Corrige o zoom"


def test_gravar_troca_so_a_versao_do_project() -> None:
    texto = '[project]\nname = "x"\nversion = "0.5.0.dev0"\n[tool.x]\nversion = "9"\n'
    assert _p().gravar_versao(texto, "0.5.3") == texto.replace('"0.5.0.dev0"', '"0.5.3"')
    with pytest.raises(ValueError):
        _p().gravar_versao(texto, "0.5.3.dev0")


def test_gravar_sem_versao_no_project_falha() -> None:
    with pytest.raises(ValueError, match="version"):
        _p().gravar_versao('[project]\nname = "x"\n[tool.x]\nversion = "9"\n', "0.5.3")
    with pytest.raises(ValueError, match="project"):
        _p().gravar_versao('[tool.x]\nversion = "9"\n', "0.5.3")


class GitFalso:
    """Um ``git`` que responde conforme os argumentos e registra as chamadas."""

    def __init__(
        self, *, tags: str = "", no_commit: str = "", anteriores: str = "", log: str = ""
    ) -> None:
        self.tags = tags
        self.no_commit = no_commit
        self.anteriores = anteriores
        self.log = log
        self.chamadas: list[tuple[str, ...]] = []

    def __call__(self, *args: str) -> str:
        self.chamadas.append(args)
        if args == ("tag", "--list", "v*"):
            return self.tags
        if args[:2] == ("tag", "--points-at") and args[3:] == ("--list", "v*"):
            return self.no_commit
        if args[:2] == ("tag", "--merged") and args[3:] == ("--list", "v*"):
            return self.anteriores
        if args[0] == "log":
            return self.log
        raise AssertionError(f"git inesperado: {args}")


def _pyproject(tmp_path: Path, versao: str = "0.5.0.dev0") -> Path:
    arquivo = tmp_path / "pyproject.toml"
    arquivo.write_text(f'[project]\nname = "x"\nversion = "{versao}"\n', encoding="utf-8")
    return arquivo


def test_main_versao_imprime_a_proxima(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    git = GitFalso(tags="v0.2.0\nv0.3.0\nv0.4.0\n")
    argv = ["versao", "--commit", "abc123", "--pyproject", str(_pyproject(tmp_path))]
    assert _p().main(argv, git=git) == 0
    assert capsys.readouterr().out == "0.5.0\n"
    assert ("tag", "--points-at", "abc123", "--list", "v*") in git.chamadas


def test_main_versao_de_commit_ja_publicado_imprime_vazio(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = GitFalso(tags="v0.4.0\nv0.5.0\n", no_commit="v0.5.0\n")
    argv = ["versao", "--commit", "abc123", "--pyproject", str(_pyproject(tmp_path))]
    assert _p().main(argv, git=git) == 0
    assert capsys.readouterr().out == "\n"


def test_main_versao_ignora_tag_que_nao_e_release_no_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = GitFalso(tags="v0.4.0\nv0.5.0-rc1\n", no_commit="v0.5.0-rc1\n")
    argv = ["versao", "--commit", "abc123", "--pyproject", str(_pyproject(tmp_path))]
    assert _p().main(argv, git=git) == 0
    assert capsys.readouterr().out == "0.5.0\n"


def test_main_versao_com_linha_menor_falha(tmp_path: Path) -> None:
    git = GitFalso(tags="v0.5.2\n")
    argv = ["versao", "--commit", "abc123", "--pyproject", str(_pyproject(tmp_path, "0.4.0"))]
    with pytest.raises(ValueError, match="menor"):
        _p().main(argv, git=git)


LOG = (
    "Merge pull request #17 from DPontello/feat/montador-simples\n\nMontador simples\n\0"
    "\nMerge pull request #15 from DPontello/docs/x\n\ndocs(app): desenho\n\0"
    "\nMerge branch 'development'\n\0"
)


def test_main_notas_usa_o_intervalo_desde_a_tag_anterior(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = GitFalso(anteriores="v0.3.0\nv0.4.0\n", log=LOG)
    argv = ["notas", "--commit", "abc123", "--pyproject", str(_pyproject(tmp_path))]
    assert _p().main(argv, git=git) == 0
    assert capsys.readouterr().out == "- Montador simples\n"
    assert ("tag", "--merged", "abc123", "--list", "v*") in git.chamadas
    assert ("log", "--merges", "--format=%B%x00", "v0.4.0..abc123") in git.chamadas


def test_main_notas_sem_tag_anterior_usa_so_o_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = GitFalso(log=LOG)
    argv = ["notas", "--commit", "abc123", "--pyproject", str(_pyproject(tmp_path))]
    assert _p().main(argv, git=git) == 0
    assert capsys.readouterr().out == "- Montador simples\n"
    assert ("log", "--merges", "--format=%B%x00", "abc123") in git.chamadas


def test_main_gravar_reescreve_o_arquivo(tmp_path: Path) -> None:
    pyproject = _pyproject(tmp_path)
    git = GitFalso()
    assert _p().main(["gravar", "0.5.3", "--pyproject", str(pyproject)], git=git) == 0
    assert pyproject.read_text(encoding="utf-8") == '[project]\nname = "x"\nversion = "0.5.3"\n'
    assert git.chamadas == []


def test_git_roda_o_git_de_verdade_so_pelo_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos: list[tuple[list[str], dict[str, object]]] = []

    def falso(comando: list[str], **opcoes: object) -> subprocess.CompletedProcess[str]:
        pedidos.append((comando, opcoes))
        return subprocess.CompletedProcess(comando, 0, stdout="v0.4.0\n", stderr="")

    monkeypatch.setattr(subprocess, "run", falso)
    assert _p()._git("tag", "--list", "v*") == "v0.4.0\n"
    assert pedidos == [
        (["git", "tag", "--list", "v*"], {"check": True, "capture_output": True, "text": True})
    ]


WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _workflow(nome: str) -> str:
    return (WORKFLOWS / nome).read_text(encoding="utf-8")


def _blocos_run(workflow: str) -> list[str]:
    """O texto de cada `run:` do workflow: a linha dele e, no `run: |`, as de recuo maior."""
    linhas = workflow.splitlines()
    blocos: list[str] = []
    for i, linha in enumerate(linhas):
        achado = re.match(r"(\s*(?:- )?)run:(.*)$", linha)
        if achado is None:
            continue
        recuo = len(achado.group(1))
        bloco = [achado.group(2)]
        for seguinte in linhas[i + 1 :]:
            if seguinte.strip() and len(seguinte) - len(seguinte.lstrip()) <= recuo:
                break
            bloco.append(seguinte)
        blocos.append("\n".join(bloco))
    return blocos


def _job(workflow: str, nome: str) -> str:
    """O texto de um job do workflow: da chave `  nome:` até a próxima chave de job."""
    achado = re.search(rf"^  {nome}:\n(.*?)(?=^  \S|^\S|\Z)", workflow, re.M | re.S)
    assert achado is not None, nome
    return achado.group(1)


def test_publicacao_roda_depois_do_ci_verde_na_master() -> None:
    publicar = _workflow("publicar.yml")
    assert "workflow_run:" in publicar
    assert 'workflows: ["CI"]' in publicar
    assert "branches: [master]" in publicar
    assert "github.event.workflow_run.conclusion == 'success'" in publicar
    assert "contents: write" in publicar
    assert "uses: ./.github/workflows/instalador.yml" in publicar
    assert "gh release create" in publicar
    assert "--latest" in publicar
    # Só `push`: um pull request de fork com ramo chamado master também dispara o workflow_run, e
    # este tem token de escrita.
    assert "github.event.workflow_run.event == 'push'" in _job(publicar, "versao")
    # Todo passo usa o commit que o CI testou (head_sha), nunca a ponta da master.
    sha = "${{ github.event.workflow_run.head_sha }}"
    assert f"ref: {sha}" in _job(publicar, "versao")
    assert f"SHA: {sha}" in _job(publicar, "versao")
    assert f"ref: {sha}" in _job(publicar, "instalador")
    assert f"SHA: {sha}" in _job(publicar, "release")
    assert '--target "$SHA"' in _job(publicar, "release")
    # As notas vêm do git log: passam por variável de ambiente, nunca coladas no script.
    blocos = _blocos_run(publicar)
    assert any("gh release create" in bloco for bloco in blocos)
    assert not any("needs.versao.outputs.notas" in bloco for bloco in blocos)


def test_instalador_reutilizavel_grava_a_versao_antes_do_pip() -> None:
    instalador = _workflow("instalador.yml")
    entrada = re.search(r"^  workflow_call:\n(.*?)(?=^  \S|^\S|\Z)", instalador, re.M | re.S)
    assert entrada is not None
    assert re.search(r"^ {6}ref:$", entrada.group(1), re.M)
    assert re.search(r"^ {6}versao:$", entrada.group(1), re.M)
    # No pwsh a variável é `$env:`; `"$VERSAO_RELEASE"` sairia vazia e gravaria nada.
    gravar = instalador.index('python packaging/publicar.py gravar "$env:VERSAO_RELEASE"')
    assert gravar < instalador.index('pip install ".[app]"')


def test_instalador_reutilizavel_so_le_o_repositorio() -> None:
    # O `contents: write` do publicar.yml não chega ao job que roda npm ci, pip e choco.
    job = _job(_workflow("instalador.yml"), "windows")
    assert re.search(r"^    permissions:\n      contents: read$", job, re.M)
    assert "contents: write" not in job


def test_fumaca_confere_que_o_app_diz_a_versao_do_release() -> None:
    # Se o instalador publicado disser outra versão que a da tag, o app instalado acharia sempre
    # que há versão nova.
    instalador = _workflow("instalador.yml")
    passo = re.search(
        r"^ {6}- name: Fumaça do app.*?\n(.*?)(?=^ {6}- |\Z)", instalador, re.M | re.S
    )
    assert passo is not None
    assert "VERSAO_RELEASE: ${{ inputs.versao }}" in passo.group(1)
    assert "$saude.versao -ne $env:VERSAO_RELEASE" in passo.group(1)
    assert 'throw "o app diz $($saude.versao), o release é $env:VERSAO_RELEASE"' in passo.group(1)

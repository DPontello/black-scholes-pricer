# Atualização pelo app e versão nova a cada subida na master — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** cada push na `master` com o CI verde publica um release `vX.Y.Z` com o instalador do
Windows. O app instalado avisa ao abrir que há versão nova, e com um clique baixa, instala por
cima e reabre.

**Architecture:**
- **CI:** um script Python sem dependências (`packaging/publicar.py`) calcula a versão e as notas
  a partir das tags e das mensagens de merge. Um workflow novo (`publicar.yml`) reaproveita o
  `instalador.yml`, transformado em workflow reutilizável, e cria o release.
- **Servidor:** um adaptador de saída (`adapters/outbound/atualizacao.py`) consulta a API de
  releases, baixa, confere o SHA-256 e abre o instalador silencioso. Uma rota nova
  (`/api/versao`) expõe isso. O servidor ganha um pedido de encerramento e um aviso de "a janela
  voltou".
- **Tela:** uma janela de diálogo (`AvisoVersao`) montada uma vez no `App`.

**Tech Stack:** Python 3.12 stdlib (`urllib`, `hashlib`, `subprocess`), FastAPI, uvicorn,
React 18 + TS, Vitest + Testing Library, GitHub Actions, Inno Setup 6 (Pascal Script).

**Spec:** `docs/superpowers/specs/2026-11-12-atualizacao-automatica-design.md`

## Global Constraints

- **Sem commit, sem push, sem merge** (regra do autor). Nenhum passo deste plano faz commit. Nada
  roda `gh release`, `gh workflow run` ou cria tag.
- **Sem dependência nova:** `dependencies = []` e o extra `app` (`fastapi`, `uvicorn`,
  `websockets`) não mudam. A rede no servidor é só `urllib.request`.
- **Repositório:** `DPontello/black-scholes-pricer`. API:
  `https://api.github.com/repos/DPontello/black-scholes-pricer/releases/latest`. Prefixo
  obrigatório do download:
  `https://github.com/DPontello/black-scholes-pricer/releases/download/`.
- **Arquivo do release:** `PainelOpcoes-<versão>-setup.exe`. Tag: `v<versão>`, com versão
  `X.Y.Z` só de números.
- **Rede só no app instalado no Windows** (`frozen_dir is not None` e `platform.system() ==
  "Windows"`). Fora dele, nada sai para a rede.
- **Nenhum teste toca a rede, o GitHub, os perfis reais** (`~/.config/painel-opcoes`) **ou roda
  `git commit`.** Rede, git e `subprocess` entram por funções injetadas.
- **Contratos do import-linter:** camadas config → adapters → application → domain; domínio e
  aplicação só com a biblioteca padrão. Este trabalho não toca `domain` nem `application`.
- **Textos em português do Brasil, exatamente como no spec §3.E.**
- **`mypy --strict` cobre `tests/`:** os testes deste plano aparecem como esboço, mas no arquivo
  levam tipos, como os testes ao redor.
- **Gates** (da raiz, com `VENV=/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin`):
  - `$VENV/ruff check .`
  - `$VENV/ruff format --check .`
  - `$VENV/mypy`
  - `$VENV/lint-imports`
  - `$VENV/pytest --cov=options_engine`, com cobertura ≥ 95%
  - `npm --prefix frontend run verificar`
  - `npm --prefix frontend run build`
  - O Vitest de um arquivo só roda de dentro de `frontend/`: `cd frontend && npx vitest run <arquivo>`.

## Decisões minhas (além do spec)

1. **O instalador espera o app sair.** Ele recebe `/ESPERAR=<pid>` e, no `InitializeSetup`,
   espera até 60 s o processo do app terminar antes de copiar. Sem isso, o instalador silencioso
   pode tentar trocar o executável com o servidor ainda encerrando.
2. **O servidor se encerra 2 s depois de abrir o instalador** (`ATRASO_ENCERRAR_S = 2.0`), para a
   tela ainda ler a fase `instalando`. Se a leitura falhar, a tela entende que o servidor saiu e
   também passa para "Instalando".
3. **A janela antiga avisa que voltou** consultando `GET /api/saude?janela=1`. Só essa consulta
   conta como "a janela voltou"; a consulta do próprio processo (`wait_until_up`) não conta.
4. **Notas:** o primeiro caractere de cada item vai em maiúscula. A ordem é a do `git log` (mais
   novo primeiro). Itens repetidos saem.
5. **Esc** fecha a janela no aviso ("Agora não") e no erro ("Fechar"). Durante o download e a
   instalação, a janela não fecha.
6. **MB na tela:** `Math.round(bytes / 1048576)`.

## Review Focus

1. **Sem internet ou GitHub lento:** a página não pode esperar `/api/versao` para aparecer, e a
   consulta com falha fica guardada pelos mesmos 30 min. Teste na Task 3 (falha guardada) e na
   Task 5 (`/api/versao` com 404 ou erro não mostra nada e não quebra o App).
2. **Dois cliques em Atualizar,** ou dois `POST`, abrem um download só. Teste na Task 3.
3. **Download que cai no meio, ou SHA-256 diferente:** o arquivo parcial é apagado, a fase vira
   `erro`, e "Tentar de novo" começa do zero e funciona. Teste na Task 3 (erro e depois sucesso no
   mesmo `Atualizador`) e na Task 5 (botão "Tentar de novo").
4. **O servidor some no meio da consulta de andamento:** isso quer dizer que está instalando, e
   não é erro. Teste na Task 5.
5. **JSON de release inesperado:**
   - tag `v0.5.1-rc1`;
   - `body` nulo;
   - `assets` vazio, sem `digest` ou com outro host;
   - `size` zero.

   Cada um dá "sem versão nova", nunca exceção. Teste na Task 3.

---

### Task 1: Script de versão e notas do release

**Files:**
- Create: `packaging/publicar.py`
- Test: `tests/packaging/test_publicar.py`

**Interfaces:**
- Produces, usado pela Task 2 no workflow:
  - `python packaging/publicar.py versao --commit <sha>` imprime a versão nova (`0.5.0`), ou
    uma linha vazia se o commit já tem tag `vX.Y.Z`;
  - `python packaging/publicar.py notas --commit <sha>` imprime as notas em Markdown;
  - `python packaging/publicar.py gravar <versão> [--pyproject <caminho>]` reescreve o
    `version = "…"` do `[project]`.
- Funções puras:
  - `linha(versao_pyproject: str) -> tuple[int, int]`
  - `numeros(tag_ou_versao: str) -> tuple[int, int, int] | None`
  - `proxima_versao(versao_pyproject: str, tags: Sequence[str]) -> str`
  - `tag_anterior(tags: Sequence[str]) -> str | None`
  - `notas(mensagens: Sequence[str]) -> str`
  - `gravar_versao(texto_pyproject: str, versao: str) -> str`
  - `main(argv: Sequence[str] | None = None, git: Callable[..., str] = _git) -> int`

  `_git(*args: str) -> str` roda `git` com `subprocess.run(check=True, capture_output=True,
  text=True)` e devolve o stdout.

- [ ] **Step 1: Escrever os testes que falham** em `tests/packaging/test_publicar.py`. Carregue o
  script como o `test_instalador.py` carrega o `versao.py`, com `importlib.util.spec_from_file_location`,
  porque `packaging` colide com o pacote do PyPI.

```python
@pytest.mark.parametrize(("pyproject", "tags", "esperada"), [
    ("0.5.0.dev0", ["v0.2.0", "v0.3.0", "v0.4.0"], "0.5.0"),
    ("0.5.0.dev0", ["v0.4.0", "v0.5.0", "v0.5.3", "v0.5.1"], "0.5.4"),
    ("0.5.0", ["v0.5.9", "v0.5.10"], "0.5.11"),
    ("1.0.0", ["v0.5.7"], "1.0.0"),
    ("0.5.0", ["v0.5.0-rc1", "nada", "v0.5.0"], "0.5.1"),
])
def test_proxima_versao(pyproject, tags, esperada): ...

def test_linha_menor_que_a_do_ultimo_release_falha():
    with pytest.raises(ValueError, match="menor"):
        _p().proxima_versao("0.4.0", ["v0.5.2"])

def test_tag_anterior_e_a_maior_versao_numerica():
    assert _p().tag_anterior(["v0.4.0", "v0.10.0", "v0.9.1", "x"]) == "v0.10.0"
    assert _p().tag_anterior([]) is None

MSG = "Merge pull request #{n} from DPontello/{ramo}\n\n{titulo}\n"
def test_notas_tiram_prefixo_e_filtram_o_que_nao_e_para_ela():
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

def test_notas_sem_nada_para_ela_dizem_ajustes_internos():
    assert _p().notas(["Merge branch 'development'\n"]) == "- Ajustes internos"

def test_gravar_troca_so_a_versao_do_project():
    texto = '[project]\nname = "x"\nversion = "0.5.0.dev0"\n[tool.x]\nversion = "9"\n'
    assert _p().gravar_versao(texto, "0.5.3") == texto.replace('"0.5.0.dev0"', '"0.5.3"')
    with pytest.raises(ValueError):
        _p().gravar_versao(texto, "0.5.3.dev0")
```

  Testes do `main` com um `git` falso (uma função que recebe `*args` e devolve texto conforme
  `args`), lendo um `pyproject.toml` temporário:
  - `test_main_versao_imprime_a_proxima`, que imprime `0.5.0\n`;
  - `test_main_versao_de_commit_ja_publicado_imprime_vazio`: o `git tag --points-at <sha> --list
    v*` devolve `v0.5.0`, e a saída é `\n`;
  - `test_main_notas_usa_o_intervalo_desde_a_tag_anterior`: o falso registra que o `log` recebeu
    `v0.4.0..<sha>`, com `--merges` e `--format=%B%x00`;
  - `test_main_gravar_reescreve_o_arquivo`.

- [ ] **Step 2: Rodar e ver falhar.** `$VENV/pytest tests/packaging/test_publicar.py -q` falha
  porque o arquivo não existe.
- [ ] **Step 3: Implementar `packaging/publicar.py`.** Siga o estilo do `versao.py`: docstring
  dizendo como o workflow chama, `tomllib` para ler o pyproject e só biblioteca padrão.
  - **`main` e o pyproject:** o `main` lê o `pyproject.toml` da raiz (`Path(__file__).parents[1]`)
    e aceita `--pyproject` em todos os subcomandos, para os testes.
  - **`main` e o git:**
    - tags com `git tag --list v*`;
    - tags do commit com `git tag --points-at <sha> --list v*`;
    - tags anteriores com `git tag --merged <sha> --list v*`;
    - mensagens com `git log --merges --format=%B%x00 <anterior>..<sha>`, separadas por `\0`.
      Sem tag anterior, o intervalo é só `<sha>`.
  - **Notas, a primeira linha da mensagem:** tem de casar
    `^Merge pull request #\d+ from \S+/(\S+)$`; ramo `development` ou `master` fica de fora.
  - **Notas, o título:** é a primeira linha não vazia depois dela. O prefixo
    `^([a-z]+)(\(([^)]*)\))?!?:\s*` sai. Os tipos `docs`, `test`, `ci`, `chore` e o escopo
    `testes` ficam de fora.
- [ ] **Step 4: Rodar e ver passar.** `$VENV/pytest tests/packaging/test_publicar.py -q`.
  Depois, `$VENV/ruff check packaging tests/packaging` e `$VENV/mypy` limpos.

### Task 2: Workflow de publicação, instalador reutilizável e instalador silencioso

**Files:**
- Create: `.github/workflows/publicar.yml`
- Modify: `.github/workflows/instalador.yml`
- Modify: `packaging/windows/PainelOpcoes.iss`
- Test: `tests/packaging/test_instalador.py`, que ganha testes, e `tests/packaging/test_publicar.py`,
  que ganha os testes do workflow

**Interfaces:**
- Consumes: os três subcomandos da Task 1.
- Produces, usado pela Task 3:
  - o instalador aceita `/RELANCAR=1` e reabre `PainelOpcoes.exe --depois-de-atualizar` no modo
    silencioso;
  - o instalador aceita `/ESPERAR=<pid>` e espera o processo sair (até 60 s) antes de instalar.

- [ ] **Step 1: Escrever os testes que falham.** São testes de texto, no estilo dos que já
  existem em `test_instalador.py`.
  - `test_atualizacao_silenciosa_reabre_o_app_com_o_parametro`: o `.iss` tem uma linha `[Run]`
    com `Filename: "{app}\PainelOpcoes.exe"`, `Parameters: "--depois-de-atualizar"`,
    `Flags: nowait` e `Check: Relancar`. A entrada `postinstall skipifsilent` atual continua.
  - `test_instalador_espera_o_app_sair_antes_de_copiar`: o `[Code]` tem `{param:ESPERAR|0}`,
    `{param:RELANCAR|0}`, `WizardSilent`, `OpenProcess@kernel32.dll stdcall`,
    `WaitForSingleObject` e `60000`.
  - `test_publicacao_roda_depois_do_ci_verde_na_master`, em `test_publicar.py`: o `publicar.yml`
    contém:
    - `workflow_run:`, `workflows: ["CI"]`, `branches: [master]`;
    - `github.event.workflow_run.conclusion == 'success'`;
    - `contents: write`;
    - `uses: ./.github/workflows/instalador.yml`;
    - `gh release create` e `--latest`.

    E não contém `${{ needs.versao.outputs.notas }}` dentro de um `run:`: as notas passam por
    variável de ambiente.
  - `test_instalador_reutilizavel_grava_a_versao_antes_do_pip`: no `instalador.yml`, o
    `workflow_call:` tem as entradas `ref` e `versao`, e
    `python packaging/publicar.py gravar` aparece antes de `pip install ".[app]"`.
- [ ] **Step 2: Rodar e ver falhar.**
  `$VENV/pytest tests/packaging/test_instalador.py tests/packaging/test_publicar.py -q`.
- [ ] **Step 3: Mudar o `PainelOpcoes.iss`.**
  - **No `[Run]`:** acrescente a linha silenciosa antes da atual.
  - **No `[Code]`:**
    - as funções externas `OpenProcess`, `WaitForSingleObject` e `CloseHandle` do
      `kernel32.dll`, com `SYNCHRONIZE = $00100000`;
    - `function Relancar: Boolean`, que dá `WizardSilent and (ExpandConstant('{param:RELANCAR|0}') = '1')`;
    - `function InitializeSetup: Boolean`, que lê `StrToIntDef(ExpandConstant('{param:ESPERAR|0}'), 0)`
      e, se for diferente de 0, abre o processo com `SYNCHRONIZE`, espera `60000` ms, fecha o
      handle e devolve `True`.

    Comente em português, no estilo do arquivo, por que esperar.
- [ ] **Step 4: Mudar o `instalador.yml`.**
  - **Em `on:`:** acrescente `workflow_call:` com as entradas `ref` e `versao` (`type: string`,
    `required: false`, `default: ""`).
  - **No checkout:** `with: ref: ${{ inputs.ref }}`.
  - **Antes de "PyInstaller do app":** um passo `if: inputs.versao != ''` que roda
    `python packaging/publicar.py gravar "$VERSAO_RELEASE"`, com
    `env: VERSAO_RELEASE: ${{ inputs.versao }}`.
  - **O resto não muda.** O artefato continua `PainelOpcoes-${{ env.VERSAO }}-setup`, e a
    `VERSAO` passa a ser a gravada. Atualize o comentário do topo.
- [ ] **Step 5: Criar o `publicar.yml`.**

```yaml
# Publicação (desenho de 12/11): cada push na master com o CI verde vira o release vX.Y.Z, com o
# instalador do Windows. Precisa estar na master para o workflow_run disparar.
name: Publicar

on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    branches: [master]

permissions:
  contents: write

concurrency:
  group: publicar
  cancel-in-progress: false

jobs:
  versao:
    name: Versão e notas
    if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'
    runs-on: ubuntu-latest
    outputs:
      versao: ${{ steps.calculo.outputs.versao }}
      notas: ${{ steps.calculo.outputs.notas }}
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.workflow_run.head_sha }}
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - id: calculo
        env:
          SHA: ${{ github.event.workflow_run.head_sha }}
        run: |
          # Atribuição em linha própria: com o bash -e do Actions, uma falha do script (linha menor
          # que a do último release) para o job; dentro do echo ela se perderia.
          versao=$(python packaging/publicar.py versao --commit "$SHA")
          echo "versao=$versao" >> "$GITHUB_OUTPUT"
          {
            echo "notas<<FIM_DAS_NOTAS"
            python packaging/publicar.py notas --commit "$SHA"
            echo "FIM_DAS_NOTAS"
          } >> "$GITHUB_OUTPUT"

  instalador:
    needs: versao
    if: needs.versao.outputs.versao != ''
    uses: ./.github/workflows/instalador.yml
    with:
      ref: ${{ github.event.workflow_run.head_sha }}
      versao: ${{ needs.versao.outputs.versao }}

  release:
    name: Release no GitHub
    needs: [versao, instalador]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: PainelOpcoes-${{ needs.versao.outputs.versao }}-setup
          path: instalador
      - env:
          GH_TOKEN: ${{ github.token }}
          GH_REPO: ${{ github.repository }}
          VERSAO: ${{ needs.versao.outputs.versao }}
          NOTAS: ${{ needs.versao.outputs.notas }}
          SHA: ${{ github.event.workflow_run.head_sha }}
        run: |
          printf '%s\n' "$NOTAS" > notas.md
          gh release create "v$VERSAO" "instalador/PainelOpcoes-$VERSAO-setup.exe" \
            --target "$SHA" --title "Painel de Opções $VERSAO" --notes-file notas.md --latest
```

- [ ] **Step 6: Rodar e ver passar.**
  `$VENV/pytest tests/packaging -q`. Se houver `actionlint` no PATH, rode
  `actionlint .github/workflows/*.yml`. Se não houver, diga isso no relatório e não instale.

### Task 3: Adaptador de atualização (consultar, baixar, conferir, instalar)

**Files:**
- Create: `src/options_engine/adapters/outbound/atualizacao.py`
- Test: `tests/adapters/test_atualizacao.py`

**Interfaces:**
- Consumes: os parâmetros do instalador da Task 2 (`/RELANCAR=1`, `/ESPERAR=<pid>`).
- Produces, usado pela Task 4:

```python
Fase = Literal["parado", "baixando", "instalando", "erro"]

@dataclass(frozen=True, slots=True)
class VersaoNova:
    versao: str
    novidades: tuple[str, ...]
    tamanho: int
    url: str
    sha256: str | None  # hex minúsculo, do campo "digest" ("sha256:<hex>")

@dataclass(frozen=True, slots=True)
class EstadoAtualizacao:
    fase: Fase
    baixado: int = 0
    total: int = 0
    mensagem: str = ""

URL_ULTIMA_VERSAO: Final = "https://api.github.com/repos/DPontello/black-scholes-pricer/releases/latest"
PREFIXO_DOWNLOAD: Final = "https://github.com/DPontello/black-scholes-pricer/releases/download/"
VALIDADE_S: Final = 1800.0
ATRASO_ENCERRAR_S: Final = 2.0

def numeros(versao: str) -> tuple[int, int, int] | None   # "0.5.0.dev0" -> (0, 5, 0)
def ler_release(corpo: object, atual: str) -> VersaoNova | None
def argumentos_do_instalador(arquivo: Path, pid: int, log: Path) -> list[str]

class Atualizador:
    def __init__(self, atual: str, *, ativo: bool,
                 buscar_json: Callable[[str], object],
                 baixar: Callable[[str], Iterable[bytes]],
                 abrir_instalador: Callable[[Sequence[str]], None],
                 encerrar: Callable[[], None],
                 pasta: Path, log: Path, pid: int,
                 relogio: Callable[[], float] = time.monotonic,
                 esperar: Callable[[float], None] = time.sleep,
                 em_segundo_plano: Callable[[Callable[[], None]], None] = <thread daemon>) -> None
    @property
    def atual(self) -> str
    def conferir(self) -> VersaoNova | None
    def iniciar(self) -> EstadoAtualizacao
    def estado(self) -> EstadoAtualizacao

def atualizador_do_app(atual: str, *, ativo: bool, config_dir: Path,
                       encerrar: Callable[[], None]) -> Atualizador
```

- [ ] **Step 1: Escrever os testes que falham.** Use um `Atualizador` montado por uma fábrica de
  teste com falsos: `buscar_json` devolve um dict ou levanta, `baixar` devolve uma lista de
  pedaços, `abrir_instalador` registra os argumentos, `encerrar` conta as chamadas,
  `em_segundo_plano` roda na hora, `esperar` registra e `relogio` é controlado. Use `tmp_path`
  como `pasta`. O release de exemplo tem:
  - `{"tag_name": "v0.5.1", "body": "- Montador simples\n- Cores suaves\n", "assets": [...]}`;
  - um arquivo `PainelOpcoes-0.5.1-setup.exe`, com `size` igual ao tamanho do conteúdo falso,
    `browser_download_url` com o prefixo e `digest` igual a `sha256:<hex do conteúdo falso>`.

  Os testes:
  - `test_versao_mais_nova_vira_aviso_com_as_novidades`: `atual` `0.5.0` resulta em
    `VersaoNova("0.5.1", ("Montador simples", "Cores suaves"), …)`.
  - `test_versao_igual_ou_mais_velha_nao_avisa`: `0.5.1` e `0.6.0` dão `None`.
  - `test_comparacao_e_numero_a_numero`: `0.5.9` contra a tag `v0.5.10` avisa, e `0.5.0.dev0`
    contra `v0.5.0` não avisa.
  - `test_release_estranho_nao_avisa` (Review Focus 5), parametrizado em:
    - tag `v0.5.1-rc1`;
    - `body: None`, que avisa com novidades `()`;
    - `assets: []`;
    - arquivo com outro nome;
    - URL de outro host;
    - `size: 0`;
    - corpo que não é dict.

    Todos dão `None`, menos `body: None`.
  - `test_sem_digest_confere_pelo_tamanho`: `sha256 is None`, e o download com o tamanho certo
    instala.
  - `test_fora_do_app_instalado_nao_consulta_a_rede`: com `ativo=False`, `conferir()` dá `None`
    e o `buscar_json` não é chamado.
  - `test_falha_na_consulta_vira_none_e_fica_guardada` (Review Focus 1): o `buscar_json` levanta
    `URLError`, e `conferir()` dá `None`. Até 1800 s, não chama de novo; depois de 1800 s, chama.
  - `test_consulta_com_sucesso_fica_guardada_30_min`.
  - `test_atualizar_baixa_confere_abre_o_instalador_e_encerra`:
    - o estado passa por `baixando` com `baixado` crescente;
    - `abrir_instalador` recebe exatamente
      `[str(pasta / "PainelOpcoes-0.5.1-setup.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES",
      "/NORESTART", "/CLOSEAPPLICATIONS", "/RELANCAR=1", f"/ESPERAR={pid}", f"/LOG={log}"]`;
    - `esperar` é chamado com `2.0` antes de `encerrar`;
    - o estado final é `EstadoAtualizacao("instalando", total, total)`.
  - `test_dois_pedidos_abrem_um_download_so` (Review Focus 2): com um `em_segundo_plano` que só
    guarda a função, o segundo `iniciar()` devolve o estado `baixando`, e só uma função foi
    guardada.
  - `test_arquivo_que_nao_confere_e_apagado_e_vira_erro` (Review Focus 3): com digest errado, a
    fase vira `erro`, a mensagem é `"o arquivo baixado não confere"`, nenhum arquivo fica em
    `pasta`, e `abrir_instalador` e `encerrar` não são chamados.
  - `test_conexao_que_cai_no_meio_apaga_o_parcial_e_tentar_de_novo_funciona`
    (Review Focus 3): o `baixar` falha (`OSError`) depois do primeiro pedaço, a mensagem é
    `"a conexão com o GitHub falhou"` e a pasta fica vazia. Num novo `iniciar()` com o download
    certo, o estado chega a `instalando`.
  - `test_instalador_que_nao_abre_vira_erro_e_o_servidor_fica`: `abrir_instalador` levanta
    `OSError`, a mensagem é `"não deu para abrir o instalador"` e `encerrar` não é chamado.
  - `test_sem_versao_nova_iniciar_vira_erro`: a mensagem é `"não há versão nova para baixar"`.
  - `test_download_fora_do_prefixo_e_recusado`: o `baixar` real de `atualizador_do_app` levanta
    `ValueError` para `https://exemplo.com/x.exe`, antes de abrir qualquer conexão.
  - `test_atualizador_do_app_usa_a_pasta_de_logs_e_a_temporaria`: o `log` é
    `config_dir / "logs" / "atualizacao.log"`, e a `pasta` é
    `Path(tempfile.gettempdir()) / "PainelOpcoes-atualizacao"`. Exponha os dois como atributos
    só de leitura, ou teste pelos argumentos do instalador com `abrir_instalador` substituído.
- [ ] **Step 2: Rodar e ver falhar.** `$VENV/pytest tests/adapters/test_atualizacao.py -q`.
- [ ] **Step 3: Implementar o `atualizacao.py`.**
  - **O estado** fica atrás de um `threading.Lock`. O download escreve em pedaços e calcula o
    SHA-256 junto. Em qualquer falha, apaga o arquivo e muda o estado.
  - **Exceções do download e do instalador:** `OSError`, `ValueError` e `urllib.error.URLError`
    (que já é `OSError`). Viram as mensagens exatas acima e uma linha `_log.warning`.
  - **A fábrica `atualizador_do_app`** monta as funções reais:
    - `buscar_json` com `urllib.request.Request`, cabeçalhos
      `Accept: application/vnd.github+json` e `User-Agent: PainelOpcoes/<atual>`, `timeout=5`;
    - `baixar`, que recusa URL fora do `PREFIXO_DOWNLOAD`, abre com `timeout=30`, recusa um
      `geturl()` final que não comece com `https://` e devolve pedaços de 64 KiB;
    - `abrir_instalador` com `subprocess.Popen`, `stdin`, `stdout` e `stderr` em `DEVNULL`,
      `close_fds=True` e
      `creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)`;
    - `pid=os.getpid()`.
  - **A thread padrão** de `em_segundo_plano` é `threading.Thread(daemon=True,
    name="atualizacao")`.
- [ ] **Step 4: Rodar e ver passar.** Rode o mesmo comando, mais `$VENV/mypy` e
  `$VENV/lint-imports`.

### Task 4: Rotas, encerramento a pedido e "uma janela só"

**Files:**
- Create: `src/options_engine/adapters/inbound/web/versao.py`
- Modify: `src/options_engine/adapters/inbound/web/app.py`, para `create_app` e `saude`
- Modify: `src/options_engine/adapters/inbound/web/launch.py`, para `Encerramento`, `serve` e a
  constante
- Modify: `src/options_engine/config/web_app.py`, para `build_web_app`
- Modify: `src/options_engine/__main__.py`, para o comando `app`
- Test: `tests/web/test_versao_api.py` (novo), `tests/web/test_app.py` e
  `tests/web/test_launch.py`

**Interfaces:**
- Consumes: `Atualizador`, `VersaoNova`, `EstadoAtualizacao` e `atualizador_do_app` da Task 3.
- Produces, usado pela Task 5:
  - `GET /api/versao` → `{"atual": str, "nova": null | {"versao": str, "novidades": [str],
    "tamanho": int}}`. A URL e o SHA não saem.
  - `POST /api/versao/atualizar` e `GET /api/versao/atualizar` → `{"fase": "parado" |
    "baixando" | "instalando" | "erro", "baixado": int, "total": int, "mensagem": str}`.
  - `GET /api/saude?janela=1` responde como hoje e avisa o servidor de que a janela voltou.
- Interfaces internas:
  - `router_versao(atualizador: AtualizadorDoApp) -> APIRouter`. O `AtualizadorDoApp` é um
    `Protocol` com `atual`, `conferir`, `iniciar` e `estado`.
  - `create_app(routers, static_dir=None, *, lifespan=None, ao_ver_janela: Callable[[], None] | None = None)`.
  - `class Encerramento`, com `ligar(servidor: _ComSaida) -> None` e `pedir() -> None`. Um
    `pedir()` antes de `ligar()` fica guardado e vale ao ligar. O `_ComSaida` é um `Protocol`
    com `should_exit: bool`.
  - `serve(app, port, on_ready=None, encerramento: Encerramento | None = None)`.
  - `ESPERA_JANELA_ANTIGA_S: Final = 15.0` no `launch.py`.
  - `build_web_app(..., encerrar: Callable[[], None] | None = None, ao_ver_janela: Callable[[], None] | None = None)`.

- [ ] **Step 1: Escrever os testes que falham.**
  - **`tests/web/test_versao_api.py`,** com um `Atualizador` falso (classe simples com os quatro
    membros) e `TestClient(create_app([router_versao(falso)]))`:
    - `test_sem_versao_nova_devolve_so_a_atual`;
    - `test_com_versao_nova_devolve_versao_novidades_e_tamanho_sem_url`;
    - `test_atualizar_comeca_e_devolve_o_estado`;
    - `test_estado_da_atualizacao`.
  - **`tests/web/test_app.py`:** `test_saude_com_janela_avisa_que_a_janela_voltou`. O
    `GET /api/saude?janela=1` chama o gancho uma vez; o `GET /api/saude` não chama. A resposta é
    a mesma nos dois.
  - **`tests/web/test_launch.py`:**
    - `test_encerramento_pedido_liga_o_should_exit`;
    - `test_encerramento_pedido_antes_de_ligar_vale_ao_ligar`;
    - `test_comando_app_passa_encerrar_e_ao_ver_janela_para_o_web_app`: no padrão de
      `build_falso(**kwargs)`, `recebido["encerrar"]` e `recebido["ao_ver_janela"]` são
      chamáveis;
    - `test_depois_de_atualizar_nao_abre_janela_se_a_antiga_voltar`: capture o `on_ready`
      passado ao `serve` falso, troque `launch.ESPERA_JANELA_ANTIGA_S` por `0.05`, chame
      `ao_ver_janela()` e depois `on_ready()`; `open_window` não é chamado;
    - `test_depois_de_atualizar_abre_janela_se_ninguem_voltar`: o mesmo, sem chamar
      `ao_ver_janela()`; `open_window` é chamado uma vez com a URL do app.
  - **`build_web_app` real**
    (`test_web_app_monta_a_rota_de_versao_desligada_fora_do_windows_instalado`):
    `build_web_app(config_dir=tmp_path, static_dir=None, bridge=False, machine_name="pc")`, e o
    `GET /api/versao` dá `nova: null`, sem rede. Coloque o teste em `tests/web/test_versao_api.py`,
    usando `tmp_path` como configuração.
- [ ] **Step 2: Rodar e ver falhar.**
  `$VENV/pytest tests/web/test_versao_api.py tests/web/test_app.py tests/web/test_launch.py -q`.
- [ ] **Step 3: Implementar.**
  - **`versao.py`:** modelos pydantic de saída, no estilo dos outros routers (`VersaoNovaOut`,
    `InfoVersaoOut`, `EstadoAtualizacaoOut`).
  - **`app.py`:** o `saude(janela: bool = False)` chama `ao_ver_janela()` quando `janela` for
    verdadeiro e houver gancho.
  - **`launch.serve`:** cria o `uvicorn.Server`, chama `encerramento.ligar(servidor)` se houver,
    e depois `run()`. O `Encerramento.pedir` põe `servidor.should_exit = True`, o caminho normal
    do uvicorn, que roda o `lifespan`: solta a trava do perfil e para a ponte.
  - **`build_web_app`:**
    - `atual = importlib.metadata.version("options-engine")`;
    - `ativo = frozen_dir is not None and platform.system() == "Windows"`;
    - `atualizador_do_app(atual, ativo=ativo, config_dir=config_dir, encerrar=encerrar or (lambda: None))`;
    - `router_versao(...)` entra na lista de routers;
    - `ao_ver_janela` vai para o `create_app`.
  - **`__main__.app`:**
    - a opção `--depois-de-atualizar`, com ajuda "aberto pelo instalador depois de uma
      atualização: só abre a janela se a antiga não voltar";
    - `encerramento = launch.Encerramento()` e `janela_voltou = threading.Event()`;
    - passa `encerrar=encerramento.pedir` e `ao_ver_janela=janela_voltou.set` ao
      `build_web_app`;
    - com `--depois-de-atualizar` e sem `--sem-janela`, o `on_ready` é
      `lambda: None if janela_voltou.wait(launch.ESPERA_JANELA_ANTIGA_S) else launch.open_window(janela, url)`.
      Leia a constante na hora da chamada, para o teste poder trocá-la;
    - `launch.serve(web, porta, on_ready, encerramento=encerramento)`.

    O ramo "já está aberto" não muda.
- [ ] **Step 4: Rodar e ver passar.** Rode os mesmos testes, depois o `tests/web` inteiro, mais
  `$VENV/mypy` e `$VENV/lint-imports`.

### Task 5: A janela do aviso na tela

**Files:**
- Create: `frontend/src/api/versao.ts`
- Create: `frontend/src/componentes/AvisoVersao.tsx`
- Test: `frontend/src/componentes/AvisoVersao.test.tsx`
- Modify: `frontend/src/App.tsx`, para montar uma vez, fora dos ramos de perfil
- Modify: `frontend/src/tema.css`, com `.veu` e `.janela-aviso`
- Test: `frontend/src/App.test.tsx`, que ganha um teste

**Interfaces:**
- Consumes: as rotas da Task 4.
- Produces:

```ts
export type VersaoNova = { versao: string; novidades: string[]; tamanho: number };
export type InfoVersao = { atual: string; nova: VersaoNova | null };
export type FaseAtualizacao = "parado" | "baixando" | "instalando" | "erro";
export type EstadoAtualizacao = { fase: FaseAtualizacao; baixado: number; total: number; mensagem: string };
export function conferirVersao(): Promise<InfoVersao>;            // GET /api/versao
export function iniciarAtualizacao(): Promise<EstadoAtualizacao>; // POST /api/versao/atualizar
export function estadoAtualizacao(): Promise<EstadoAtualizacao>;  // GET /api/versao/atualizar
export function versaoNoAr(): Promise<string>;                    // GET /api/saude?janela=1 → .versao

type Props = { intervaloMs?: number; limiteMs?: number; recarregar?: () => void };
export function AvisoVersao({ intervaloMs = 1000, limiteMs = 120_000,
                              recarregar = () => window.location.reload() }: Props): JSX.Element | null;
```

  Use `pedir` e `json` de `api/cliente.ts`.

- [ ] **Step 1: Escrever os testes que falham** em `AvisoVersao.test.tsx`, com `simularFetch`,
  `intervaloMs` pequeno (por exemplo, 5) e `recarregar = vi.fn()`.
  - `test("com versão nova, a janela diz a versão, a atual e o que mudou")`:
    - `role="dialog"` com nome "Versão nova do app: 0.5.1";
    - o texto "Você está usando a 0.5.0. O que mudou:";
    - os itens;
    - os botões "Atualizar" e "Agora não";
    - o foco em "Atualizar".
  - `test("sem versão nova, ou com a consulta falhando, nada aparece")`: `nova: null`, e também
    404, não mostram `dialog`.
  - `test("mais de 5 novidades mostram 5 e 'e mais N'")`: com 7, aparecem 5 itens e "e mais 2".
  - `test("Agora não e Esc fecham a janela")`.
  - `test("Atualizar mostra o andamento em MB e depois Instalando")`: o estado `baixando`
    (12582912 de 31457280) mostra "Baixando a versão nova: 12 de 30 MB" e um `progressbar`.
    Depois, com `instalando`, mostra "Instalando. O app fecha e abre de novo sozinho, em menos de
    um minuto."
  - `test("se o servidor some durante o andamento, é porque está instalando")`
    (Review Focus 4): o `GET /api/versao/atualizar` passa a rejeitar (o `fetch` lança `TypeError`),
    e aparece "Instalando…".
  - `test("quando o app volta na versão nova, a página recarrega")`: o `GET /api/saude?janela=1`
    responde `0.5.0`, depois `0.5.1`. `recarregar` é chamado uma vez, e só depois do `0.5.1`.
  - `test("passado o limite sem voltar, diz para abrir pelo atalho")`: com `limiteMs` pequeno,
    aparece "Se o app não abrir sozinho, abra pelo atalho Painel de Opções."
  - `test("erro no download mostra o motivo, e Tentar de novo começa outra vez")`
    (Review Focus 3): o estado `erro` com a mensagem "o arquivo baixado não confere" mostra "Não
    deu para baixar a versão nova: o arquivo baixado não confere. O app continua na versão
    0.5.0." "Tentar de novo" faz um novo `POST` (conte as chamadas de `fetch` com
    `method: "POST"`), e "Fechar" fecha.

  Em `App.test.tsx`, acrescente
  `test("o aviso de versão aparece por cima da escolha de perfil")`: `/api/perfil` com 404,
  `/api/perfis` com `[]` e `/api/versao` com `nova`. Aparecem "Quem está usando?" e o `dialog`.
- [ ] **Step 2: Rodar e ver falhar.**
  `cd frontend && npx vitest run src/componentes/AvisoVersao.test.tsx src/App.test.tsx`.
- [ ] **Step 3: Implementar.**
  - **Os estados internos:** `fechado`, `aviso`, `baixando`, `instalando`, `demorou` e `erro`.
  - **O andamento:** em `baixando`, consulta `estadoAtualizacao` a cada `intervaloMs`. Uma
    rejeição leva a `instalando`.
  - **A volta do app:** em `instalando`, consulta `versaoNoAr` a cada `intervaloMs`, ignorando
    as falhas, e chama `recarregar()` quando a versão for a nova. Passado `limiteMs`, mostra a
    frase do atalho e continua consultando.
  - **Limpeza:** os intervalos são limpos ao desmontar.
  - **Marcação:** `<div className="veu">` envolve
    `<div role="dialog" aria-modal="true" aria-labelledby=… className="janela-aviso">`, com
    `<progress value max aria-label="Andamento do download">`.
  - **Botões:** "Atualizar" e "Tentar de novo" usam `className="botao-principal"`.
  - **No `App.tsx`:** monte `<AvisoVersao />` uma vez, ao lado do conteúdo, inclusive enquanto
    "Abrindo o Painel de Opções…". Não pode remontar quando o perfil muda.
  - **No `tema.css`:**
    - `.veu` fixo, cobrindo a tela, com fundo `rgba(0, 0, 0, 0.55)` e o diálogo no centro;
    - `.janela-aviso` com fundo `var(--painel)`, borda `var(--borda)`, `max-width: 28rem` e
      margem de 16px nas laterais em telas estreitas.

    Nenhuma cor nova fora dos tokens.
- [ ] **Step 4: Rodar e ver passar.** Rode o mesmo comando, depois
  `npm --prefix frontend run verificar` (todos os testes e o `tsc`) e
  `npm --prefix frontend run build`.

### Task 6: Documentação e conferência final

**Files:**
- Modify: `README.md`, nas linhas ~226-246 (instalador do Windows e "Atualizar")
- Modify: `docs/superpowers/HANDOFF-2026-11-02.md`, com a §13 nova no fim
- Modify: `docs/ROADMAP.md`, com um item ao lado do "Montador simples (2026-11-10)"

- [ ] **Step 1: README.**
  - **De onde vem o instalador:** a página de releases do GitHub
    (`https://github.com/DPontello/black-scholes-pricer/releases/latest`). Cada push na `master`
    com o CI verde publica uma versão. O artefato do PR continua para testar empacotamento.
  - **"Atualizar"** passa a dizer:
    - o app avisa ao abrir e atualiza com um clique;
    - a primeira vez, saindo da versão de 05/11, é à mão;
    - o registro fica em `%APPDATA%\PainelOpcoes\logs\atualizacao.log`.
  - **Linux:** não muda.
  - **Estilo:** o do texto ao redor, com itens curtos em negrito.
- [ ] **Step 2: HANDOFF §13, "12/11: atualização pelo app".**
  - o que entrou;
  - a ordem do spec §8, passo a passo, com os comandos que o autor roda (merge da `development`
    na `master` e push; instalar a `v0.5.0` à mão; subir uma mudança para gerar a `v0.5.1`);
  - os critérios 3, 4 e 5 do spec §7 como lista de conferência no Windows;
  - os testes sem internet;
  - o registro `atualizacao.log`.
- [ ] **Step 3: ROADMAP.** Um item `**Atualização pelo app (2026-11-12):**` com link para o spec.
- [ ] **Step 4: Gates completos** (Global Constraints), todos com a saída mostrada no relatório.

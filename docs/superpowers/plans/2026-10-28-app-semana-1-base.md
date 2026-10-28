# App de opções — Semana 1 (base) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** abrir o app local numa janela, escolher o perfil, ver cotações ao vivo do Tryd (lista de ativos e cadeia de opções) com recuo rotulado para o fim de dia da B3, e importar arquivos da B3 arrastando.

**Architecture:** FastAPI como adapter inbound (extra `app`) serve uma SPA React e uma API REST + WebSocket. A ponte do Tryd é um processo separado em Python do Windows (pacote `options_ponte`, stdlib + pywin32) que fala JSON por linha via TCP local com o app. Adapters Tryd e COTAHIST ficam atrás dos ports; perfis em JSON na pasta de cada pessoa.

**Tech Stack:** Python 3.12+ (FastAPI ≥ 0.115, uvicorn ≥ 0.30 e websockets ≥ 13 só no extra `app`; httpx ≥ 0.27 no `dev`), pywin32 só na ponte, React 18 + TypeScript 5 + Vite 5 + Vitest 2, react-router-dom 6.

**Spec:** `docs/superpowers/specs/2026-10-28-app-opcoes-design.md`. Planos das semanas 2 a 5 vêm depois deste.

## Global Constraints

- **Nunca** `git commit`, `push`, merge, rebase: as mudanças ficam no working tree e o autor commita. Este plano não tem passos de commit.
- Português em código, docstrings, testes (`test_...` em pt-BR), mensagens de tela e de erro, como o resto do repo.
- `domain/` e `application/` stdlib-only (import-linter). `dependencies = []` do pyproject continua vazio: FastAPI, uvicorn e websockets só no extra `app`.
- `win32com`, `pythoncom`, `pywintypes` e `win32api` proibidos em `options_engine` (contrato novo do import-linter). Só `src/options_ponte/rtd.py` os usa, e só dentro de funções, via `importlib` (o pacote precisa importar no Linux).
- Servidores escutam só em `127.0.0.1`. App HTTP na porta 8765 (a próxima livre se estiver ocupada); ponte na 8766.
- Lado de book ausente é `None`, nunca `0` (ADR-0003); prêmio pelo lado certo do book (ADR-0004).
- Nenhum dado real do Tryd ou da B3 no repositório; fixtures sintéticas. Nenhum perfil ou carteira dentro do repositório.
- Tempo injetado nos adapters ao vivo (`Clock` e uma função monotônica); nada de `datetime.now()` no domínio.
- Nome nas telas: **"Painel de Opções"**; pasta de configuração `painel-opcoes` (Linux, `$XDG_CONFIG_HOME` ou `~/.config`) e `PainelOpcoes` (Windows, `%APPDATA%`).
- Constantes fixadas (fonte única em `src/options_engine/adapters/outbound/tryd/settings.py`, salvo indicação): `PORTA_PONTE = 8766`, `TEMPO_CARGA_S = 3.0`, `PONTE_ATRASADA_S = 10.0`, `PONTE_PERDIDA_S = 30.0`, `LIMITE_TOPICOS = 600`, `FAIXA_STRIKES = 0.20`, `VENCIMENTOS_PADRAO = 2`, `CAMPOS_ATIVO = ("ULT", "OCP", "OVD", "NEG", "VOL", "FEC", "HOR", "DAT")`, `CAMPOS_OPCAO = ("ULT", "OCP", "OVD", "NEG", "VOL", "HOR", "DAT")`. Em `options_ponte/protocolo.py`: `PROGID = "RTDTrading.RtdServer"`, `CLSID = "{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}"`, tópico RTD `(f"{ticker}_B_0", campo)`. Cadastro velho: mais de 5 dias úteis. Trava de perfil expira em 12 h.
- Gates ao fim de cada task (todos verdes):
  `.venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check . && .venv/bin/python -m mypy && PYTHONPATH=src .venv/bin/lint-imports --no-cache && .venv/bin/python -m pytest -q -p no:cacheprovider`
  e, a partir da Task 15, `npm --prefix frontend run verificar`.

## Review Focus

1. **Tryd fechado, ou ponte que não sobe, ao abrir o app:** o app abre, o status diz "desconectado" e cotações e cadeia vêm do fim de dia, rotuladas `fim_de_dia`. Teste na Task 11.
2. **Zeros iniciais do RTD:** nunca viram preço. Antes da carga a cotação não existe. Teste na Task 10.
3. **Pasta do perfil indisponível** (nuvem não montada, pendrive fora): erro claro com o caminho; nada é criado em outro lugar e a configuração não muda. Teste na Task 3.
4. **Trava deixada por um PC que travou:** trava com mais de 12 h é ignorada; mais nova pede confirmação, com o nome do PC. Teste na Task 3.
5. **Arquivo errado arrastado** (PDF, COTAHIST truncado, CSV sem `TckrSymb`): recusado com motivo, e nada fica gravado na biblioteca. Teste na Task 5.

---

### Task 1: Base do backend web

**Files:**
- Modify: `pyproject.toml` (versão `0.5.0.dev0`; extra `app = ["fastapi>=0.115", "uvicorn>=0.30", "websockets>=13"]`; `httpx>=0.27` no `dev`; terceiro contrato do import-linter)
- Modify: `.github/workflows/ci.yml` (job `quality` instala `-e ".[dev,app]"`)
- Modify: `.gitignore` (`src/options_engine/adapters/inbound/web/static/`, `frontend/node_modules/`)
- Create: `src/options_engine/adapters/inbound/web/__init__.py`, `app.py`, `errors.py`
- Test: `tests/web/__init__.py`, `tests/web/test_app.py`

**Interfaces:**
- Produces: `create_app(routers: Sequence[APIRouter], static_dir: Path | None = None) -> FastAPI` em `app.py`. Inclui `GET /api/saude`; com `static_dir`, serve os arquivos e devolve `index.html` para qualquer caminho fora de `/api` (SPA).
- Produces: `ERROR_STATUS: dict[type[Exception], int]` e `error_body(exc: Exception) -> dict[str, object]` em `errors.py`. `DomainError` vira `{"erro": <nome da classe>, "mensagem": str(exc)}`, com status 422 por padrão e `UnknownSymbolError` → 404. Tasks seguintes acrescentam entradas ao dicionário.
- Contrato novo do import-linter: `forbidden`, nome `"pywin32 só na ponte do Tryd"`, `source_modules = ["options_engine"]`, `forbidden_modules = ["win32com", "pythoncom", "pywintypes", "win32api"]`.

- [ ] **Step 1: Editar o `pyproject.toml`** (versão, extra `app`, `httpx` no `dev`, contrato do import-linter) **e instalar** no venv local: `.venv/bin/pip install -e ".[dev,app]"`. Esperado: termina sem erro.
- [ ] **Step 2: Escrever os testes que falham**

```python
def test_saude_responde_ok_com_a_versao_do_pacote() -> None:
    resposta = TestClient(create_app([])).get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "versao": importlib.metadata.version("options-engine")}


def test_erro_de_dominio_vira_422_e_simbolo_desconhecido_404() -> None:
    router = APIRouter()

    @router.get("/api/teste/{caso}")
    def rota(caso: str) -> None:
        if caso == "desconhecido":
            raise UnknownSymbolError("XXXX99")
        raise InvalidDomainValueError("valor ruim")

    cliente = TestClient(create_app([router]))
    r = cliente.get("/api/teste/desconhecido")
    assert (r.status_code, r.json()) == (404, {"erro": "UnknownSymbolError", "mensagem": "XXXX99"})
    r = cliente.get("/api/teste/outro")
    assert (r.status_code, r.json()["erro"]) == (422, "InvalidDomainValueError")


def test_spa_devolve_index_fora_da_api_e_404_json_dentro(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=raiz></div>", encoding="utf-8")
    cliente = TestClient(create_app([], static_dir=tmp_path))
    assert cliente.get("/mercado").text == "<div id=raiz></div>"
    assert cliente.get("/api/inexistente").status_code == 404
```

- [ ] **Step 3: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/web/test_app.py -q`. Esperado: FAIL (módulo inexistente).
- [ ] **Step 4: Implementar** `create_app`, `ERROR_STATUS` e `error_body`. Endpoints de cálculo nas tasks seguintes são `def` síncronos (o Starlette os roda no threadpool; ROADMAP S4).
- [ ] **Step 5: Rodar os testes:** mesmo comando. Esperado: PASS.
- [ ] **Step 6: Gates.** O `lint-imports` deve listar **3 contratos KEPT**.

---

### Task 2: VOs de perfil e de cotação do ativo

**Files:**
- Create: `src/options_engine/domain/model/profile.py`, `src/options_engine/domain/model/quotes.py`
- Modify: `src/options_engine/domain/model/errors.py` (acrescentar ao catálogo: `ProfileFolderUnavailableError`, `ProfileLockedError`, `DuplicateProfileError`, `UnknownProfileError`, `NoActiveProfileError`, todas filhas de `DomainError`)
- Test: `tests/domain/test_profile.py`, `tests/domain/test_quotes.py`

**Interfaces:**
- Produces: `normalize_ticker(raw: str) -> str` (strip + upper; vazio ou com caractere não alfanumérico → `InvalidDomainValueError`).
- Produces: `Profile(name: str, watchlist: tuple[str, ...], cdi_annual: float)`, frozen. Invariantes: nome sem espaços nas pontas, não vazio, até 40 caracteres; cada ticker já normalizado e sem repetição; `cdi_annual` finito com `0 <= cdi < 1`.
- Produces: `ProfileEntry(name: str, folder: str)`, frozen.
- Produces: `ProfileLockedError(machine: str, since: datetime)` com os atributos `machine` e `since`.
- Produces: `DataSource(Enum)`: `AO_VIVO = "ao_vivo"`, `ATRASADO = "atrasado"`, `FIM_DE_DIA = "fim_de_dia"`.
- Produces: `UnderlyingQuote(symbol: str, last: float | None, bid: float | None, ask: float | None, previous_close: float | None, trades: int, volume: float, timestamp: datetime, source: DataSource)`, frozen. Preços `None` ou finitos > 0; `bid <= ask` quando os dois existem; `trades >= 0`; `volume` finito ≥ 0; timestamp tz-aware. Propriedade `change_pct -> float | None` = `last / previous_close - 1` quando os dois existem.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_ticker_normalizado_e_lista_sem_repeticao() -> None:
    assert normalize_ticker(" petr4 ") == "PETR4"
    with pytest.raises(InvalidDomainValueError):
        normalize_ticker("PETR 4")
    with pytest.raises(InvalidDomainValueError):
        Profile("Hugo", ("PETR4", "PETR4"), 0.15)
    with pytest.raises(InvalidDomainValueError):
        Profile("Hugo", ("petr4",), 0.15)


def test_cdi_fora_da_faixa_e_nome_vazio_sao_rejeitados() -> None:
    for cdi in (-0.01, 1.0, math.nan):
        with pytest.raises(InvalidDomainValueError):
            Profile("Hugo", (), cdi)
    with pytest.raises(InvalidDomainValueError):
        Profile("  ", (), 0.15)


def test_cotacao_do_ativo_lado_ausente_e_variacao() -> None:
    t = datetime(2026, 10, 28, 12, 2, 31, tzinfo=B3_UTC_OFFSET)
    q = UnderlyingQuote("PETR4", 52.51, None, 52.53, 52.79, 22704, 679557741.0, t, DataSource.AO_VIVO)
    assert q.bid is None
    assert q.change_pct == pytest.approx(52.51 / 52.79 - 1)
    with pytest.raises(InvalidDomainValueError):
        UnderlyingQuote("PETR4", 0.0, None, None, None, 0, 0.0, t, DataSource.AO_VIVO)
    with pytest.raises(InvalidDomainValueError):
        UnderlyingQuote("PETR4", 52.5, 52.6, 52.5, None, 0, 0.0, t, DataSource.AO_VIVO)
```

- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/domain/test_profile.py tests/domain/test_quotes.py -q`. Esperado: FAIL (import).
- [ ] **Step 3: Implementar** os VOs e as exceções, no padrão de `market.py` e `chain.py` (forma negada contra NaN, mensagens com o valor recebido).
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 3: Perfis — armazenamento, trava e serviço

**Files:**
- Modify: `src/options_engine/application/ports/outbound.py` (`ProfileRepository`), `src/options_engine/application/ports/inbound.py` (`ProfileUseCase`)
- Create: `src/options_engine/application/use_cases/profiles.py`
- Create: `src/options_engine/adapters/outbound/storage/__init__.py`, `json_files.py`, `profiles.py`
- Test: `tests/adapters/storage/__init__.py`, `tests/adapters/storage/test_profiles.py`, `tests/application/test_profiles.py`

**Interfaces:**
- Consumes: `Profile`, `ProfileEntry`, as exceções de perfil (Task 2); `Clock`.
- Produces: `write_json_atomic(path: Path, data: object) -> None` (grava `*.tmp` e troca com `os.replace`).
- Produces (port): `ProfileRepository` com `list_profiles() -> tuple[ProfileEntry, ...]`, `create(name: str, folder: str) -> Profile`, `load(name: str) -> Profile`, `save(name: str, profile: Profile) -> None`, `acquire_lock(name: str, machine: str, now: datetime, force: bool) -> None`, `release_lock(name: str, machine: str) -> None`.
- Produces (adapter): `JsonProfileRepository(config_path: Path)`.
  - Configuração da máquina: `{"versao": 1, "perfis": [{"nome": ..., "pasta": ...}]}`.
  - Na pasta do perfil, `perfil.json`: `{"versao": 1, "nome": ..., "ativos": [...], "cdi_anual": ...}`. Padrão na criação: ativos `["PETR4", "VALE3"]` e `cdi_anual` = `DEFAULT_CDI_ANNUAL` (0.15).
  - `create` numa pasta que já tem `perfil.json` **adota** o perfil existente, e o `nome` do arquivo prevalece. É assim que o mesmo perfil, na nuvem, aparece em outro PC.
  - Trava: `perfil.lock` com `{"pc": ..., "desde": ISO com fuso}`.
- Produces (serviço): `ProfileService(repository: ProfileRepository, clock: Clock, machine_name: str)` com `list() -> tuple[ProfileEntry, ...]`, `create(name: str, folder: str) -> Profile`, `open(name: str, force: bool = False) -> Profile`, `active() -> Profile` (sem perfil aberto → `NoActiveProfileError`), `set_watchlist(tickers: Sequence[str]) -> Profile` (normaliza e remove repetidos mantendo a ordem) e `close() -> None`. `ProfileUseCase` é o Protocol desses métodos.

- [ ] **Step 1: Escrever os testes que falham (adapter, com `tmp_path`)**

```python
def test_cria_e_relê_o_perfil_na_pasta_escolhida(tmp_path: Path) -> None:
    pasta = tmp_path / "drive_hugo"; pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json")
    criado = repo.create("Hugo", str(pasta))
    assert criado == Profile("Hugo", ("PETR4", "VALE3"), 0.15)
    assert JsonProfileRepository(tmp_path / "config.json").load("Hugo") == criado
    assert not list(pasta.glob("*.tmp"))


def test_pasta_indisponivel_nao_cria_nada_nem_muda_a_configuracao(tmp_path: Path) -> None:
    repo = JsonProfileRepository(tmp_path / "config.json")
    with pytest.raises(ProfileFolderUnavailableError, match="nuvem_desmontada"):
        repo.create("Mãe", str(tmp_path / "nuvem_desmontada"))
    assert not (tmp_path / "nuvem_desmontada").exists()
    assert repo.list_profiles() == ()


def test_adota_perfil_existente_na_pasta(tmp_path: Path) -> None:
    pasta = tmp_path / "onedrive_mae"; pasta.mkdir()
    JsonProfileRepository(tmp_path / "pc1.json").create("Mãe", str(pasta))
    adotado = JsonProfileRepository(tmp_path / "pc2.json").create("qualquer", str(pasta))
    assert adotado.name == "Mãe"


def test_trava_de_outro_pc_bloqueia_expira_em_12h_e_cede_ao_forcar(tmp_path: Path) -> None:
    pasta = tmp_path / "p"; pasta.mkdir()
    repo = JsonProfileRepository(tmp_path / "config.json"); repo.create("Hugo", str(pasta))
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
```

- [ ] **Step 2: Escrever os testes do serviço** (repositório falso em memória): `open` define o perfil ativo e trava com `machine_name`; `active()` sem `open` levanta `NoActiveProfileError`; `set_watchlist(["petr4 ", "PETR4", "vale3"])` grava e devolve `("PETR4", "VALE3")`; `close()` libera a trava.
- [ ] **Step 3: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/adapters/storage tests/application/test_profiles.py -q`. Esperado: FAIL.
- [ ] **Step 4: Implementar** port, adapter e serviço. `ProfileFolderUnavailableError` leva o caminho na mensagem.
- [ ] **Step 5: Rodar os testes.** Esperado: PASS.
- [ ] **Step 6: Gates.**

---

### Task 4: API de perfis

**Files:**
- Create: `src/options_engine/adapters/inbound/web/profiles.py`
- Modify: `src/options_engine/adapters/inbound/web/errors.py` (`DuplicateProfileError` → 409, `ProfileLockedError` → 409 com `"trava": {"pc", "desde"}` no corpo, `NoActiveProfileError` e `UnknownProfileError` → 404)
- Test: `tests/web/test_profiles_api.py`

**Interfaces:**
- Consumes: `ProfileUseCase` (Task 3).
- Produces: `router_perfis(service: ProfileUseCase) -> APIRouter` com:
  - `GET /api/perfis` → `[{"nome", "pasta"}]`;
  - `POST /api/perfis` `{"nome", "pasta"}` → 201 com o perfil;
  - `POST /api/perfis/{nome}/abrir` `{"forcar": false}` → 200 com o perfil, ou 409 com a trava;
  - `GET /api/perfil` → perfil ativo, ou 404;
  - `PUT /api/perfil/ativos` `{"ativos": [...]}` → perfil;
  - `POST /api/perfil/fechar` → 204.
- O perfil sai como `{"nome", "ativos", "cdi_anual"}`.

- [ ] **Step 1: Escrever os testes que falham** (TestClient com `ProfileService` real, `JsonProfileRepository` em `tmp_path` e `FixedClock`): criar e listar; abrir; trava de outro PC → 409 com `{"pc": "PC-SALA", ...}` e, com `forcar: true`, 200; pasta inexistente → 422 com o caminho na mensagem; `GET /api/perfil` antes de abrir → 404; `PUT` dos ativos normaliza.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/web/test_profiles_api.py -q`.
- [ ] **Step 3: Implementar** o router com DTOs pydantic só neste módulo.
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 5: Biblioteca de arquivos da B3

**Files:**
- Create: `src/options_engine/adapters/outbound/b3files/__init__.py`, `library.py`
- Create: `src/options_engine/adapters/inbound/web/b3files.py`
- Modify: `src/options_engine/adapters/inbound/web/errors.py` (`B3FileRejectedError` → 422)
- Test: `tests/adapters/b3files/__init__.py`, `tests/adapters/b3files/test_library.py`, `tests/web/test_b3files_api.py`

**Interfaces:**
- Consumes: `parse_cotahist` e `load_instruments` (validação completa do conteúdo); `Clock`; `TradingCalendar`.
- Produces: `B3FileKind(Enum)`: `COTAHIST = "cotahist"`, `CADASTRO = "cadastro"`.
- Produces: `ImportedFile(kind: B3FileKind, name: str, reference_date: date | None, first_date: date | None, imported_at: datetime, path: Path)`. Em COTAHIST, `first_date` é o menor pregão do arquivo; em CADASTRO, `None`. A Task 12 usa `(menor first_date, maior reference_date)` dos COTAHIST como faixa.
- Produces: `B3FileRejectedError(Exception)`, erro de arquivo do adapter, fora do catálogo de domínio, como os `SourceFileError`.
- Produces: `B3FileLibrary(root: Path, clock: Clock)` com:
  - `import_file(name: str, content: bytes) -> ImportedFile`;
  - `files() -> tuple[ImportedFile, ...]`;
  - `latest_cadastro() -> ImportedFile | None`;
  - `cotahist_paths() -> tuple[Path, ...]`.
  - Layout: `root/cotahist/`, `root/cadastro/` e `root/biblioteca.json` (data de importação por arquivo). Reimportar o mesmo nome substitui.
  - Identificação pelo conteúdo: ZIP com um `.TXT` ou texto cuja 1ª linha começa com `00COTAHIST` → COTAHIST; CSV com cabeçalho contendo `TckrSymb` e `OptnStyle` → CADASTRO; senão rejeita com "tipo de arquivo não reconhecido".
  - Data de referência: COTAHIST = maior pregão dos registros; CADASTRO = `_AAAAMMDD` do nome, senão `None`.
  - Validação em diretório temporário, antes de mover para `root`.
- Produces: `CadastroFreshness(reference_date: date, business_days: int, stale: bool)` e `cadastro_freshness(library: B3FileLibrary, calendar: TradingCalendar, today: date) -> CadastroFreshness | None`. Velho quando `business_days_between(ref, hoje) > 5`.
- Produces: `router_arquivos_b3(library: B3FileLibrary) -> APIRouter`:
  - `POST /api/mercado/arquivos?nome=<arquivo>`, corpo binário → 201 `{"tipo", "nome", "data"}`;
  - `GET /api/mercado/arquivos` → lista com `"importado_em"`.

- [ ] **Step 1: Escrever os testes que falham** (fixtures de `tests/data/cotahist/`)

```python
def test_importa_cotahist_txt_e_zip_e_o_cadastro(tmp_path: Path) -> None:
    lib = B3FileLibrary(tmp_path / "mercado", FixedClock(_AGORA))
    txt = (FIXTURE / COTAHIST_NAME).read_bytes()
    assert lib.import_file(COTAHIST_NAME, txt).reference_date == date(2026, 10, 23)
    assert lib.import_file("COTAHIST_D23102026.ZIP", _zip(COTAHIST_NAME, txt)).kind is B3FileKind.COTAHIST
    cad = lib.import_file(INSTRUMENTS_NAME, (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    assert (cad.kind, cad.reference_date) == (B3FileKind.CADASTRO, date(2026, 10, 23))


def test_arquivo_errado_e_recusado_e_nada_fica_gravado(tmp_path: Path) -> None:
    lib = B3FileLibrary(tmp_path / "mercado", FixedClock(_AGORA))
    truncado = b"\n".join((FIXTURE / COTAHIST_NAME).read_bytes().splitlines()[:-1])
    for nome, conteudo in (("nota.pdf", b"%PDF-1.4 ..."), ("COTAHIST.TXT", truncado),
                           ("lista.csv", b"Ticker;Preco\nPETR4;52,5\n")):
        with pytest.raises(B3FileRejectedError):
            lib.import_file(nome, conteudo)
    assert lib.files() == ()
    assert not [p for p in (tmp_path / "mercado").rglob("*") if p.is_file()]


def test_cadastro_velho_depois_de_5_dias_uteis(tmp_path: Path) -> None:
    lib = B3FileLibrary(tmp_path / "m", FixedClock(_AGORA))
    lib.import_file(INSTRUMENTS_NAME, (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    cal = StaticHolidayCalendar.from_packaged_data()
    assert cadastro_freshness(lib, cal, date(2026, 10, 30)) == CadastroFreshness(date(2026, 10, 23), 5, False)
    assert cadastro_freshness(lib, cal, date(2026, 11, 3)) == CadastroFreshness(date(2026, 10, 23), 6, True)
```

- [ ] **Step 2: Escrever o teste da API:** upload do cadastro → 201 `{"tipo": "cadastro", ...}`; upload de PDF → 422 com `"erro": "B3FileRejectedError"`; `GET` lista o cadastro.
- [ ] **Step 3: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/adapters/b3files tests/web/test_b3files_api.py -q`.
- [ ] **Step 4: Implementar** biblioteca, frescor e router.
- [ ] **Step 5: Rodar os testes.** Esperado: PASS.
- [ ] **Step 6: Gates.**

---

### Task 6: Cadastro com os termos da série e vol realizada reutilizável

**Files:**
- Modify: `src/options_engine/adapters/outbound/cotahist/instruments.py`
- Create: `src/options_engine/adapters/outbound/cotahist/volatility.py`
- Modify: `src/options_engine/adapters/outbound/cotahist/adapter.py` (`_vol_realizada` passa a usar `realized_volatility`, sem mudar comportamento)
- Test: `tests/adapters/cotahist/test_instruments.py` (acrescentar), `tests/adapters/cotahist/test_volatility.py`

**Interfaces:**
- Produces: `InstrumentInfo` ganha `option_type: OptionType | None`, `strike: float | None` e `expiry: date | None`, lidos das colunas opcionais `OptnTp`, `ExrcPric` e `XprtnDt`.
  - Leitura tolerante: `OptnTp` por prefixo, sem distinguir maiúsculas (`CALL`, `Put`); `ExrcPric` com `.` ou `,` decimal; `XprtnDt` em `AAAA-MM-DD` ou `DD/MM/AAAA`; valor ilegível ou ausente → `None`.
  - Duplicata contraditória → todos os campos opcionais `None`, como já é para o estilo.
  - Registrar na docstring como premissa a conferir no arquivo real.
- Produces: `realized_volatility(closes: Sequence[float], window: int) -> Volatility | str`. A string é o motivo da indisponibilidade, com as mesmas mensagens de hoje: "histórico insuficiente ... mínimo N (W retornos)" e "vol realizada zero ...".

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_cadastro_traz_tipo_strike_e_vencimento() -> None:
    info = load_instruments(FIXTURE / INSTRUMENTS_NAME)["PETRK280"]
    assert (info.option_type, info.strike, info.expiry, info.exercise_style) == (
        OptionType.CALL, 28.0, date(2026, 11, 19), ExerciseStyle.AMERICAN)


def test_formatos_alternativos_e_lixo(tmp_path: Path) -> None:
    csv_ = tmp_path / "c.csv"
    csv_.write_text("TckrSymb;OptnStyle;OptnTp;ExrcPric;XprtnDt\n"
                    "PETRW285;EURO;Put;28,50;19/11/2026\nPETRX999;EURO;???;abc;amanhã\n", encoding="utf-8")
    dados = load_instruments(csv_)
    assert (dados["PETRW285"].option_type, dados["PETRW285"].strike, dados["PETRW285"].expiry) == (
        OptionType.PUT, 28.5, date(2026, 11, 19))
    assert (dados["PETRX999"].option_type, dados["PETRX999"].strike, dados["PETRX999"].expiry) == (None, None, None)


def test_vol_realizada_confere_com_o_calculo_manual_e_explica_a_falta() -> None:
    closes = [30.0, 30.3, 29.9, 30.6, 30.2]
    retornos = [math.log(b / a) for a, b in itertools.pairwise(closes)]
    esperado = statistics.stdev(retornos) * math.sqrt(252)
    vol = realized_volatility(closes, window=4)
    assert isinstance(vol, Volatility) and vol.value == pytest.approx(esperado, rel=REL_SELF)
    motivo = realized_volatility(closes, window=21)
    assert isinstance(motivo, str) and "mínimo 22" in motivo
```

(`REL_SELF` vem de `tests/_tolerances.py`; nenhuma tolerância inline.)

- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/adapters/cotahist -q`. Esperado: FAIL nos testes novos.
- [ ] **Step 3: Implementar** e refatorar o adapter para usar `realized_volatility`.
- [ ] **Step 4: Rodar a suíte inteira do COTAHIST e a de contrato:** `.venv/bin/python -m pytest tests/adapters/cotahist tests/contract -q`. Esperado: PASS, sem nenhum teste antigo alterado.
- [ ] **Step 5: Gates.**

---

### Task 7: Ponte — protocolo, assinaturas e laço do servidor (sem COM)

**Files:**
- Create: `src/options_ponte/__init__.py`, `protocolo.py`, `assinaturas.py`, `servidor.py` (só stdlib, roda no Linux)
- Test: `tests/ponte/__init__.py`, `tests/ponte/test_protocolo.py`, `tests/ponte/test_assinaturas.py`, `tests/ponte/test_servidor.py`

**Interfaces:**
- Produces (`protocolo.py`):
  - `PROGID`, `CLSID` e `topico_rtd(ticker: str, campo: str) -> tuple[str, str]` (Global Constraints);
  - mensagens frozen:
    - `Valor(ticker: str, campo: str, tipo_valor: str, valor: float | int | str | None, instante: str)`;
    - `Status(tryd: str, motivo: str | None, topicos: int)`, com `tryd` em `"iniciando" | "conectado" | "perdido"`;
    - `Assinar(topicos: tuple[tuple[str, str], ...])`;
    - `Cancelar(topicos: tuple[tuple[str, str], ...])`;
    - `Ping()`, `Pong()`, `Encerrar()`;
  - `Mensagem` = união das mensagens;
  - `codificar(msg: Mensagem) -> bytes`: JSON + `"\n"`, UTF-8, com a chave `"tipo"` ∈ `valor | status | assinar | cancelar | ping | pong | encerrar`;
  - `decodificar(linha: bytes) -> Mensagem`: JSON inválido ou tipo desconhecido → `ErroDeProtocolo(ValueError)`;
  - `classificar_valor(v: object) -> tuple[str, float | int | str | None]`: `float`, `int` (bool fica de fora), `str` e `None` passam como estão; qualquer outro tipo vira `("outro", repr(v))`.
- Produces (`assinaturas.py`): `RegistroDeTopicos(limite: int)` com:
  - `adicionar(topicos) -> tuple[tuple[int, tuple[str, str]], ...]`: devolve os ids novos para `ConnectData`; tópico já assinado é ignorado; passar do limite → `LimiteDeTopicos(Exception)` sem registrar nenhum do lote;
  - `remover(topicos) -> tuple[int, ...]`;
  - `topico(id_: int) -> tuple[str, str] | None`;
  - `total: int`.
- Produces (`servidor.py`):
  - `SessaoRtd` (Protocol): `conectar(id_: int, strings: tuple[str, str]) -> object`, `desconectar(id_: int) -> None`, `atualizar() -> list[tuple[int, object]]`, `vivo() -> bool`, `avisos() -> int`, `encerrar() -> None`;
  - `Ponte(sessao: SessaoRtd, relogio: Callable[[], float], agora_iso: Callable[[], str], limite: int)`:
    - `tratar(cmd: Mensagem) -> list[Mensagem]`: `Assinar` conecta e devolve os valores iniciais como `Valor`; `Cancelar` desconecta; `Ping` devolve `Pong`;
    - `ciclo() -> list[Mensagem]`: com aviso novo, `atualizar()` vira `Valor`s; `Status` a cada 2 s; depois de 5 s sem aviso chama `vivo()`, e `False` vira `Status("perdido", motivo, n)`;
  - `ServidorTcp(ponte: Ponte, porta: int, bombear: Callable[[float], None])` com:
    - `rodar(parar: threading.Event) -> None`: thread de aceite e leitura que enfileira comandos; a thread principal bombeia, trata a fila e difunde para todos os clientes;
    - `endereco -> tuple[str, int]`.
  - `Encerrar` para o laço.

- [ ] **Step 1: Escrever os testes que falham.** Com uma `SessaoFalsa` em memória, cobrir:
  - ida e volta de `codificar` e `decodificar` para todos os tipos;
  - `decodificar(b"{lixo")` levanta `ErroDeProtocolo`;
  - `Assinar([("PETR4", "ULT")])` emite um `Valor` com `tipo_valor == "float"`;
  - assinar duas vezes não reconecta;
  - lote acima do limite devolve `Status` com motivo contendo `"limite de tópicos"`, e a sessão não recebe nenhum `conectar`;
  - `ciclo()` depois de um aviso emite os valores mudados;
  - relógio avançado 5 s com `vivo() == False` emite `Status(tryd="perdido")`;
  - ponta a ponta com `ServidorTcp(porta=0)`: um cliente socket envia `assinar` e recebe uma linha `valor`; `encerrar` faz `rodar` voltar.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/ponte -q`.
- [ ] **Step 3: Implementar** os três módulos.
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates** (o mypy já cobre `src/options_ponte`).

---

### Task 8: Ponte — camada COM e execução no Wine

**Files:**
- Create: `src/options_ponte/rtd.py`, `src/options_ponte/__main__.py`
- Create: `src/options_ponte/rtd_shim.idl` (cópia de `~/.local/share/wineprefixes/tryd/drive_c/rtd-shim/rtd_shim.idl`)
- Create: `scripts/linux/preparar_ponte_wine.sh` (reproduz o ambiente do spike: distrobox `tryd`, Wine, Python 3.12 do Windows em `C:\Python312`, `pip install pywin32`, `widl` do `.idl` e `RegisterTypeLib`)
- Create: `src/options_ponte/README.md` (como rodar no Windows e no Linux)

**Interfaces:**
- Consumes: `Ponte`, `ServidorTcp`, `SessaoRtd` e o protocolo (Task 7).
- Produces: `SessaoRtdCom(progid: str = PROGID, clsid: str = CLSID)`, que implementa `SessaoRtd`. Criação: tenta o ProgID e, se falhar com `CO_E_CLASSSTRING`, usa o CLSID com `CLSCTX_LOCAL_SERVER`. Tipos `IRtdServer`/`IRTDUpdateEvent` em ordem: type library do Tryd `{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}` 1.0; senão a do Excel `{00020813-0000-0000-C000-000000000046}` 1.4 (no Linux, o shim); senão erro explícito que diz qual faltou. Reaproveite o cliente RTD de `tools/tryd_spike/tryd_poc.py`.
- Produces: CLI `python -m options_ponte`:
  - `servir --porta 8766 [--limite 600]`;
  - `diagnostico` (ProgID, CLSID, LocalServer32, qual type library foi usada);
  - `autoteste` (do `tryd_poc.py`: servidor RTD falso no mesmo processo e em outro);
  - `espiar --porta 8766 --ativos PETR4,VALE3 --segundos 10`: cliente só stdlib, roda em qualquer Python e imprime os `Valor`s.

- [ ] **Step 1: Implementar** `rtd.py` e `__main__.py`. Os imports de `pythoncom`/`win32com` ficam dentro das funções.
- [ ] **Step 2: Gates no Linux.** Esperado: verdes; o import-linter não acusa nada (a ponte está fora de `options_engine`).
- [ ] **Step 3: Autoteste no Wine:** `cd src && distrobox enter tryd -- env WINEPREFIX=$HOME/.local/share/wineprefixes/tryd WINEDEBUG=-all PYTHONIOENCODING=utf-8 wine 'C:\Python312\python.exe' -m options_ponte autoteste`. Esperado: última linha `AUTOTESTE OK`.
- [ ] **Step 4: Ao vivo, com o Tryd aberto e logado:**
  - no Wine, `... -m options_ponte servir --porta 8766`;
  - noutro terminal, no Linux, `cd src && ../.venv/bin/python -m options_ponte espiar --porta 8766 --ativos PETR4,VALE3 --segundos 10`;
  - esperado: linhas `valor` com `ULT`, `OCP` e `OVD` não nulos para PETR4 e VALE3 em pregão aberto, e um `status` com `"tryd": "conectado"`.
  - Fora do pregão, registre o que veio (pergunta 13 do spike).

---

### Task 9: Cliente da ponte no app, quadro ao vivo e lançador

**Files:**
- Create: `src/options_engine/adapters/outbound/tryd/__init__.py`, `settings.py`, `board.py`, `client.py`, `launcher.py`
- Test: `tests/adapters/tryd/__init__.py`, `tests/adapters/tryd/test_board.py`, `tests/adapters/tryd/test_client.py`, `tests/adapters/tryd/test_launcher.py`

**Interfaces:**
- Consumes: `options_ponte.protocolo` (só stdlib; o app importa o protocolo da ponte).
- Produces:
  - `settings.py`: as constantes das Global Constraints.
  - `RawValue(kind: str, value: float | int | str | None, received_at: float)`.
  - `LiveBoard(monotonic: Callable[[], float] = time.monotonic)`, thread-safe, com:
    - `mark_subscribed(tickers: Iterable[str]) -> None`;
    - `apply(valor: Valor) -> None`;
    - `values(ticker: str) -> Mapping[str, RawValue]`;
    - `is_loaded(ticker: str) -> bool`: verdadeiro se recebeu algum `Valor` depois da assinatura **ou** se passaram `TEMPO_CARGA_S` desde ela.
  - `BridgeHealth(Enum)`: `CONECTADA`, `ATRASADA`, `DESCONECTADA`.
  - `TrydBridgeClient(board: LiveBoard, host: str = "127.0.0.1", port: int = PORTA_PONTE, monotonic: Callable[[], float] = time.monotonic)` com:
    - `start()`: thread que conecta e reconecta a cada 2 s;
    - `ensure_subscribed(topics: frozenset[tuple[str, str]])`: envia a diferença como `Assinar`/`Cancelar` e reenvia tudo ao reconectar;
    - `health() -> BridgeHealth`: idade da última mensagem < `PONTE_ATRASADA_S` → `CONECTADA`, < `PONTE_PERDIDA_S` → `ATRASADA`, senão (ou nunca) `DESCONECTADA`; `Status(tryd="perdido")` recente → `ATRASADA`;
    - `shutdown_bridge()`: envia `Encerrar`;
    - `stop()`.
  - `default_bridge_command(system: str, src_dir: Path, home: Path, port: int) -> tuple[tuple[str, ...], Path]`: comando e diretório de trabalho.
    - Linux: `("distrobox", "enter", "tryd", "--", "env", f"WINEPREFIX={home}/.local/share/wineprefixes/tryd", "WINEDEBUG=-all", "wine", "C:\\Python312\\python.exe", "-m", "options_ponte", "servir", "--porta", str(port))`, com cwd = `src_dir`.
    - Windows (desenvolvimento): `("python", "-m", "options_ponte", "servir", "--porta", str(port))`.
    - O instalador da semana 4 troca o comando.
  - `BridgeProcess(command: tuple[str, ...], cwd: Path, client: TrydBridgeClient)` com:
    - `start()`;
    - `stop()`: `shutdown_bridge()`, espera 3 s, depois `terminate()`.

- [ ] **Step 1: Escrever os testes que falham**

```python
def test_regra_de_carga_por_atualizacao_ou_tempo() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETRK500", "PETRW500"])
    t[0] = 1.0
    assert not quadro.is_loaded("PETRK500")
    quadro.apply(Valor("PETRK500", "OCP", "float", 4.42, "2026-10-28T12:03:00-03:00"))
    assert quadro.is_loaded("PETRK500")
    t[0] = 3.1
    assert quadro.is_loaded("PETRW500")  # sem atualização, mas passou TEMPO_CARGA_S
```

Mais:
- `test_cliente_assina_reconecta_e_reassina`: ponte falsa = `socketserver` em porta 0 dentro do teste; o cliente envia `Assinar` com os tópicos; os valores recebidos chegam ao quadro; ao derrubar e reabrir o servidor, o cliente reenvia a assinatura completa.
- `test_saude_por_idade_da_ultima_mensagem`: relógio falso em 0 / 9,9 / 10,1 / 30,1 s → `CONECTADA`, `CONECTADA`, `ATRASADA`, `DESCONECTADA`.
- `test_comando_da_ponte_no_linux`: igualdade exata da tupla e do cwd.

- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/adapters/tryd -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 10: Tradução dos valores crus para o domínio

**Files:**
- Create: `src/options_engine/adapters/outbound/tryd/translation.py`
- Test: `tests/adapters/tryd/test_translation.py`

**Interfaces:**
- Consumes: `RawValue` (Task 9); `UnderlyingQuote`, `DataSource` (Task 2); `OptionQuote`, `RejectedSeries`, `OptionContract`.
- Produces:
  - `parse_tryd_timestamp(date_text: str | None, time_text: str | None, tz: tzinfo) -> datetime | None` (`"28/10/2026"`, `"12:02:31"`).
  - `to_underlying_quote(ticker: str, values: Mapping[str, RawValue], loaded: bool, source: DataSource, fallback_time: datetime) -> UnderlyingQuote | None`.
    - `None` se não carregado.
    - Preços `ULT`/`OCP`/`OVD`/`FEC`: número > 0 → `float`; `0`, `None` ou `""` → `None`; texto pt-BR estrito (`^\d+(\.\d{3})*,\d+$` ou `^\d+(\.\d+)?$`) → número; outro texto → `None`.
    - `NEG` → `int`, aceitando `float` inteiro.
    - `VOL` → `float` ≥ 0.
    - Hora vem de `DAT` + `HOR`, senão `fallback_time`.
  - `to_option_quote(contract: OptionContract, values: Mapping[str, RawValue], loaded: bool, fallback_time: datetime) -> OptionQuote | RejectedSeries | None`.
    - `None` se não carregado.
    - `bid > ask` → `RejectedSeries(symbol, "book cruzado na fonte (Tryd)")`.
    - Texto ilegível num campo numérico → `RejectedSeries(symbol, f"valor ilegível no campo {campo}: {valor!r}")`.

- [ ] **Step 1: Escrever os testes que falham.** Cobrir:
  - zeros com `loaded=False` → `None` (Review Focus 2);
  - `loaded=True` com `OCP` = 0.0 → `bid is None` e `ask` presente;
  - `"52,51"` → 52.51 e `"1.234,5"` → 1234.5;
  - `"abc"` em `OVD` → `RejectedSeries` com o motivo acima;
  - `OCP` 4.47 e `OVD` 4.42 → `RejectedSeries` "book cruzado";
  - `NEG` 18502 → `trades == 18502`;
  - timestamp `datetime(2026, 10, 28, 12, 2, 31, tzinfo=B3_UTC_OFFSET)`;
  - sem `HOR` → `fallback_time`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/adapters/tryd/test_translation.py -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 11: Mercado ao vivo, fim de dia e recuo automático (adapters)

**Files:**
- Modify: `src/options_engine/application/ports/outbound.py` (`QuoteBoardPort`, `LiveFeedPort`)
- Create: `src/options_engine/adapters/outbound/tryd/feed.py` (`TrydMarketFeed`)
- Create: `src/options_engine/adapters/outbound/b3files/end_of_day.py` (`EndOfDayMarket`)
- Create: `src/options_engine/adapters/outbound/fallback_market.py` (`FallbackMarket`)
- Test: `tests/adapters/tryd/test_feed.py`, `tests/adapters/b3files/test_end_of_day.py`, `tests/adapters/test_fallback_market.py`

**Interfaces:**
- Consumes: Tasks 5, 6, 9 e 10; `OptionChainPort`; `FixedRateAdapter.from_cdi_annual`; `StaticHolidayCalendar`.
- Produces (ports):
  - `QuoteBoardPort.get_quotes(symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]`. A string é o motivo: `"ativo desconhecido"` ou `"aguardando dados"`.
  - `LiveFeedPort.watch(underlyings: Sequence[str], chain_symbols: Sequence[str]) -> None` e `LiveFeedPort.health() -> DataSource`.
  - `MarketPort(QuoteBoardPort, LiveFeedPort, OptionChainPort, Protocol)`: o que o serviço da Task 12 consome. `EndOfDayMarket` implementa `watch` como no-op e `health()` sempre `FIM_DE_DIA`.
- Produces: `TrydMarketFeed(client: TrydBridgeClient, board: LiveBoard, library: B3FileLibrary, calendar: TradingCalendar, clock: Clock, cdi_annual: Callable[[], float], tz: tzinfo = B3_UTC_OFFSET)`, que implementa `QuoteBoardPort`, `LiveFeedPort` e `OptionChainPort`.
  - `watch`: tópicos = ativos × `CAMPOS_ATIVO`, mais, para cada símbolo de cadeia, as séries do cadastro (raiz igual ou `UndrlygTckrSymb1`) dos `VENCIMENTOS_PADRAO` próximos vencimentos ≥ hoje, com strike a até `FAIXA_STRIKES` do último spot (todas, se o spot ainda não existe), × `CAMPOS_OPCAO`.
  - Corte em `LIMITE_TOPICOS`: ativos primeiro, depois os strikes mais perto do spot.
  - `health`: `CONECTADA` → `AO_VIVO`; `ATRASADA` → `ATRASADO`; `DESCONECTADA` → `FIM_DE_DIA`.
  - `get_chain`:
    - spot = `ULT`;
    - bid/ask do ativo = `OCP`/`OVD`; sem os dois, spot nos três e `underlying_book_available=False`;
    - vol realizada pelas closes do COTAHIST da biblioteca; motivo → `UnderlyingUnavailableError`;
    - taxa pelo CDI do perfil;
    - série do cadastro sem estilo → `RejectedSeries(..., "sem estilo de exercício no cadastro")`;
    - série ainda não carregada fica de fora.
- Produces: `EndOfDayMarket(library: B3FileLibrary, cdi_annual: Callable[[], float], tz: tzinfo = B3_UTC_OFFSET)`, que implementa `QuoteBoardPort` e `OptionChainPort` sobre um `CotahistOptionChainAdapter` do último pregão dos arquivos e do último cadastro. Recarrega quando a biblioteca muda. `UnderlyingQuote.source = FIM_DE_DIA`; `previous_close` = fechamento do pregão anterior.
- Produces: `FallbackMarket(live: TrydMarketFeed, end_of_day: EndOfDayMarket)`, que implementa os três ports e delega ao fim de dia quando `live.health() is DataSource.FIM_DE_DIA`.

- [ ] **Step 1: Escrever os testes que falham** (fixture sintética importada numa biblioteca em `tmp_path`; cliente falso que registra `ensure_subscribed` e tem `health` controlável):
  - `test_watch_assina_dois_vencimentos_na_faixa_e_respeita_o_limite`: tópicos de PETR4 só de 2026-11-19 e 2026-12-18 com strike em [0,8·spot; 1,2·spot]; com `LIMITE_TOPICOS` reduzido por parâmetro de teste, os ativos ficam e os strikes mais longe saem.
  - `test_ponte_desconectada_cai_para_o_fim_de_dia_rotulado` (Review Focus 1): `FallbackMarket.get_quotes(["PETR4"])["PETR4"].source is DataSource.FIM_DE_DIA`, e `get_chain("PETR4")` sai igual à do `CotahistOptionChainAdapter` da fixture.
  - `test_ticker_digitado_errado_vira_motivo`: `get_quotes(["PETR44"])["PETR44"] == "ativo desconhecido"` nas duas fontes.
  - `test_cadeia_ao_vivo_usa_o_quadro_e_rejeita_serie_sem_estilo`: quadro com valores sintéticos e cliente `CONECTADA`; bid/ask das séries vêm do quadro; a série da fixture sem `OptnStyle` aparece em `rejected_series`.
  - `TrydMarketFeed` e `EndOfDayMarket` passam na `OptionChainPortContract` (subclasses em `tests/contract/`).
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/adapters/tryd/test_feed.py tests/adapters/b3files tests/adapters/test_fallback_market.py tests/contract -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 12: Serviço de visão de mercado e composição

**Files:**
- Create: `src/options_engine/application/use_cases/market_view.py`
- Modify: `src/options_engine/application/ports/inbound.py` (`MarketViewUseCase`)
- Modify: `src/options_engine/config/composition.py` (`build_web_app`)
- Test: `tests/application/test_market_view.py`, `tests/config/test_composition.py` (acrescentar)

**Interfaces:**
- Consumes: os três ports da Task 11; `build_smile`, `series_risk` e `SeriesMarket` de `domain/pricing/smile.py`; `ProfileUseCase`.
- Produces:
  - `WatchRow(symbol: str, quote: UnderlyingQuote | None, reason: str | None)`.
  - `SeriesRow(symbol: str, option_type: OptionType, strike: float, exercise_style: ExerciseStyle, bid: float | None, ask: float | None, last: float | None, trades: int, volume: float, implied_vol: float | None, delta: float | None)`.
  - `ExpiryBlock(expiry: date, business_days: int, rows: tuple[SeriesRow, ...])`, ordenado por strike, depois CALL antes de PUT.
  - `ChainView(symbol: str, spot: float, source: DataSource, expiries: tuple[ExpiryBlock, ...], rejected: tuple[RejectedSeries, ...])`.
  - `MarketStatus(source: DataSource, cadastro: CadastroFreshness | None, cotahist_range: tuple[date, date] | None)`.
  - `MarketViewService(market: MarketPort, calendar: TradingCalendar, clock: Clock, valuation_timezone: tzinfo, day_count: DayCountConvention, freshness: Callable[[], CadastroFreshness | None], cotahist_range: Callable[[], tuple[date, date] | None])` com:
    - `follow(watchlist: Sequence[str], chain_symbol: str | None) -> None`, que chama `watch`;
    - `quotes(watchlist: Sequence[str]) -> tuple[WatchRow, ...]`;
    - `chain(symbol: str, expiries: int = VENCIMENTOS_PADRAO) -> ChainView`: IV e delta por série via `series_risk`, com tau BUS/252 pelo calendário; a IV vem do mid só com book completo, como no domínio;
    - `status() -> MarketStatus`.
- Produces: `build_web_app(*, config_dir: Path, static_dir: Path | None, bridge: bool, machine_name: str, clock: Clock | None = None) -> FastAPI`. Monta perfis, biblioteca em `config_dir / "mercado"`, mercado com recuo e os routers das Tasks 4 e 5. A Task 13 acrescenta o router de mercado. Com `bridge=True`, o *lifespan* sobe `BridgeProcess` e o cliente e, ao desligar, encerra os dois e fecha o perfil (solta a trava).

- [ ] **Step 1: Escrever os testes que falham** (ports falsos em memória com uma cadeia de dois vencimentos):
  - blocos por vencimento com `business_days` do calendário;
  - linhas ordenadas;
  - `implied_vol` e `delta` iguais aos de `series_risk` chamado direto (tolerância de auto-consistência da tabela);
  - série com um lado só → `implied_vol is None` e `delta` pela vol do smile;
  - `quotes(["PETR4", "PETR44"])` → linha com cotação e linha com `reason == "ativo desconhecido"`;
  - `build_web_app(..., bridge=False)` responde `/api/saude`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/application/test_market_view.py tests/config/test_composition.py -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 13: API de mercado e WebSocket ao vivo

**Files:**
- Create: `src/options_engine/adapters/inbound/web/market.py`
- Modify: `src/options_engine/config/composition.py` (`build_web_app` inclui `router_mercado`)
- Test: `tests/web/test_market_api.py`

**Interfaces:**
- Consumes: `MarketViewUseCase`, `ProfileUseCase`.
- Produces: `router_mercado(market: MarketViewUseCase, profiles: ProfileUseCase) -> APIRouter`:
  - `GET /api/mercado/status` → `{"fonte", "cadastro": {"data", "dias_uteis", "velho"} | null, "cotahist": {"de", "ate"} | null}`.
  - `GET /api/mercado/cotacoes` → linhas `{"ativo", "ultimo", "compra", "venda", "fechamento_anterior", "variacao_pct", "negocios", "volume", "hora", "fonte", "motivo"}` do perfil ativo.
  - `GET /api/mercado/cadeia/{ativo}?vencimentos=2` → `{"ativo", "spot", "fonte", "vencimentos": [{"data", "dias_uteis", "series": [{"ticker", "tipo", "strike", "estilo", "compra", "venda", "ultimo", "negocios", "volume", "iv", "delta"}]}], "rejeitadas": [{"ticker", "motivo"}]}`.
  - `WS /api/ao-vivo`:
    - ao conectar, o servidor manda `{"tipo": "status", ...}` e `{"tipo": "cotacoes", "dados": [...]}`;
    - a cada 1,0 s, reenvia o que mudou;
    - mensagem do cliente `{"tipo": "cadeia", "ativo": "PETR4", "vencimentos": 2}` passa a incluir `{"tipo": "cadeia", "dados": {...}}`, e `"ativo": null` para;
    - toda mudança de lista ou de cadeia chama `follow`;
    - o cálculo roda em `run_in_threadpool`.
- Números saem crus (sem formatação). A formatação pt-BR é do frontend (decisão nº 8: conversão de exibição só na apresentação).

- [ ] **Step 1: Escrever os testes que falham** (serviço falso):
  - `GET` cotações sem perfil → 404;
  - com perfil, as linhas têm as chaves acima;
  - `GET` cadeia de ativo desconhecido → 404;
  - `client.websocket_connect("/api/ao-vivo")` recebe primeiro `status`, depois `cotacoes`;
  - depois de enviar `cadeia` recebe `{"tipo": "cadeia"}`, e o serviço falso registrou `follow(..., "PETR4")`.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/web/test_market_api.py -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 14: Comando `python -m options_engine app`

**Files:**
- Create: `src/options_engine/adapters/inbound/web/launch.py`
- Modify: `src/options_engine/__main__.py` (subcomando `app [--porta 8765] [--sem-janela] [--sem-ponte]`)
- Test: `tests/web/test_launch.py`, `tests/config/test_smoke.py` (o smoke antigo continua passando)

**Interfaces:**
- Consumes: `build_web_app` (Task 12).
- Produces:
  - `platform_config_dir(system: str, env: Mapping[str, str], home: Path) -> Path` (Global Constraints).
  - `find_free_port(preferred: int) -> int`.
  - `app_window_command(system: str, url: str, which: Callable[[str], str | None], has_flatpak: Callable[[str], bool]) -> tuple[str, ...] | None`.
    - Windows: `("msedge", f"--app={url}")` se `which("msedge")`.
    - Linux, em ordem: `google-chrome`, `chromium`, `brave-browser` com `--app=`; depois `("flatpak", "run", "com.google.Chrome", f"--app={url}")` e `com.brave.Browser`.
    - Senão `None`, e o chamador usa `webbrowser.open`.
  - O subcomando sobe o uvicorn em `127.0.0.1`, abre a janela quando o servidor responde `/api/saude` e serve o frontend de `adapters/inbound/web/static/`. Sem a pasta compilada, mostra "rode `npm --prefix frontend run build`" e sai com código 2, sem traceback.

- [ ] **Step 1: Escrever os testes que falham:**
  - porta preferida livre → ela mesma; ocupada (socket aberto no teste) → outra;
  - comandos de janela para Windows com Edge, Linux com Chrome flatpak e nenhum navegador → `None`;
  - `platform_config_dir("Linux", {"XDG_CONFIG_HOME": "/x"}, Path("/h")) == Path("/x/painel-opcoes")` e o equivalente do Windows com `APPDATA`;
  - `main(["app", "--sem-janela", "--sem-ponte"])` sem a pasta `static` → código 2. A pasta vem de `default_static_dir() -> Path` em `launch.py`, e o teste a substitui com `monkeypatch` por um caminho inexistente, para não depender do build local.
- [ ] **Step 2: Rodar e ver falhar:** `.venv/bin/python -m pytest tests/web/test_launch.py tests/config -q`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Rodar os testes.** Esperado: PASS.
- [ ] **Step 5: Gates.**

---

### Task 15: Frontend — base, tema e formatação

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json` (strict), `frontend/vite.config.ts`, `frontend/index.html` (`lang="pt-BR"`, título "Painel de Opções")
- Create: `frontend/src/main.tsx`, `App.tsx`, `tema.css`, `formatacao.ts`, `formatacao.test.ts`, `componentes/Shell.tsx`, `componentes/Shell.test.tsx`, `paginas/EmBreve.tsx`
- Modify: `.github/workflows/ci.yml` (job `frontend`: Node 22, `npm ci`, `npm run verificar`, `npm run build`)

**Interfaces:**
- Scripts do `package.json`:
  - `dev`;
  - `build` = `vite build --outDir ../src/options_engine/adapters/inbound/web/static --emptyOutDir`;
  - `verificar` = `tsc --noEmit && vitest run`.
- Dependências: `react` ^18.3.1, `react-dom` ^18.3.1, `react-router-dom` ^6.28.0. Dev: `typescript` ^5.6.0, `vite` ^5.4.0, `@vitejs/plugin-react` ^4.3.0, `vitest` ^2.1.0, `@testing-library/react` ^16.0.0, `jsdom` ^25.0.0, `@types/react` ^18.3.0, `@types/react-dom` ^18.3.0.
- Proxy do Vite: `/api` → `http://127.0.0.1:8765`, com `ws: true`.
- Rotas:
  - `/perfis` e `/arquivos`: Task 16;
  - `/mercado`: Task 17;
  - `/montador`, `/book`, `/carteira`, `/alertas` → `EmBreve` ("Chega na semana N", com N = 2, 3, 2 e 4).
- Tema escuro inspirado no home broker (tokens em `tema.css`): fundo `#0f1115`, painel `#171a21`, borda `#262b36`, texto `#e6e8ee`, texto secundário `#9aa3b2`, compra `#1e88e5`, venda `#e53935`, alta `#26a69a`, baixa `#ef5350`, atenção `#f9a825`.
- Produces (`formatacao.ts`): `formatarPreco(v: number | null): string`, `formatarPercentual(v: number | null): string`, `formatarVolume(v: number | null): string`, `formatarInteiro(v: number | null): string`, `formatarData(iso: string): string`.

- [ ] **Step 1: Instalar:** `npm --prefix frontend install`. Esperado: sem erro; `package-lock.json` criado.
- [ ] **Step 2: Escrever os testes que falham**

```ts
test("formatação pt-BR", () => {
  expect(formatarPreco(52.51)).toBe("52,51");
  expect(formatarPreco(null)).toBe("—");
  expect(formatarPercentual(-0.0059)).toBe("-0,59%");
  expect(formatarVolume(679557741)).toBe("679,6 mi");
  expect(formatarInteiro(22704)).toBe("22.704");
  expect(formatarData("2026-11-19")).toBe("19/11/2026");
});
test("menu com as seis áreas", () => {
  render(<MemoryRouter><Shell status={null}><div /></Shell></MemoryRouter>);
  for (const nome of ["Mercado", "Montador", "Book", "Carteira", "Alertas", "Arquivos B3"])
    expect(screen.getByRole("link", { name: nome })).toBeTruthy();
});
```

- [ ] **Step 3: Rodar e ver falhar:** `npm --prefix frontend run verificar`.
- [ ] **Step 4: Implementar** a base, o `Shell` (barra superior com nome do app, perfil ativo e espaço do status; menu lateral) e a formatação com `Intl.NumberFormat("pt-BR")`.
- [ ] **Step 5: Verificar:** `npm --prefix frontend run verificar && npm --prefix frontend run build`. Esperado: PASS, e `src/options_engine/adapters/inbound/web/static/index.html` existe.

---

### Task 16: Frontend — perfis e arquivos da B3

**Files:**
- Create: `frontend/src/api/cliente.ts`, `frontend/src/paginas/Perfis.tsx`, `Perfis.test.tsx`, `frontend/src/paginas/ArquivosB3.tsx`, `ArquivosB3.test.tsx`

**Interfaces:**
- Consumes: endpoints das Tasks 4, 5 e 13 (`/api/mercado/status`).
- Produces (`cliente.ts`): `listarPerfis()`, `criarPerfil(nome, pasta)`, `abrirPerfil(nome, forcar)`, `perfilAtivo()`, `definirAtivos(ativos)`, `listarArquivos()`, `enviarArquivo(arquivo: File)` e `statusMercado()`, com os tipos TypeScript das respostas. Erros HTTP viram `ErroApi { status, erro, mensagem, trava? }`.
- **Perfis:**
  - cartões dos perfis e botão "Novo perfil" com nome e pasta;
  - dica: "Use uma pasta da sua nuvem (Google Drive, OneDrive, Dropbox) para ver a carteira em qualquer PC";
  - 409 com trava abre a confirmação "Este perfil está aberto no PC {pc} desde {hora}. Abrir mesmo assim?" e, se confirmado, `abrirPerfil(nome, true)`;
  - sem perfil ativo, qualquer rota redireciona para `/perfis`.
- **Arquivos B3:**
  - área de arrastar e soltar (e botão) e lista de arquivos com tipo, data e importação;
  - aviso "Cadastro com N dias úteis: séries novas podem estar faltando" quando `velho`;
  - links da B3 para baixar o COTAHIST (séries históricas) e o Cadastro de Instrumentos;
  - erro de upload mostra a `mensagem`.

- [ ] **Step 1: Escrever os testes que falham** (com `fetch` simulado):
  - a lista vem da API;
  - 409 com `trava.pc = "PC-SALA"` mostra o texto com "PC-SALA";
  - `ArquivosB3` mostra "Cadastro com 6 dias úteis" quando o status traz `velho: true, dias_uteis: 6`;
  - upload recusado mostra a mensagem do 422.
- [ ] **Step 2: Rodar e ver falhar:** `npm --prefix frontend run verificar`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Verificar:** `npm --prefix frontend run verificar`. Esperado: PASS.

---

### Task 17: Frontend — Mercado ao vivo

**Files:**
- Create: `frontend/src/api/aoVivo.ts`, `frontend/src/componentes/BarraStatus.tsx`, `BarraStatus.test.tsx`, `frontend/src/componentes/ListaAtivos.tsx`, `ListaAtivos.test.tsx`, `frontend/src/componentes/TabelaCadeia.tsx`, `TabelaCadeia.test.tsx`, `frontend/src/paginas/Mercado.tsx`

**Interfaces:**
- Consumes: `WS /api/ao-vivo` e `PUT /api/perfil/ativos`.
- Produces: `useAoVivo(): { status, cotacoes, cadeia, seguirCadeia(ativo: string | null, vencimentos?: number) }`, que reconecta a cada 2 s.
- **BarraStatus:**
  - `ao_vivo` → "Ao vivo (Tryd)", verde (`--alta`);
  - `atrasado` → "Atrasado", âmbar (`--atencao`);
  - `fim_de_dia` → "Fim de dia (B3)", cinza;
  - mais o aviso do cadastro velho.
- **ListaAtivos:**
  - colunas Ativo, Último, Var%, Compra, Venda, Negócios, Volume, Hora;
  - campo para adicionar ticker e botão de remover, que chamam `definirAtivos`;
  - linha com `motivo` mostra o motivo no lugar dos números;
  - classe `alta`/`baixa` pela variação;
  - clique escolhe o ativo da cadeia.
- **TabelaCadeia:**
  - abas por vencimento, "19/11 (16 du)";
  - colunas espelhadas: CALLS [Compra, Venda, Último, IV, Delta, Neg.] | Strike | PUTS [Neg., Delta, IV, Último, Venda, Compra];
  - lado ausente "—";
  - destaque (classe `no-dinheiro`) na linha do strike mais perto do spot;
  - séries rejeitadas num bloco recolhível com o motivo.

- [ ] **Step 1: Escrever os testes que falham:**
  - um rótulo da `BarraStatus` por fonte;
  - `TabelaCadeia` com `compra: null` mostra "—" e marca `no-dinheiro` na linha de strike 52 com spot 52,51;
  - `ListaAtivos` com `variacao_pct = -0.0059` tem a classe `baixa` e o texto "-0,59%";
  - linha com `motivo: "ativo desconhecido"` mostra o motivo.
- [ ] **Step 2: Rodar e ver falhar:** `npm --prefix frontend run verificar`.
- [ ] **Step 3: Implementar.**
- [ ] **Step 4: Verificar e compilar:** `npm --prefix frontend run verificar && npm --prefix frontend run build`. Esperado: PASS.

---

### Task 18: Verificação ponta a ponta no Linux, arquivo real da B3 e documentação

**Files:**
- Modify: `docs/spikes/tryd-intraday.md` (tabela de resultados: perguntas 1, 3, 5, 6, 9, 10, 11 e 14 com os achados de 2026-10-28; 13 e 12 com o que a Task 8 mediu)
- Modify: `docs/adr/0008-intraday-tryd-rtd.md` e `docs/adr/README.md`: status **"Aceita (2026-10-28), com as correções do spike"**, a decisão do usuário no questionário. Corrigir ProgID, tópico, campos e "só Windows" (funciona no Linux via Wine).
- Modify: `docs/adr/0006-fontes-de-dados-de-opcoes.md`: status ganha "decisão 3 emendada pela ADR-0008".
- Modify: `docs/ROADMAP.md`: status no topo e a fase "App" (spec e este plano) no lugar da Sprint 4, que passa a ser só a API do app.
- Modify: `README.md`: seção "App" (instalar `.[app]`, `npm --prefix frontend run build`, `python -m options_engine app`, ponte no Linux via `scripts/linux/preparar_ponte_wine.sh`).

- [ ] **Step 1: Compilar e subir:** `npm --prefix frontend run build && .venv/bin/python -m options_engine app`, com o Tryd aberto e logado. Esperado: a janela do app abre em `http://127.0.0.1:8765`.
- [ ] **Step 2: Fluxo real**, conferido pela API com `curl` e pelo autor na tela:
  - criar o perfil do autor numa pasta própria;
  - lista PETR4 e VALE3 com status "Ao vivo (Tryd)";
  - cadeia de PETR4 com bid/ask batendo com a tela do Tryd;
  - fechar o Tryd → "Atrasado" em até 10 s e "Fim de dia (B3)" em até 30 s, com os números do último COTAHIST importado.
- [ ] **Step 3: Arquivo real da B3.** Pedir ao autor o COTAHIST (anual de 2026 e o diário do último pregão) e o Cadastro de Instrumentos do mesmo pregão, baixados no site da B3. Importar pela tela e conferir as premissas do HANDOFF da S5:
  - o TOTREG do trailer;
  - os valores de `OptnStyle`, `OptnTp`, `ExrcPric` e `XprtnDt` (Task 6);
  - o ESPECI das opções;
  - o `PREEXE` contra o `PEX` do Tryd em 3 séries (por exemplo PETRK500: `PEX` 48,91 em 2026-10-28).
  - Premissa errada vira task de correção antes de fechar a semana.
- [ ] **Step 4: Atualizar a documentação** listada em **Files**.
- [ ] **Step 5: Gates completos**, Python e frontend, e o oráculo scipy se alguma task tocou o kernel (não deve). Esperado: todos verdes. Reportar ao autor a saída e o que ficou pendente.

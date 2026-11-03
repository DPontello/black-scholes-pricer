# Semana 4, parte 1: instalador — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** instalador `.exe` do Windows gerado pelo GitHub Actions (app de 64 bits + ponte do Tryd de 32 bits, PyInstaller `onedir` + Inno Setup, sem administrador) e script de instalação do Linux, com o app achando a tela, a ponte e o log quando roda empacotado, e abrindo só a janela quando já está rodando.

**Spec:** [`docs/superpowers/specs/2026-11-03-semana-4-instalador-ir-alertas-design.md`](../specs/2026-11-03-semana-4-instalador-ir-alertas-design.md), §2.

## Global Constraints

- O núcleo segue sem dependências: PyInstaller e pywin32 só em `packaging/windows/requirements-build.txt`; nada novo no `pyproject.toml`.
- Comentário só para um porquê não óbvio; português simples nas mensagens ao usuário.
- **Quem constrói não commita sem perguntar ao autor** (HANDOFF §4); uma tarefa por vez, com entrada no ledger da semana 4 (`docs/superpowers/ledger-semana-4.md`) e a pergunta "commito e sigo?".
- Branch `feat/instalador`, a partir da `development`.
- O comportamento fora do executável não muda: `python -m options_engine app` segue igual no Windows e no Linux.

## Review Focus

1. **Executável sem `python` no PATH:** a ponte sobe pelo `PonteTryd.exe` ao lado do app (Task 1).
2. **Metadados no executável:** `importlib.metadata.version("options-engine")` (no `GET /api/saude`) funciona empacotado (`--copy-metadata`, Task 3).
3. **Segundo clique no atalho** não sobe outro servidor nem disputa a trava do perfil (Task 2).
4. **Atualizar por cima** não apaga `%APPDATA%\PainelOpcoes` nem a pasta do perfil (Task 4).

---

### Task 1: caminhos do app empacotado (ponte, tela e log)

**Files:**
- Modify: `src/options_engine/adapters/outbound/tryd/launcher.py` (`default_bridge_command`), `src/options_engine/adapters/inbound/web/launch.py` (`default_static_dir`, log), `src/options_engine/__main__.py` (ligar o log no comando `app`)
- Test: `tests/adapters/outbound/tryd/test_launcher.py`, `tests/web/test_launch.py`

- [ ] **Step 1: Testes que falham**
  - `default_bridge_command("Windows", ..., frozen_dir=Path("C:/App"))` → `("C:/App/ponte/PonteTryd.exe", "servir", "--porta", "8766")` com `cwd` `C:/App/ponte`; sem `frozen_dir`, o comando de hoje (Windows e Linux).
  - `default_static_dir(meipass=Path(...))` → `<meipass>/static`; sem `meipass`, o caminho de hoje.
  - `log_file(config_dir)` → `<config_dir>/logs/app.log`, com a pasta criada.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** O executável é detectado por `getattr(sys, "frozen", False)` e `sys._MEIPASS` só na borda (`__main__.py`), que passa os caminhos como parâmetro; as funções seguem puras. Empacotado, o log vai para um `RotatingFileHandler` (5 MB, 3 arquivos).
- [ ] **Step 4: Rodar e ver passar** (suítes tocadas, mypy, ruff, format, import-linter).

### Task 2: "já está aberto" só abre a janela

**Files:**
- Modify: `src/options_engine/adapters/inbound/web/app.py` (`GET /api/saude` ganha `"app": "painel-de-opcoes"`), `src/options_engine/adapters/inbound/web/launch.py`, `src/options_engine/__main__.py`
- Test: `tests/web/test_launch.py`, `tests/web/test_app.py`

- [ ] **Step 1: Testes que falham**
  - `already_running(port, fetch)`: `True` quando a porta responde ao `/api/saude` com `"app": "painel-de-opcoes"`; `False` sem resposta, com outro serviço na porta ou com JSON sem o campo.
  - O comando `app` com o app já rodando na porta padrão abre a janela nessa porta, não sobe servidor e devolve 0 (com `fetch` e `open_window` falsos).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** com `urllib.request` e prazo de 1 s. Só a porta padrão é consultada (a escolhida em `--porta`, senão 8765).
- [ ] **Step 4: Rodar e ver passar.**

### Task 3: executáveis com PyInstaller

**Files:**
- Create: `packaging/windows/painel.py`, `packaging/windows/ponte.py` (pontos de entrada), `packaging/windows/painel.spec`, `packaging/windows/ponte.spec`, `packaging/windows/requirements-build.txt` (PyInstaller e pywin32 com versão exata), `packaging/windows/README.md`
- Test: `tests/packaging/test_entradas.py` (os pontos de entrada chamam `main` com os argumentos certos, sem PyInstaller)

- [ ] **Step 1: Testes que falham** — `painel.main([])` chama `options_engine.__main__.main(["app"])`; `ponte.main(["servir", "--porta", "8766"])` repassa os argumentos a `options_ponte.__main__.main`.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** `painel.spec`: `onedir`, `console=False`, `datas` com `src/options_engine/adapters/inbound/web/static` em `static` e os dados do pacote (calendário de feriados, tabela de custos), `copy_metadata("options-engine")`, `hiddenimports` do uvicorn. `ponte.spec`: `onedir`, `console=False`, `pywin32` com `pythoncom`/`pywintypes`. Os dois com o ícone do app.
- [ ] **Step 4: Rodar e ver passar.** O build de verdade é conferido na Task 5 (no Linux o PyInstaller não gera `.exe`).

### Task 4: Inno Setup

**Files:**
- Create: `packaging/windows/PainelOpcoes.iss`, `packaging/windows/versao.py` (lê a versão do `pyproject.toml` para o build)
- Test: `tests/packaging/test_versao.py`

- [ ] **Step 1: Teste que falha** — `versao.py` devolve a versão do `pyproject.toml` no formato do Inno Setup (`0.5.0.dev0` → `0.5.0`).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** `PrivilegesRequired=lowest`, `DefaultDirName={localappdata}\Programs\PainelOpcoes`, `AppId` fixo (GUID gerado uma vez), atalhos na área de trabalho e no menu Iniciar para `PainelOpcoes.exe`, `[UninstallDelete]` só na pasta do programa (nunca em `{userappdata}`), e "fechar o app antes de atualizar" (`CloseApplications=yes`).
- [ ] **Step 4: Rodar e ver passar.**

### Task 5: job do GitHub Actions

**Files:**
- Create: `.github/workflows/instalador.yml`

- [ ] **Step 1:** `on: workflow_dispatch` e `push: tags: ["v*"]`; `runs-on: windows-latest`. Passos: checkout; Node 22 e `npm --prefix frontend ci && npm --prefix frontend run build`; Python 3.12 **x64**, `pip install . [app]` e o `requirements-build.txt`, `pyinstaller packaging/windows/painel.spec`; Python 3.12 **x86**, `pip install` do `requirements-build.txt`, `pyinstaller packaging/windows/ponte.spec`; fumaça; `iscc`; `actions/upload-artifact` do `PainelOpcoes-<versão>-setup.exe`.
- [ ] **Step 2: Fumaça.** `PainelOpcoes.exe app --sem-janela --sem-ponte --porta 8799` em segundo plano e `GET /api/saude` com `"app": "painel-de-opcoes"` e `GET /` com o `index.html`; `PonteTryd.exe autoteste` com `AUTOTESTE OK`. Se o autoteste não rodar no runner (registro COM), o passo sai e vira item manual da Task 7, no ledger.
- [ ] **Step 3:** rodar o workflow na branch (`workflow_dispatch`) e baixar o artefato. Pedir ao autor antes do push que dispara o job.

### Task 6: instalação no Linux

**Files:**
- Create: `scripts/linux/instalar.sh`, `scripts/linux/painel-opcoes.desktop.in`
- Test: `tests/scripts/test_instalar_sh.py` (com `--simular`: imprime o que faria, sem instalar)

- [ ] **Step 1: Teste que falha** — `instalar.sh --simular` lista: venv em `~/.local/share/painel-opcoes/venv`, `pip install "<repo>[app]"`, build da tela, o `.desktop` em `~/.local/share/applications/` com `Exec` apontando para o Python do venv e `app`; sai com erro claro sem `node` ou sem Python 3.12+.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** (`set -euo pipefail`, sem `sudo`); lembra o `preparar_ponte_wine.sh --verificar` no fim.
- [ ] **Step 4: Rodar e ver passar.**

### Task 7: conferência e documentação (controlador)

- [ ] **Step 1:** gate completo (pytest com cobertura, mypy, ruff, ruff format, import-linter, `verificar`, `build`).
- [ ] **Step 2:** com o autor, num PC Windows: o roteiro do §2.4 item 2 do spec, mais `PonteTryd.exe diagnostico` com o Tryd aberto (que type library usou).
- [ ] **Step 3:** no Linux deste PC: `instalar.sh` do zero e o atalho do menu.
- [ ] **Step 4:** README (instalar, SmartScreen, atualizar, desinstalar), ROADMAP e HANDOFF.

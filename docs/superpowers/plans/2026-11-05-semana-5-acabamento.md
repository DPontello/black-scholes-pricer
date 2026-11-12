# Semana 5: acabamento para o teste com a mãe (plano)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** tirar do caminho "montar e registrar uma operação" o que trava uma pessoa leiga. A
semana também dá ao app o ícone e entrega o roteiro do teste com a mãe do autor.

**Architecture:** quase tudo é frontend (React/TypeScript) e empacotamento:

- o ícone vem de um SVG versionado, com os derivados gerados no repositório;
- a única peça nova no backend é o seletor de pasta nativo. Ele é um adaptador de entrada, ao
  lado do `launch.py`, que roda `kdialog`/`zenity` no Linux ou o PowerShell no Windows e responde
  numa rota do router de perfis.

Nenhum cálculo muda.

**Tech Stack:**

- Python 3.12, FastAPI e pytest;
- React 18, Vite e Vitest (jsdom);
- ImageMagick 7 com librsvg, só para regerar o ícone;
- PyInstaller e Inno Setup (Windows), Bash (Linux).

**Spec:** [`docs/superpowers/specs/2026-11-05-semana-5-acabamento-design.md`](../specs/2026-11-05-semana-5-acabamento-design.md)

## Global Constraints

- **Commit:** quem constrói **não commita nem dá push**; o autor commita. Este plano não tem
  passo de commit.
- **Arquitetura e gates:** domínio e aplicação só com a stdlib (import-linter). Os gates são:
  - cobertura ≥ 95% com `--cov`;
  - mypy strict;
  - ruff (`check` e `format --check`);
  - `npm --prefix frontend run verificar` e `run build`.
- **Estilo:** textos da tela em português do Brasil, no tom dos que já existem. Comentário só
  para um porquê não óbvio. Seguir o estilo do arquivo em volta.
- **Nenhum número muda:** cálculo, preço, IR e alertas ficam como estão.
- **Montador:** o "+" da cadeia não rola a tela.
- **Dados reais:** nunca gravar nos perfis reais (`~/.config/painel-opcoes` e as pastas deles);
  conferências só em pasta temporária.
- **Comandos:** rodar da raiz do worktree
  `/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer-dev`, com
  `PY=/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin/python` e
  `PYTHONPATH=src`.
- **Checagens por tarefa:** só as rápidas (ruff, mypy, lint-imports e as suítes tocadas). O gate
  inteiro roda no fim (Task 6).

## Review Focus

1. **Caminho com acento e espaço** vindo do seletor (`C:\Users\Mãe\OneDrive\Painel de Opções`
   com `\r\n` no fim): tem que voltar inteiro, só sem a quebra de linha. Teste na Task 4.
2. **Dois cliques em "Escolher pasta…"** abririam duas janelas: o botão fica desabilitado
   enquanto espera. Teste na Task 4.
3. **Cancelar o seletor** com algo já digitado no campo: o texto fica. Teste na Task 4.
4. **`1.000` num campo de stop** vira 1000, e `1.30` continua 1,30. Os dois estão na tabela de
   casos da Task 2.
5. **Simulação salva de outro ativo:** o Montador troca o ativo e só depois põe as pernas. A
   rolagem tem que acontecer nesse caminho também. Teste na Task 3.

---

### Task 1: Ícone do app

**Files:**
- Create:
  - `packaging/icone/painel-opcoes.svg` (conteúdo exato no desenho, §5.A)
  - `scripts/gerar_icone.sh`
  - os gerados `packaging/icone/painel-opcoes.ico`, `packaging/icone/painel-opcoes-256.png`,
    `frontend/public/favicon.svg` e `frontend/public/icone-192.png`
  - `tests/packaging/test_icone.py`
- Modify:
  - `frontend/index.html`
  - `packaging/windows/painel.spec` e `packaging/windows/ponte.spec`
  - `packaging/windows/PainelOpcoes.iss`
  - `scripts/linux/instalar.sh` e `scripts/linux/painel-opcoes.desktop.in`
  - `tests/packaging/test_instalador.py` e `tests/scripts/test_instalar_sh.py`

**Interfaces:**
- Produces: os arquivos acima. Nenhuma outra tarefa depende deles.

- [ ] **Step 1: Write the failing tests** em `tests/packaging/test_icone.py`. Leia o cabeçalho
  ICO (6 bytes `<HHH>` e entradas de 16 bytes, em que largura 0 quer dizer 256) e o IHDR do PNG
  (largura e altura `>II` nos bytes 16–24) com `struct`.
  - `test_favicon_e_copia_do_svg`: os bytes de `frontend/public/favicon.svg` são iguais aos de
    `packaging/icone/painel-opcoes.svg`.
  - `test_ico_tem_os_sete_tamanhos`: o tipo é 1, e o conjunto das larguras (igual ao das
    alturas) é `{16, 24, 32, 48, 64, 128, 256}`.
  - `test_pngs_tem_o_tamanho_do_nome`: `painel-opcoes-256.png` tem 256×256, e `icone-192.png`
    tem 192×192.
  - `test_index_liga_os_dois_icones`: o `frontend/index.html` tem
    `<link rel="icon" type="image/svg+xml" href="/favicon.svg" />` e
    `<link rel="icon" type="image/png" sizes="192x192" href="/icone-192.png" />`.
  - `test_executaveis_usam_o_ico`: `painel.spec` e `ponte.spec` passam
    `icon=str(RAIZ / "packaging" / "icone" / "painel-opcoes.ico")` ao `EXE`. Se o `ponte.spec`
    não tiver `RAIZ`, use o caminho equivalente dele.

  Em `tests/packaging/test_instalador.py`, `test_instalador_tem_o_icone`:
  `_diretiva("SetupIconFile") == r"..\icone\painel-opcoes.ico"`.

  Em `tests/scripts/test_instalar_sh.py`:
  - `test_modelo_do_atalho` passa a exigir a linha `Icon=painel-opcoes`;
  - `test_simular_mostra_o_icone`: a saída cita os dois destinos,
    `<DIR_ICONES>/hicolor/scalable/apps/painel-opcoes.svg` e
    `<DIR_ICONES>/hicolor/256x256/apps/painel-opcoes.png`, e nada é gravado;
  - na instalação de verdade (`test_instala_de_verdade_…`): os dois arquivos existem em
    `~/.local/share/icons/hicolor/...` do home temporário e são iguais aos de
    `packaging/icone/`.

- [ ] **Step 2: Run them to verify they fail**

  Run: `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider tests/packaging tests/scripts`

  Expected: FAIL, por arquivos inexistentes, diretiva ausente e linha `Icon=` ausente.

- [ ] **Step 3: Create the SVG and `scripts/gerar_icone.sh`.** O script deve:
  - começar com `set -euo pipefail` e se achar pela própria pasta, como o `instalar.sh`;
  - exigir `magick` e sair com mensagem em português se ele não existir;
  - gerar cada PNG direto do SVG, com
    `magick -background none -density 384 <svg> -resize NxN <png>`, para 16, 24, 32, 48, 64, 128
    e 256 (numa pasta temporária) e para 192;
  - montar o `.ico` a partir dos sete PNGs (`magick p16.png … p256.png painel-opcoes.ico`);
  - copiar o de 256 para `packaging/icone/painel-opcoes-256.png`, o de 192 para
    `frontend/public/icone-192.png` e o SVG para `frontend/public/favicon.svg`.

  O cabeçalho em comentário diz que é ferramenta de quem mexe no ícone: precisa do ImageMagick 7
  com librsvg, e o CI não roda.

  Rode o script e confira que os quatro arquivos foram gerados.

- [ ] **Step 4: Wire it up.**
  - **`index.html`:** as duas tags `<link>` acima, depois do `<title>`.
  - **Os dois `.spec`:** `icon=` no `EXE`.
  - **`.iss`:** `SetupIconFile=..\icone\painel-opcoes.ico` no `[Setup]`, com um comentário
    curto: é relativo à pasta do `.iss`.
  - **`.desktop.in`:** `Icon=painel-opcoes` depois do `Comment=`.
  - **`instalar.sh`:**
    - a variável `DIR_ICONES="${DIR_ICONES:-$HOME/.local/share/icons}"`, citada no comentário
      "Variáveis:" (ajuste o intervalo do `uso()` se o cabeçalho crescer);
    - uma função `instalar_icone` que cria as duas pastas `hicolor/.../apps` e copia o SVG e o
      PNG pelo `executar`, para o `--simular` mostrar os comandos;
    - no roteiro, uma linha `info "Ícone: $DIR_ICONES/hicolor"` antes do atalho.

- [ ] **Step 5: Run the tests to verify they pass**

  Run: `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider tests/packaging tests/scripts`

  Expected: PASS. Também `npm --prefix frontend run build`: `favicon.svg` e `icone-192.png`
  aparecem em `src/options_engine/adapters/inbound/web/static/`.

---

### Task 2: Campos de preço tolerantes e mensagens

**Files:**
- Modify:
  - `frontend/src/componentes/CampoPreco.tsx` (só `numero`)
  - `frontend/src/paginas/Book.tsx:86`
  - `src/options_engine/adapters/outbound/b3files/loaded.py:64`
- Create: `frontend/src/componentes/CampoPreco.test.ts`
- Test:
  - `frontend/src/paginas/Book.test.tsx`
  - `tests/adapters/b3files/test_loaded.py:51`
  - e qualquer teste que fixe o texto antigo da série (`grep -rn "série desconhecida no
    cadastro" tests frontend/src`; só os que vêm de `option_terms`)

**Interfaces:**
- Produces: `numero(texto: string): number | null`, com a mesma assinatura e a leitura nova.

- [ ] **Step 1: Write the failing tests**

  - **`CampoPreco.test.ts`:** um `test.each` com a tabela do desenho, §5.D. Espaço que não
    quebra é `"\u00a0"`. Compare com `toBeCloseTo` quando for fração.
    - `"1,30"`, `"1.30"`, `" 1,30 "`, `"R$ 1,30"`, `"R$1,30"`, `"r$ 1,30"`, `"1,30\u00a0"`
      dão 1.3;
    - `"1.000,50"` e `"R$ 1.000,50"` dão 1000.5;
    - `"1.000"` dá 1000, e `"12.500"` dá 12500;
    - `"-1,30"` dá -1.3;
    - `"0,5"` e `",5"` dão 0.5;
    - `""`, `"   "`, `"abc"`, `"1,3x"`, `"1,2,3"`, `"1.2.3"` e `"R$"` dão `null`.
  - **`Book.test.tsx`:** enquanto o book não chega, o texto é "Varrendo o fim de dia… Na
    primeira vez depois de um arquivo novo da B3, pode levar alguns minutos.".
  - **`test_loaded.py`:**
    `loaded.option_terms("VALEK600", "VALE3") == "VALEK600: série não encontrada no Cadastro da B3. Confira o código na nota da corretora; se a série for nova, importe o Cadastro mais recente em Arquivos B3."`

- [ ] **Step 2: Run them to verify they fail**

  Run:
  - `npm --prefix frontend exec vitest run src/componentes/CampoPreco.test.ts src/paginas/Book.test.tsx`
  - `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider tests/adapters/b3files/test_loaded.py`

  Expected: FAIL, porque "R$", milhar e os textos ainda são os antigos.

- [ ] **Step 3: Implement.**

  `numero()` funciona assim:
  1. Tira os espaços (inclusive `\u00a0`) e um `R$` do começo, sem diferenciar maiúscula de
     minúscula.
  2. Exige o casamento inteiro com um destes formatos:
     - `^-?\d*,\d+$` ou `^-?\d+$`: vírgula decimal;
     - `^-?\d{1,3}(\.\d{3})+(,\d+)?$`: ponto de milhar;
     - `^-?\d*\.\d+$`: ponto decimal.
  3. Tira os pontos de milhar, troca a vírgula por ponto e converte.

  Os textos do Book e do `loaded.py` são os do Step 1. As outras "série desconhecida no
  cadastro" (feed do Tryd e fim de dia) não mudam.

- [ ] **Step 4: Run the tests to verify they pass.** São os mesmos comandos do Step 2, mais
  `npm --prefix frontend run verificar` e
  `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider tests/web tests/adapters/b3files`.

  Expected: PASS.

---

### Task 3: Montador rola até a montagem

**Files:**
- Modify: `frontend/src/paginas/Montador.tsx`
- Test: `frontend/src/paginas/Montador.test.tsx`

**Interfaces:**
- Consumes: nada das outras tarefas.

- [ ] **Step 1: Write the failing tests** em `Montador.test.tsx`.

  Em cada teste:
  - substitua `Element.prototype.scrollIntoView` por um `vi.fn()`, restaurando no fim;
  - finja a posição com
    `vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({ top, … } as DOMRect)`,
    com top de 1400 (abaixo) ou 200 (à vista). O `window.innerHeight` do jsdom é 768.

  Os testes:
  - `"o modelo pronto rola a tela até a montagem quando ela está abaixo da cadeia"`: depois do
    `change` do Modelo pronto e da sugestão, o `scrollIntoView` foi chamado uma vez com
    `{ behavior: "smooth", block: "start" }`. O elemento (`mock.contexts[0]`) tem a classe
    `montador-resultado`.
  - `"o pedido que vem do book rola até a montagem"`: o render com `state: { pedido: SUGESTAO }`
    chama o `scrollIntoView` uma vez.
  - `"o + da cadeia não rola a tela"`: depois do clique em "Pôr PETRK541 no montador" e da
    análise, o `scrollIntoView` não foi chamado.
  - `"com a montagem à vista, o modelo pronto não rola"`: com top 200, não foi chamado.
  - `"abrir uma simulação salva de outro ativo rola depois de trocar o ativo"`: a lista de
    simulações traz uma de VALE3. O teste clica nela e espera a análise de VALE3; o
    `scrollIntoView` foi chamado uma vez. Use o `api()` do arquivo, estendido para devolver essa
    simulação.

- [ ] **Step 2: Run them to verify they fail**

  Run: `npm --prefix frontend exec vitest run src/paginas/Montador.test.tsx`

  Expected: FAIL, porque o `scrollIntoView` nunca é chamado.

- [ ] **Step 3: Implement in `Montador.tsx`.**
  - Uma `useRef<HTMLDivElement>` na `div.montador-resultado`.
  - Um contador `chegadas`. Ele começa em 1 quando `doBook !== null`, senão em 0, e cresce:
    - quando a sugestão do Modelo pronto chega (em `escolherModelo`, o que também cobre o
      `?modelo=`);
    - quando `abrir(simulacao)` põe o pedido, do mesmo ativo ou, no efeito de `[ativo]`, quando
      havia um `pendente`.
  - Um `useEffect` em `[chegadas]`. Com `chegadas > 0`, ele mede `getBoundingClientRect().top`
    da `ref` e chama `scrollIntoView({ behavior: "smooth", block: "start" })` só quando
    `top > window.innerHeight / 2`.
  - Comentário de uma linha com o porquê: abaixo de 1780 px o resultado fica sob a cadeia, e o
    clique pareceria não fazer nada.
  - `porSerie` e a `TabelaPernas` não mexem no contador.

- [ ] **Step 4: Run the tests to verify they pass**

  Run:
  - `npm --prefix frontend exec vitest run src/paginas/Montador.test.tsx`
  - `npm --prefix frontend run verificar`

  Expected: PASS.

---

### Task 4: "Escolher pasta…" no perfil novo

**Files:**
- Create:
  - `src/options_engine/adapters/inbound/web/folder_picker.py`
  - `tests/web/test_folder_picker.py`
- Modify:
  - `src/options_engine/adapters/inbound/web/profiles.py` (`router_perfis`)
  - `src/options_engine/config/web_app.py:201`
  - `frontend/src/api/cliente.ts`
  - `frontend/src/paginas/Perfis.tsx`
  - `frontend/src/aprender/Comece.tsx:12`
- Test:
  - `tests/web/test_profiles_api.py`
  - `frontend/src/paginas/Perfis.test.tsx`
  - os testes do Aprender que fixem o texto do passo 1

**Interfaces:**
- Produces:
  - `FolderPicker = Callable[[], str | None]`;
  - `PICK_TIMEOUT_S = 600.0`;
  - `WINDOWS_SCRIPT: str` (abaixo);
  - `PICK_TITLE = "Escolha a pasta do perfil"`;
  - `folder_picker_command(system: str, which: Callable[[str], str | None], home: Path) -> tuple[str, ...] | None`;
  - `pick_folder(command: Sequence[str], run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run, timeout_s: float = PICK_TIMEOUT_S) -> str | None`;
  - `folder_picker(system: str, which: Callable[[str], str | None], home: Path) -> FolderPicker | None`;
  - `router_perfis(service: ProfileUseCase, escolher_pasta: FolderPicker | None = None) -> APIRouter`;
  - no frontend, `escolherPasta(): Promise<string | null>` em `api/cliente.ts`.

- [ ] **Step 1: Write the failing backend tests**

  **`tests/web/test_folder_picker.py`** (com `which` falso, `Path("/home/maria")` e `run`
  falso que grava os argumentos):

  `folder_picker_command`:

  | Situação | Resultado |
  |---|---|
  | `"Linux"` com `kdialog` | `("/usr/bin/kdialog", "--title", PICK_TITLE, "--getexistingdirectory", "/home/maria")` |
  | `"Linux"` só com `zenity` | `("/usr/bin/zenity", "--file-selection", "--directory", f"--title={PICK_TITLE}", "--filename=/home/maria/")` |
  | `"Linux"` com os dois | o do `kdialog` |
  | `"Linux"` sem nenhum | `None` |
  | `"Windows"` com `powershell` | `(<ps>, "-NoProfile", "-NonInteractive", "-STA", "-Command", WINDOWS_SCRIPT)` |
  | `"Windows"` sem `powershell` | `None` |
  | `"Darwin"` | `None` |

  `pick_folder`:
  - `pick_folder_devolve_o_caminho_inteiro`: com stdout
    `"C:\\Users\\Mãe\\OneDrive\\Painel de Opções\r\n"` e código 0, devolve
    `"C:\\Users\\Mãe\\OneDrive\\Painel de Opções"`;
  - código 1, com ou sem saída, dá `None`; código 0 com stdout vazio também;
  - um `run` que levanta `subprocess.TimeoutExpired` ou `OSError` dá `None`;
  - o `run` recebe `timeout=600.0`, `capture_output=True`, `text=True`, `encoding="utf-8"` e
    `stdin=subprocess.DEVNULL`.

  `folder_picker`:
  - devolve `None` sem comando;
  - com comando, devolve uma função. Para testar, injete o `run` via `monkeypatch` em
    `pick_folder` ou num parâmetro, como preferir.

  **`tests/web/test_profiles_api.py`:**
  - `test_escolher_pasta_devolve_o_caminho`: com
    `router_perfis(servico, lambda: "/nuvem/Mãe")`, o `POST /api/perfis/escolher-pasta` dá 200 e
    `{"pasta": "/nuvem/Mãe"}`;
  - `test_escolher_pasta_cancelada`: com `lambda: None`, dá 200 e `{"pasta": None}`;
  - `test_sem_seletor_de_pasta`: com `router_perfis(servico)`, dá 501 e
    `{"erro": "SemSeletorDePasta", "mensagem": "Este PC não tem como abrir a escolha de pasta. Digite o caminho completo da pasta."}`.

- [ ] **Step 2: Run them to verify they fail**

  Run: `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider tests/web/test_folder_picker.py tests/web/test_profiles_api.py`

  Expected: FAIL, porque o módulo e a rota não existem.

- [ ] **Step 3: Implement the backend.**

  `pick_folder`:
  - chama o `run` com `check=False` e
    `creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)`, para não abrir console no
    Windows;
  - tira só `"\r\n"` do fim da saída;
  - devolve `None` se o código não for 0 ou a saída vier vazia.

  A rota é `@router.post("/perfis/escolher-pasta")`, síncrona (roda no threadpool). Sem
  seletor, ela devolve `JSONResponse(status_code=501, content=…)` com o corpo exato do teste.

  No `web_app.py`:
  `router_perfis(profiles, folder_picker(platform.system(), shutil.which, Path.home()))`.

  `WINDOWS_SCRIPT` tem este texto exato, numa linha por comando unida com `"; "` ou com quebras
  de linha:

  ```powershell
  Add-Type -AssemblyName System.Windows.Forms
  [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
  $dono = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true; ShowInTaskbar = $false }
  $janela = New-Object System.Windows.Forms.FolderBrowserDialog
  $janela.Description = 'Escolha a pasta do perfil (pode ser uma pasta da nuvem ou de um pendrive)'
  $janela.ShowNewFolderButton = $true
  if ($janela.ShowDialog($dono) -eq [System.Windows.Forms.DialogResult]::OK) { [Console]::Out.Write($janela.SelectedPath) }
  ```

  A docstring do módulo diz três coisas:
  - o servidor é local, por isso é ele quem abre a janela;
  - o navegador não entrega o caminho da pasta;
  - no Windows, a janela ainda precisa ser conferida no PC do autor.

- [ ] **Step 4: Run the backend tests to verify they pass**

  Run:
  - `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider tests/web tests/config`
  - `$PY -m mypy`
  - `$PY -m ruff check .`
  - `$PY -m ruff format --check .`
  - `/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin/lint-imports --no-cache`

  Expected: PASS.

- [ ] **Step 5: Write the failing frontend tests** em `Perfis.test.tsx`, no padrão do arquivo
  (`simularFetch`). Antes de cada clique, abra o formulário em "Novo perfil".
  - `"Escolher pasta… põe o caminho escolhido no campo"`: com
    `POST /api/perfis/escolher-pasta` → `{ pasta: "/nuvem/Mãe" }`, o campo "Pasta de dados"
    fica com `/nuvem/Mãe`.
  - `"cancelar a escolha deixa o que já estava digitado"`: com o campo em `/tmp/x` e a resposta
    `{ pasta: null }`, o campo continua `/tmp/x`.
  - `"o botão fica desabilitado enquanto a janela de escolha está aberta"`: com uma promessa que
    só resolve no fim do teste, o botão está `disabled` logo após o clique e volta habilitado
    quando ela resolve.
  - `"sem seletor neste PC, a mensagem aparece"`: o 501 com o corpo da Task 4 põe a mensagem no
    `role="alert"`.
  - O texto de ajuda: "Em "Escolher pasta…", use uma pasta da sua nuvem (Google Drive, OneDrive,
    Dropbox) para ver a carteira em qualquer PC.".

- [ ] **Step 6: Run them to verify they fail**

  Run: `npm --prefix frontend exec vitest run src/paginas/Perfis.test.tsx`

  Expected: FAIL, porque não há o botão "Escolher pasta…".

- [ ] **Step 7: Implement the frontend.**
  - **`escolherPasta()`:** `pedir<{ pasta: string | null }>("/api/perfis/escolher-pasta", json("POST", {}))`,
    devolvendo o `.pasta`.
  - **Em `Perfis.tsx`:**
    - o botão `type="button"` "Escolher pasta…" logo depois do `label` da pasta, `disabled`
      enquanto espera;
    - o resultado não nulo vai para `setPasta`, e o erro vai para o `setErro(mensagemDe(e))`;
    - o texto de ajuda é o do Step 5.
  - **Em `Comece.tsx`,** o passo 1 fica: "Na tela de perfis, crie o seu perfil com um nome e, em
    "Escolher pasta…", escolha a pasta onde ficam a sua carteira e as simulações (pode ser uma
    pasta na nuvem ou num pendrive). Cada pessoa usa o próprio perfil, com a própria carteira."

  Ajuste os testes do Aprender que fixam o texto antigo.

- [ ] **Step 8: Run the frontend tests to verify they pass**

  Run:
  - `npm --prefix frontend exec vitest run src/paginas/Perfis.test.tsx src/aprender`
  - `npm --prefix frontend run verificar`

  Expected: PASS.

---

### Task 5: Roteiro do teste com a mãe (eu, sessão principal)

**Files:**
- Create: `docs/teste-usabilidade.md`

- [ ] **Step 1: Escrever o roteiro** com as seções do desenho, §5.F: preparação, regras do
  observador, as cinco tarefas, o critério 9, a ficha e o "depois do teste". Além delas:
  - **o modelo da nota fictícia:** ativo, série, lado, quantidade, preço e data, em branco para
    o autor preencher no dia, porque as séries mudam toda semana;
  - **o `config.json` de cada sistema:** `%APPDATA%\PainelOpcoes\config.json` e
    `~/.config/painel-opcoes/config.json`, com o trecho do perfil Teste a apagar com o app
    fechado;
  - **o texto para colar no Claude Code** com a ficha preenchida.
- [ ] **Step 2: Conferir** que cada tarefa cita os nomes dos botões e das abas exatamente como
  estão na tela: "Novo perfil", "Escolher pasta…", "Modelo pronto", "Abrir no montador",
  "Registrar como executada", "Registrar", "Abertas", "Comece aqui", "Operações".

---

### Task 6: Documentação de fechamento e conferência (eu, sessão principal)

**Files:**
- Create: `docs/superpowers/ledger-semana-5.md`
- Modify:
  - `README.md`
  - `docs/ROADMAP.md`
  - `docs/superpowers/HANDOFF-2026-11-02.md` (§1, §8 e a §11 nova)

- [ ] **Step 1: Gate inteiro**

  Run, um por vez:
  - `PYTHONPATH=src $PY -m pytest -q -p no:cacheprovider --cov`
  - `$PY -m mypy`
  - `$PY -m ruff check .`
  - `$PY -m ruff format --check .`
  - `lint-imports --no-cache`
  - `npm --prefix frontend run verificar`
  - `npm --prefix frontend run build`

  Expected: todos verdes, cobertura ≥ 95%. Anote as contagens.
- [ ] **Step 2: Conferência no app isolado** (HOME temporário, arquivos da B3 de 30/10 copiados,
  `--sem-janela --sem-ponte`, Chrome headless pelo CDP):
  - `GET /favicon.svg` dá 200;
  - o Modelo pronto e o "Abrir no montador" deixam o `scrollY` > 0, perto do topo da
    montagem;
  - `R$ 1,30` registra;
  - `PETRW999` mostra a mensagem nova;
  - o Book mostra o aviso da primeira varredura.

  Guarde as fotos no scratchpad.
- [ ] **Step 3: `instalar.sh`** com `DIR_APP`, `DIR_MENU` e `DIR_ICONES` em pasta temporária:
  - o ícone é copiado, e o atalho tem `Icon=painel-opcoes`;
  - `magick identify packaging/icone/painel-opcoes.ico` lista os sete tamanhos.
- [ ] **Step 4: Documentos.**
  - **ledger:** as decisões do desenho e as da construção, como `Ruling:`.
  - **HANDOFF:**
    - §1: a linha da semana 5;
    - §8: os itens novos para o PC Windows (o ícone no instalador, no atalho e na barra de
      tarefas; o "Escolher pasta…" abre na frente e devolve caminho com acento);
    - §11 nova: o que foi feito, a tabela dos 9 critérios com o estado de cada um e os passos de
      fechamento (versão 1.0.0, merge na `master`, tag `v1.0.0`).
  - **ROADMAP** e **README:** a linha da semana 5.

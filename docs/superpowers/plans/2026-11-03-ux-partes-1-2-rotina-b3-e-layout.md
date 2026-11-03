# UX partes 1 e 2: rotina da B3 e layout — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a aba Arquivos B3 ganha a rotina da semana com os links exatos e o estado de cada arquivo, e o Montador e o "Registrar operação" param de cortar a cadeia e de esticar em tela larga.

**Architecture:** a idade do COTAHIST em dias úteis entra no status de mercado do mesmo jeito que a do Cadastro (calculada no `config`, levada pelo `MarketViewService`, exposta pelo `GET /api/mercado/status`); a rotina é um bloco novo na página `ArquivosB3`. O layout é CSS no `tema.css` mais a troca de lugar das ações no `Montador.tsx`.

**Tech Stack:** Python 3.12+ (FastAPI, pydantic), React + TypeScript (Vite, Vitest, Testing Library).

**Spec:** [`docs/superpowers/specs/2026-11-03-ux-book-aprender-design.md`](../specs/2026-11-03-ux-book-aprender-design.md), §2, §3 e §4.

## Global Constraints

- Português em código, comentários, testes e textos; comentário só para um porquê não óbvio.
- **Nenhum agente faz `git commit`, `merge` ou `push`**: as mudanças ficam no working tree e o autor commita.
- Parte 1 na branch `feat/ux-rotina-b3`, parte 2 na branch `feat/ux-layout`, as duas a partir da `development`, na worktree `/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer-dev`.
- Python: `PY=/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin/python` com `PYTHONPATH=src`, rodando da raiz da worktree. Por tarefa: `$PY -m pytest -q -p no:cacheprovider <suítes tocadas>`, `$PY -m mypy`, `$PY -m ruff check .`, `$PY -m ruff format --check .`, `$(dirname $PY)/lint-imports --no-cache`. Frontend: `npm --prefix frontend run verificar`.
- Gate completo só no fim de cada parte: `$PY -m pytest -q -p no:cacheprovider --cov` (cobertura ≥ 95%) e `npm --prefix frontend run build`.
- Links exatos (autor, 03/11):
  - Cadastro: `https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/`
  - COTAHIST: `https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/`
- "Velho" = mais de 5 dias úteis (`STALE_CADASTRO_BUSINESS_DAYS` de `adapters/outbound/b3files/library.py`), para o Cadastro e para o COTAHIST.
- Larguras do Montador (medidas em 03/11 com a cadeia real): cadeia natural ≈ 855 px, menu 180 px, respiro do `main` ≈ 38 px; coluna do resultado **600 px**; duas colunas só a partir de **1720 px** de largura de janela.

## Review Focus

1. **Hoje além do calendário de feriados** (o calendário vai até 31/12/2027): a idade sai `None`, a tela mostra a data do último pregão sem "em dia" nem "hora de baixar", e nada quebra. Testes nas Tasks 1 e 2.
2. **COTAHIST com pregão no futuro em relação a hoje** (relógio do PC atrasado): idade 0, "em dia". Teste na Task 1.
3. **Biblioteca ilegível ou sem COTAHIST**: idade `None`; a rotina mostra "ainda não baixado" para o COTAHIST. Testes nas Tasks 1 e 2.
4. **Cadastro presente mas sem data** (`cadastro: null` com motivo): o passo do Cadastro mostra o motivo que já vem da API, não "em dia". Teste na Task 2.
5. **Janela entre 1100 e 1780 px** (notebook de 1366): o resultado fica embaixo da cadeia, sem corte de colunas; confere-se nos prints da Task 5.

---

## Parte 1 — rotina da semana (branch `feat/ux-rotina-b3`)

### Task 1: idade do COTAHIST no status de mercado

**Files:**
- Modify: `src/options_engine/application/ports/inbound.py` (`MarketStatus`)
- Modify: `src/options_engine/application/use_cases/market_view.py` (`MarketViewService.__init__` e `status`)
- Modify: `src/options_engine/config/web_app.py` (nova `_cotahist_age`, ligada no `MarketViewService`)
- Modify: `src/options_engine/adapters/inbound/web/market.py` (`FaixaOut`, `_status_out`)
- Test: `tests/application/test_market_view.py`, `tests/config/test_web_app.py`, `tests/web/test_market_api.py`

**Interfaces:**
- Produces:
  - `MarketStatus.cotahist_business_days: int | None = None` (último campo, com padrão).
  - `MarketViewService(..., cotahist_age: Callable[[], int | None] = lambda: None)` (keyword-only, ao lado de `cotahist_range`).
  - `_cotahist_age(library: B3FileLibrary, calendar: TradingCalendar, clock: Clock) -> int | None` em `config/web_app.py`.
  - JSON: `"cotahist": {"de": str, "ate": str, "dias_uteis": int | null, "velho": bool}`.

- [ ] **Step 1: Escrever os testes que falham**
  - `test_market_view.py`: `test_status_leva_a_idade_do_cotahist` — serviço montado com `cotahist_age=lambda: 7` devolve `status().cotahist_business_days == 7`; sem o argumento, `None`.
  - `test_web_app.py`, usando a `biblioteca(...)` que o arquivo já usa (último pregão 23/10/2026), `StaticHolidayCalendar.from_packaged_data()` e um `FixedClock` com a data de "hoje" de cada caso (por exemplo `FixedClock(datetime(2026, 11, 3, 15, 0, tzinfo=UTC))`):
    - `test_idade_do_cotahist_em_dias_uteis`: último pregão 23/10/2026, hoje 03/11/2026 → `6` (24/10 e 25/10 fim de semana, 02/11 feriado: 26, 27, 28, 29, 30/10 e 03/11);
    - `test_idade_do_cotahist_sem_arquivo_e_nula` → `None`;
    - `test_idade_do_cotahist_com_pregao_no_futuro_e_zero` → `0`;
    - `test_idade_do_cotahist_fora_do_calendario_e_nula`: hoje em 2028 → `None` (o `DomainError` do calendário não sobe).
  - `test_market_api.py`: no falso que já devolve `cotahist_range=(date(2026, 1, 2), date(2026, 10, 23))`, pôr `cotahist_business_days=6`; o `GET /api/mercado/status` traz `"cotahist": {"de": "2026-01-02", "ate": "2026-10-23", "dias_uteis": 6, "velho": True}`. Um segundo caso com `cotahist_business_days=5` dá `"velho": False`, e com `None` dá `"dias_uteis": None, "velho": False`.

- [ ] **Step 2: Rodar e ver falhar**

  Run: `$PY -m pytest -q -p no:cacheprovider tests/application/test_market_view.py tests/config/test_web_app.py tests/web/test_market_api.py`
  Expected: FAIL (campo e função inexistentes).

- [ ] **Step 3: Implementar**
  - `_cotahist_age`: o fim de `_cotahist_range(library)`; hoje é `clock.now().astimezone(B3_UTC_OFFSET).date()`; `calendar.business_days_between(fim, hoje)` se `fim < hoje`, senão `0`; `DomainError` ou `OSError` → `None`. Mesmo molde de `_freshness`.
  - `FaixaOut.velho = dias_uteis is not None and dias_uteis > STALE_CADASTRO_BUSINESS_DAYS`.

- [ ] **Step 4: Rodar e ver passar** (mesmo comando do Step 2; depois mypy, ruff, ruff format e import-linter).

### Task 2: bloco "Rotina da semana" na aba Arquivos B3

**Files:**
- Modify: `frontend/src/api/cliente.ts` (`StatusMercado.cotahist`)
- Modify: `frontend/src/paginas/ArquivosB3.tsx`
- Modify: `frontend/src/tema.css` (estilo do bloco)
- Test: `frontend/src/paginas/ArquivosB3.test.tsx`

**Interfaces:**
- Consumes: `cotahist: { de: string; ate: string; dias_uteis: number | null; velho: boolean } | null` (Task 1).

- [ ] **Step 1: Escrever os testes que falham** (no `ArquivosB3.test.tsx`; o `STATUS_VELHO` ganha `dias_uteis: 6, velho: true` no `cotahist`)
  - `test("a rotina da semana tem os dois links exatos da B3")`: `getByRole("link", { name: /Cadastro de Instrumentos/ })` com `href` igual ao link do Cadastro das Global Constraints, e `getByRole("link", { name: /COTAHIST anual/ })` com o `href` do COTAHIST; os nomes de arquivo `pesquisa-pregao.zip` e `COTAHIST_A2026.zip` aparecem no texto (o ano sai do relógio do navegador).
  - `test("cadastro velho e cotahist velho dizem hora de baixar")`: com o `STATUS_VELHO`, os dois passos mostram "hora de baixar".
  - `test("arquivo recente diz em dia com a data")`: `cadastro: { data: "2026-11-03", dias_uteis: 0, velho: false }`, `cotahist: { ..., ate: "2026-10-30", dias_uteis: 1, velho: false }` → os dois passos mostram "em dia" e as datas 03/11/2026 e 30/10/2026.
  - `test("cotahist sem idade mostra só a data")`: `cotahist: { de: "2026-01-02", ate: "2026-10-30", dias_uteis: null, velho: false }` → o passo do COTAHIST mostra 30/10/2026 e não mostra "em dia" nem "hora de baixar".
  - `test("sem arquivo diz ainda não baixado")`: `cadastro: null` com `cadastro_motivo: "nenhum Cadastro de Instrumentos importado"` e `cotahist: null` → o passo do COTAHIST mostra "ainda não baixado" e o do Cadastro mostra o motivo.
  - O teste antigo `"lista os arquivos com tipo e data e os links da B3"` passa a conferir só a lista; a lista "Onde baixar" sai (os links agora são os da rotina).

- [ ] **Step 2: Rodar e ver falhar**

  Run: `npm --prefix frontend run verificar`
  Expected: FAIL nos testes novos.

- [ ] **Step 3: Implementar** no topo da página, acima do texto de hoje:
  - título "Rotina da semana" e os dois passos, cada um com: o link (texto "Cadastro de Instrumentos — Pesquisa por pregão" e "COTAHIST anual — Cotações Históricas", `target="_blank" rel="noreferrer"`), a instrução ("escolha o último pregão e o Cadastro de Instrumentos" / "baixe a série anual do ano corrente"), o arquivo esperado e o estado (`em dia` · data, `hora de baixar` · data e dias úteis, `ainda não baixado`, ou o `cadastro_motivo`);
  - uma linha: "O diário não é preciso: o anual baixado no dia já traz o último pregão.";
  - trocar `LINK_BOLETIM` pelo link da Pesquisa por pregão e remover a seção "Onde baixar".
  - O estado também é texto, não só cor (regra do `tema.css`: "Cor nunca é a única pista").

- [ ] **Step 4: Rodar e ver passar** (`npm --prefix frontend run verificar`).

**Fim da parte 1:** gate completo, prints da aba em 1366 e 1920 px pelo controlador (navegador automático fora do repositório) e entrega ao autor.

---

## Parte 2 — layout (branch `feat/ux-layout`, a partir da `development` com a parte 1)

### Task 3: Montador sem cadeia cortada nem resultado esticado

**Files:**
- Modify: `frontend/src/paginas/Montador.tsx` (ordem dentro de `.montador-resultado`)
- Modify: `frontend/src/tema.css` (`.montador-corpo` e o `@media`)
- Test: `frontend/src/paginas/Montador.test.tsx`

- [ ] **Step 1: Escrever o teste que falha**
  - `test("salvar e registrar ficam logo abaixo das pernas, antes do resumo e do gráfico")`: com a análise de sempre (`api()` + `montar()` e um modelo escolhido, como no teste de "salvar simulação"), o botão "Salvar simulação" vem **antes** do `getByRole("img", { name: /Resultado de/ })` na ordem do documento (`compareDocumentPosition` com `DOCUMENT_POSITION_FOLLOWING`), e o botão "Registrar como executada" também.

- [ ] **Step 2: Rodar e ver falhar** (`npm --prefix frontend run verificar`; hoje as ações vêm depois do gráfico).

- [ ] **Step 3: Implementar**
  - No `Montador.tsx`, `.acoes-montador` e o `<details className="simulacoes">` passam para logo depois de `<TabelaPernas …/>`, antes do bloco `analise !== null`.
  - No `tema.css`: `.montador-corpo` com uma coluna por padrão; `@media (min-width: 1780px)` com `grid-template-columns: minmax(0, 1fr) 600px`. Sai o `@media (max-width: 1100px)` de hoje. Um comentário curto diz de onde vêm os 1780 px (cadeia ≈ 855 + 600 + menu e respiros).

- [ ] **Step 4: Rodar e ver passar** (`npm --prefix frontend run verificar`).

### Task 4: "Registrar operação" e os outros painéis da Carteira com largura máxima

**Files:**
- Modify: `frontend/src/componentes/FormOperacao.tsx` (classe no campo do ticker)
- Modify: `frontend/src/tema.css` (`.painel-carteira`, `.tabela-registro`)
- Test: `frontend/src/componentes/FormOperacao.test.tsx`

- [ ] **Step 1: Escrever o teste que falha**
  - `test("o campo da série cabe o ticker inteiro")`: no formulário vindo do montador (mesmo arranjo do primeiro teste do arquivo), o `getByLabelText("Ticker da perna 1")` tem a classe `campo-ticker` e o valor `BOVAK168W1` inteiro (o valor já é inteiro hoje; o que falha é a classe, que é o gancho do CSS).

- [ ] **Step 2: Rodar e ver falhar** (`npm --prefix frontend run verificar`).

- [ ] **Step 3: Implementar**
  - `className="campo-ticker"` no input do ticker de cada perna.
  - `tema.css`: `.painel-carteira { max-width: 900px; }` (vale para os quatro painéis que usam a classe: registrar, encerrar, exercício e adicionar ações); `.tabela-registro { width: auto; }` para o × ficar ao lado das execuções; `.tabela-registro input.campo-ticker { width: 13ch; }` (o maior ticker de opção tem 10 caracteres; 13ch dá folga para o padding).

- [ ] **Step 4: Rodar e ver passar** (`npm --prefix frontend run verificar`).

### Task 5: conferência das telas nas quatro larguras (controlador)

Feita por quem coordena, não por um implementador, porque precisa do app rodando com os arquivos reais e de um navegador automático fora do repositório.

- [ ] **Step 1:** `npm --prefix frontend run build` e reiniciar o app da worktree.
- [ ] **Step 2:** prints em 1280, 1366, 1920 e 2560 px de: Mercado (cadeia aberta), Montador (item do Book aberto), Carteira (Registrar operação aberto), Book e Arquivos B3.
- [ ] **Step 3:** para cada print, conferir: nenhuma tabela principal cortada; nenhum painel esticado sem necessidade; "Salvar simulação" logo abaixo das pernas; ticker inteiro no campo Série. Problema do mesmo tipo resolvido só com CSS: corrigir no `tema.css` e refazer o print. Problema que pede mudança de comportamento: anotar numa lista para o autor (spec §4.3).
- [ ] **Step 4:** gate completo da parte 2 e entrega dos prints ao autor.

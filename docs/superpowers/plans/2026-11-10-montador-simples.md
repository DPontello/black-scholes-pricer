# Montador simples: menos informação à vista, cores suaves (plano)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o Montador abre simples. A cadeia é enxuta à esquerda e o resultado fica à direita. À
vista ficam a frase, três números e o gráfico, e o resto vai para "ver detalhes". As cores do app
ficam mais suaves.

**Architecture:** só frontend (React/TypeScript e `tema.css`), mais um teste em pytest que lê o
`tema.css` para conferir o contraste. Nenhum número, API ou arquivo de dados muda.

Três peças novas:

- `usePreferencia`: o que fica guardado no navegador, protegido por `try/catch`;
- `TabelaCadeia` com a opção `enxuta`;
- `CartaoResultado`: título, frase, números, gráfico, avisos e detalhes.

O Montador passa a ter um vencimento só, o do seletor do topo. Ele acompanha esse vencimento e
também os das pernas já postas.

**Tech Stack:**

- React 18, Vite e Vitest (jsdom, Testing Library);
- CSS puro (`frontend/src/tema.css`);
- Python 3.12 e pytest, só no teste de contraste.

**Spec:** [`docs/superpowers/specs/2026-11-09-montador-simples-design.md`](../specs/2026-11-09-montador-simples-design.md)

## Global Constraints

- **Commit:** quem constrói **não commita nem dá push**; o autor commita. Este plano não tem
  passo de commit. A branch é a `feat/montador-simples`, aberta da `development` em `abb8911`,
  com o valor bruto já dentro (§8 do desenho, item 1).
- **Nenhum número muda:** cálculo, preço, custo, IR e chance ficam como estão. O texto de
  `frase()` também não muda.
- **O "+" da cadeia não rola a tela.** A rolagem até a montagem quando ela chega de fora da
  cadeia (semana 5) continua.
- **Avisos e "Sem avaliação de hoje"** nunca ficam atrás de "ver detalhes".
- **O Mercado** continua com a cadeia completa: 15 colunas, a fileira de vencimentos e as abas.
- **Contraste:** todo texto colorido fica com pelo menos 4,5:1 sobre `--fundo` (`#0f1115`) e
  sobre `--painel` (`#171a21`).
- **Tons:** `--destaque: #1e88e5` (o azul forte de hoje). Os tons suaves são `--compra: #7fb3e6`,
  `--venda: #e09a98`, `--alta: #5fbfb4` e `--baixa: #e5807e`.
- **Navegador:** toda leitura e escrita no `localStorage` vai dentro de `try/catch`. Sem ele, a
  tela começa com tudo fechado.
- **Estilo:** textos em português do Brasil, no tom dos que já existem. Comentário só para um
  porquê não óbvio. Seguir o estilo do arquivo em volta.
- **Comandos:** rodar da raiz do worktree
  `/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer-dev`. Use
  `VENV=/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin` e
  `PYTHONPATH=src` no Python.
- **Checagens por tarefa:** só as suítes tocadas e `tsc`. O gate inteiro roda na Task 6.

## Decisões minhas (o autor confere ao ler)

1. **O Montador acompanha o vencimento do seletor e os das pernas postas.** Com o Tryd ao vivo, a
   cadeia só traz as séries dos vencimentos acompanhados (`adapters/outbound/tryd/feed.py`,
   `_selected_rows`). Se o Montador acompanhasse só o do seletor, trocar o vencimento tiraria o
   preço das pernas já postas, e a análise sairia com "fora da cadeia (vencimento não
   assinado…)". Isso quebraria o "trocar o vencimento não mexe nas pernas" do objetivo B. A
   cadeia enxuta mostra só o vencimento do seletor.
2. **O pedido que vem do Book abre no vencimento do item, e a rolagem no vencimento novo.** O
   Book passa `vencimento` no estado da rota. A rolagem já leva `vencimento_novo`.
3. **Limite conhecido, igual ao de hoje:** uma simulação salva num vencimento que não está no
   seletor sai com o erro "fora da cadeia". A simulação não guarda o vencimento, e o backend não
   muda. É só escolher o vencimento no seletor.
4. **"ver detalhes" é um botão** (`aria-expanded`), não um `<details>`, igual ao "mostrar IV,
   delta e negócios". Os textos são "▸ ver detalhes" e "▾ esconder detalhes". Fechado, o
   conteúdo nem é desenhado.
5. **O botão principal tem texto `--fundo` sobre `--destaque`** (5,1:1). O branco sobre
   `#1e88e5` dá 3,7:1 e não passa.
6. **O ponto de quebra fica em 1280 px**, com as colunas `minmax(0, max-content)` para a cadeia e
   `minmax(480px, 1fr)` para o resultado. A cadeia enxuta tem uns 420 px, e a conta é 420 + 16 +
   480 + 180 (menu) + 40 (respiro) = 1136 px, o que deixa folga para o Segoe UI. Com IV, delta e
   negócios abertos, a cadeia rola dentro do próprio cartão. A medida no Windows fica com o autor
   (Task 6).
7. **O gráfico do Montador tem 260 px de altura,** em vez de 320, para a frase, os números e o
   gráfico caberem a 1366 × 768 sem rolar (critério 1).
8. **O contraste é conferido em pytest** (`tests/web/test_tema.py`), lendo o `tema.css`. No
   Vitest, o `import "./tema.css?raw"` volta vazio, porque o CSS não é processado nos testes.

## Review Focus

1. **Perna de outro vencimento com o Tryd ao vivo:** trocar o seletor com uma perna posta
   precisa continuar acompanhando o vencimento dela, senão a perna perde o preço. Teste na Task 3.
2. **Modelo pronto logo depois de trocar o vencimento,** antes de a cadeia nova chegar: o backend
   responderia "sem séries no vencimento". O modelo fica em "aguardando a cadeia" até o
   vencimento estar na cadeia. Teste na Task 3.
3. **Pedido de assinatura repetido:** um tique da cadeia ou um novo render não pode reenviar o
   `seguirCadeia`, porque os termos do Tryd vedam "flood". Teste na Task 3.
4. **Item do Book na semanal mais próxima** (fora do primeiro mensal): o seletor abre nele, e a
   análise sai com preço. Teste na Task 3.
5. **`localStorage` bloqueado** (janela anônima, por exemplo): a tela abre fechada, os botões
   funcionam na memória e nada estoura. Teste na Task 2.

---

### Task 1: Cores suaves, `--destaque` e o botão principal

**Files:**
- Modify: `frontend/src/tema.css`
- Create: `tests/web/test_tema.py`

**Interfaces:**
- Produces: a variável `--destaque` e a classe `.botao-principal`, que a Task 4 usa no
  "Registrar como executada".

- [ ] **Step 1: Escrever os testes que falham**

O arquivo fica em `tests/web/test_tema.py`. `RAIZ = Path(__file__).resolve().parents[2]` e
`TEMA = RAIZ / "frontend" / "src" / "tema.css"`. Os auxiliares:

- `_variaveis()` lê as `--nome: #rrggbb;` do primeiro bloco `:root`;
- `_contraste(a, b)` calcula a razão do WCAG 2.x pela luminância relativa.

```python
@pytest.mark.parametrize("fundo", ["fundo", "painel"])
@pytest.mark.parametrize("cor", ["compra", "venda", "alta", "baixa", "destaque"])
def test_cores_de_texto_tem_contraste_minimo(cor: str, fundo: str) -> None:
    v = _variaveis()
    assert _contraste(v[cor], v[fundo]) >= 4.5

def test_tons_suaves_do_rascunho() -> None:
    v = _variaveis()
    assert (v["destaque"], v["compra"], v["venda"], v["alta"], v["baixa"]) == (
        "#1e88e5", "#7fb3e6", "#e09a98", "#5fbfb4", "#e5807e")

def test_compra_so_pinta_o_preco_de_compra() -> None:
    # Links, menu, abas, foco e a faixa da rolagem usam --destaque.
    assert TEMA.read_text(encoding="utf-8").count("var(--compra)") == 1

def test_botao_principal_tem_texto_escuro_sobre_o_destaque() -> None:
    bloco = re.search(r"\.botao-principal \{([^}]*)\}", TEMA.read_text(encoding="utf-8"))
    assert bloco is not None
    assert "background: var(--destaque)" in bloco.group(1)
    assert "color: var(--fundo)" in bloco.group(1)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `PYTHONPATH=src $VENV/python -m pytest -q tests/web/test_tema.py`
Expected: FAIL. Falta `destaque`, a venda de hoje (`#e53935`) dá 4,47:1 sobre `--fundo`, e
`var(--compra)` aparece 15 vezes.

- [ ] **Step 3: Mudar o `tema.css`**

- No `:root`, entra `--destaque: #1e88e5;` e os quatro tons passam para os valores das Global
  Constraints.
- Todo `var(--compra)` vira `var(--destaque)`, menos o de `.compra { color: … }`. São estes:
  - `a`;
  - `.menu-lateral a.active`;
  - `button:hover`;
  - `button.link`;
  - `.abas button[aria-selected="true"]`;
  - `.sub-abas a.active`;
  - `a.termo` e `a.termo:hover`;
  - `a.ajuda:hover, a.ajuda:focus-visible`;
  - `.termo-glossario.termo-alvo`;
  - `.vencimentos button[aria-pressed="true"]`;
  - `.faixa-rolagem`.
- A classe nova `.botao-principal` tem `background: var(--destaque)`, `border-color:
  var(--destaque)`, `color: var(--fundo)` e `font-weight: 600`. O `:hover` clareia a borda com
  `var(--texto)`. Desabilitado, o botão segue o visual de botão desabilitado que já existe.

- [ ] **Step 4: Rodar e ver passar**

Run: `PYTHONPATH=src $VENV/python -m pytest -q tests/web/test_tema.py && $VENV/ruff check tests/web/test_tema.py && $VENV/ruff format --check tests/web/test_tema.py && $VENV/mypy`
Expected: os 13 testes passam, e o ruff e o mypy não acusam nada.

---

### Task 2: Preferência guardada e a cadeia enxuta

**Files:**
- Create: `frontend/src/preferencias.ts` e `frontend/src/preferencias.test.ts`
- Modify: `frontend/src/componentes/TabelaCadeia.tsx`, `frontend/src/componentes/TabelaCadeia.test.tsx` e `frontend/src/testes/setup.ts`

**Interfaces:**
- Produces:
  - `usePreferencia(chave: string): [boolean, (valor: boolean) => void]`;
  - `PREFERENCIA_COLUNAS = "montador.colunas-completas"`;
  - `PREFERENCIA_DETALHES = "montador.detalhes"`;
  - as props novas do `TabelaCadeia`: `enxuta?: boolean`, `vencimento?: string` e
    `onVencimentos?: (datas: string[]) => void`, que passa a ser opcional.

- [ ] **Step 1: Escrever os testes que falham**

No `setup.ts`, entra um `afterEach(() => localStorage.clear())`.

Os testes do `preferencias.test.ts` usam o `renderHook` e o `act` do `@testing-library/react`:

```ts
test("sem nada guardado começa falso, e o que se grava volta ao montar de novo", () => {
  const primeira = renderHook(() => usePreferencia("x"));
  expect(primeira.result.current[0]).toBe(false);
  act(() => primeira.result.current[1](true));
  expect(primeira.result.current[0]).toBe(true);
  primeira.unmount();
  expect(renderHook(() => usePreferencia("x")).result.current[0]).toBe(true);
});

test("com o localStorage bloqueado, começa falso e muda só na memória, sem erro", () => {
  const erro = () => { throw new DOMException("bloqueado", "SecurityError"); };
  const ler = vi.spyOn(Storage.prototype, "getItem").mockImplementation(erro);
  const gravar = vi.spyOn(Storage.prototype, "setItem").mockImplementation(erro);
  const { result } = renderHook(() => usePreferencia("x"));
  expect(result.current[0]).toBe(false);
  act(() => result.current[1](true));
  expect(result.current[0]).toBe(true);
  ler.mockRestore();
  gravar.mockRestore();
});
```

No `TabelaCadeia.test.tsx`, a ajuda `enxuta(vencimento)` desenha a cadeia com `enxuta`,
`vencimento` e `onEscolherSerie={nada}`, sem `onVencimentos`. Os testes:

- `test("enxuta: 7 colunas, sem a fileira de vencimentos nem as abas")`:
  - a linha do 52,00 tem 7 células, nesta ordem: `+`, `—` (sem compra), `1,25`, `52,00`,
    `1,25`, `1,20` e `+`;
  - `queryByRole("group", { name: "Vencimentos" })` é nulo;
  - `queryAllByRole("tab")` tem tamanho 0.
- `test("enxuta mostra o vencimento que vem de fora")`: com `"2026-12-17"`, aparece o `52,00` e
  some o `54,00`.
- `test("enxuta com um vencimento que ainda não chegou avisa no lugar da tabela")`: com
  `"2026-11-06"`, aparece o texto `Carregando o vencimento 06/11…`.
- `test("mostrar IV, delta e negócios abre as 4 colunas de cada lado, e a escolha fica guardada")`:
  - o clique no botão `mostrar IV, delta e negócios` deixa a linha do 52,00 com 15 células, e o
    botão passa a se chamar `esconder IV, delta e negócios`, com `aria-expanded="true"`;
  - depois do `unmount()`, a cadeia desenhada de novo já vem com 15 células;
  - os dois "?" (IV e Delta) só aparecem com as colunas abertas.
- `test("sem enxuta, a cadeia do Mercado continua com as 15 colunas, a fileira e as abas")`: sem
  `onEscolherSerie`, a linha do 52,00 tem 13 células, e o grupo "Vencimentos" e as 2 abas existem.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm --prefix frontend exec -- vitest run src/preferencias.test.ts src/componentes/TabelaCadeia.test.tsx`
Expected: FAIL. O módulo `../preferencias` não existe, e a cadeia enxuta ainda tem 15 colunas.

- [ ] **Step 3: Implementar**

`preferencias.ts`:

- `usePreferencia` lê uma vez, no `useState` inicial: `localStorage.getItem(chave) === "1"`.
  Qualquer exceção vira `false`.
- O setter muda o estado e grava `"1"` ou `"0"`, ignorando a exceção.

`TabelaCadeia`:

- Com `enxuta`, a cadeia não tem `EscolhaVencimentos` nem abas.
- O vencimento mostrado é `cadeia.vencimentos.find((v) => v.data === vencimento)`:
  - sem `vencimento`, a mensagem de hoje, "Nenhum vencimento com séries no cadastro.";
  - com `vencimento` fora da cadeia, `Carregando o vencimento dd/mm…`.
- O `Lado` recebe `completas: boolean` e, com `false`, só desenha as células `compra` e
  `venda`, na mesma ordem espelhada.
- As linhas de cabeçalho ficam com `colSpan` 2 ou 6, e a lista de rótulos de cada lado fica com
  2 ou 6 nomes.
- O botão `button.link` com `aria-expanded` fica entre o cabeçalho e a tabela, só na enxuta. Ele
  usa `usePreferencia(PREFERENCIA_COLUNAS)`.
- Sem `enxuta`, nada muda.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm --prefix frontend exec -- vitest run src/preferencias.test.ts src/componentes/TabelaCadeia.test.tsx && npm --prefix frontend exec -- tsc --noEmit`
Expected: todos passam, e o `tsc` não acusa nada. O `Mercado` e o `Montador` não mudam nesta
tarefa.

---

### Task 3: Montador com um vencimento só

**Files:**
- Modify:
  - `frontend/src/paginas/Montador.tsx` e `frontend/src/paginas/Montador.test.tsx`;
  - `frontend/src/componentes/CartaoDestaque.tsx` e `frontend/src/componentes/CartaoDestaque.test.tsx`;
  - `frontend/src/componentes/TabelaFamilia.tsx` e `frontend/src/componentes/TabelaFamilia.test.tsx`.

**Interfaces:**
- Consumes: o `TabelaCadeia` com `enxuta` e `vencimento` (Task 2).
- Produces: o estado da rota do Montador,
  `{ pedido?: PedidoAnalise; vencimento?: string; rolagem?: Rolagem }`. O Book manda
  `{ pedido: item.pedido, vencimento: item.vencimento }`.

- [ ] **Step 1: Escrever os testes que falham**

No `Montador.test.tsx`, entra a constante
`COM_DEZEMBRO = { ...CADEIA, disponiveis: [...CADEIA.disponiveis, { data: "2026-12-17", dias_uteis: 35, semanal: false }] }`.
A ajuda `montar` passa a aceitar o `aoVivo`. O seletor muda de `aria-label` para
`"Vencimento"`.

Os testes que mudam:

- "modelo pronto pede a sugestão…": `expect(seguir).toHaveBeenCalledWith("PETR4", ["2026-11-19"])`.
- "o + da cadeia põe a série…", "o + da cadeia não rola a tela" e "o + depois do modelo
  pronto…": sai o clique na aba `19/11 (15 du)`, porque o 19/11 já é o padrão.
- "o modelo usa o primeiro mensal…": passa a buscar pelo rótulo `"Vencimento"`.

Os testes novos:

- `test("o seletor lista todos os vencimentos disponíveis, com a semanal marcada com S")`: com
  `COM_DEZEMBRO`, os textos das opções são `["30/10 S", "19/11", "17/12"]`.
- `test("trocar o vencimento acompanha o novo e mantém a perna, ainda acompanhada")`:
  - "+" na PETRK541, depois troca para `2026-10-30`;
  - `seguir` termina chamado com `("PETR4", ["2026-10-30", "2026-11-19"])`;
  - `getByLabelText("Preço de PETRK541")` continua lá;
  - clicar em `Tirar PETRK541` faz o `seguir` terminar com `("PETR4", ["2026-10-30"])`.
- `test("o modelo espera o vencimento escolhido chegar na cadeia")`:
  - com `COM_DEZEMBRO`, trocar para `2026-12-17`, que está em `disponiveis` mas não em
    `vencimentos`, deixa o "Modelo pronto" desabilitado com a opção `aguardando a cadeia`;
  - num rerender com a cadeia trazendo o 17/12 em `vencimentos`, ele volta a funcionar.
- `test("um tique da cadeia não pede a assinatura de novo")`: depois da primeira chamada com
  `["2026-11-19"]`, um rerender com a `hora` nova não muda o `seguir.mock.calls.length`.
- `test("cadeia indisponível: o aviso no lugar da cadeia e o seletor desabilitado")`:
  - entrada: `cadeia: null` e
    `cadeiaIndisponivel: { ativo: "PETR4", erro: "x", mensagem: "aguardando dados do Tryd" }`;
  - saída: o texto `/Cadeia de PETR4 indisponível/` e o seletor com `disabled`.
- `test("só semanais: o padrão é o primeiro da lista")`: com `disponiveis` só de semanais, o
  valor do seletor é o primeiro deles.
- `test("o pedido do book abre no vencimento do item")`:
  - entrada: o estado `{ pedido: SUGESTAO, vencimento: "2026-10-30" }`;
  - saída: o seletor fica em `2026-10-30`, e a última chamada do `seguir` inclui o
    `"2026-10-30"`. A PETRK541 é de 19/11, então o 19/11 também entra.
- Na "a rolagem dos alertas abre o pedido novo…", com `COM_DEZEMBRO`, o seletor fica em
  `2026-12-17`, que é o `vencimento_novo` de `rolagem()`.

No `CartaoDestaque.test.tsx` e no `TabelaFamilia.test.tsx`, o teste de abrir no Montador também
confere `expect(destino.estado.vencimento).toBe(item.vencimento)`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm --prefix frontend exec -- vitest run src/paginas/Montador.test.tsx src/componentes/CartaoDestaque.test.tsx src/componentes/TabelaFamilia.test.tsx`
Expected: FAIL nos testes novos e nos que mudaram. O seletor ainda lista só os `blocos`, e o
estado da rota ainda não leva o `vencimento`.

- [ ] **Step 3: Implementar**

No `Montador.tsx`:

- Saem o estado `vencimentos`, o `blocos` e o `onVencimentos`.
- `disponiveis = cadeiaDoAtivo?.disponiveis ?? []`.
- O `vencimento` é o escolhido, se ele estiver em `disponiveis`. Senão é o primeiro com
  `semanal === false` e, sem mensal, `disponiveis[0]?.data`.
- O escolhido começa em `estadoDaRota?.vencimento ?? estadoDaRota?.rolagem?.vencimento_novo ?? null`.
- `vencimentoNaCadeia = cadeiaDoAtivo?.vencimentos.some((v) => v.data === vencimento) ?? false`.
  Ele toma o lugar do `vencimentoDoModelo === undefined` no "Modelo pronto", no texto "aguardando
  a cadeia", no efeito do `?modelo=` e no `escolherModelo`.
- O vencimento de cada série vem de um `Map` ticker → data, aprendido de toda cadeia do ativo que
  chega (todas as séries de todos os `vencimentos`) e zerado quando o ativo muda.
- `acompanhados` é `null` sem `vencimento`. Com ele, são os únicos ordenados de
  `[vencimento, ...datas conhecidas das pernas do pedido]`.
- O efeito do `seguirCadeia(ativo, acompanhados)` depende de `ativo` e de
  `acompanhados?.join(",")`, nunca do array.
- As opções do seletor são `dd/mm` mais `" S"` nas semanais, e o seletor fica desabilitado com
  `disponiveis` vazio.
- O `TabelaCadeia` recebe `enxuta` e `vencimento={vencimento}`.

No `CartaoDestaque` e no `TabelaFamilia`, o `navegar` passa
`state: { pedido: x.pedido, vencimento: x.vencimento }`.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm --prefix frontend exec -- vitest run src/paginas/Montador.test.tsx src/componentes/CartaoDestaque.test.tsx src/componentes/TabelaFamilia.test.tsx && npm --prefix frontend exec -- tsc --noEmit`
Expected: todos passam, inclusive os de rolagem da semana 5, que não mudam.

---

### Task 4: Cartão do resultado e a ordem da coluna da direita

**Files:**
- Create: `frontend/src/componentes/CartaoResultado.tsx` e `frontend/src/componentes/CartaoResultado.test.tsx`
- Modify:
  - `frontend/src/componentes/ResumoEstrutura.tsx` e `frontend/src/componentes/ResumoEstrutura.test.tsx`;
  - `frontend/src/paginas/Montador.tsx` e `frontend/src/paginas/Montador.test.tsx`.

**Interfaces:**
- Consumes: `usePreferencia` e `PREFERENCIA_DETALHES` (Task 2); `.botao-principal` (Task 1).
- Produces:
  - em `ResumoEstrutura.tsx`: `frase`, sem mudança; `ResumoEstrutura({ analise })`, com a frase e
    os três números grandes; `AvisosEstrutura({ analise })`, com os avisos e o "Sem avaliação de
    hoje"; e `DetalhesEstrutura({ analise })`, com os custos de montagem, os dias úteis, as 4
    gregas e a `GradeCenarios` quando há `hoje`;
  - `CartaoResultado({ analise }: { analise: Analise })`;
  - as classes `.cartao`, `.cartao-resultado`, `.cartao-pernas` e `.numeros-grandes`, que a
    Task 5 estiliza.

- [ ] **Step 1: Escrever os testes que falham**

O `CartaoResultado.test.tsx` desenha com `MemoryRouter`, como o `ResumoEstrutura.test.tsx`:

- `test("abre com a frase, os três números e o gráfico, e os detalhes fechados")`:
  - os números (pela ajuda `numero` do teste de hoje) são `Ganho máximo` R$ 211,00,
    `Perda máxima` R$ -5.080,00 e `Chance de lucro` 68,0%;
  - o gráfico aparece pela `getByRole("img", { name: /Resultado de/ })`;
  - `queryByText("Theta por dia útil")` e `queryByText("Custos de montagem")` são nulos;
  - o botão `▸ ver detalhes` tem `aria-expanded="false"`.
- `test("ver detalhes abre custos, dias úteis, gregas e a grade, e a escolha fica guardada")`:
  - depois do clique, aparecem `Custos de montagem` R$ 1,81, `Dias úteis` 15,
    `Theta por dia útil` e a legenda `Resultado hoje se o preço e a volatilidade mudarem agora`;
  - o botão vira `▾ esconder detalhes`;
  - depois do `unmount()`, o cartão desenhado de novo já vem aberto.
- `test("avisos e 'Sem avaliação de hoje' aparecem com os detalhes fechados")`:
  - o `/ADR-0002/` aparece;
  - com `hoje: null, hoje_indisponivel: "put americana"`, aparece
    `Sem avaliação de hoje: put americana.`
- `test("sem o preço de alguma perna, a frase avisa e os números grandes somem")`: com
  `no_vencimento: null`, aparece `/Falta o preço/`, e `queryByText("Ganho máximo")` é nulo.
- `test("ganho ilimitado aparece como ilimitado")`: com `ganho_max: null`, o número de
  `Ganho máximo` é `ilimitado`.
- `test("a ordem é título, frase, números, gráfico, avisos e ver detalhes")`: confere com
  `compareDocumentPosition`, como o teste de hoje no Montador.

No `ResumoEstrutura.test.tsx`:

- o teste dos brutos confere só os três números, sem `Custos de montagem` e sem `/IR/`;
- o teste dos "?" passa a esperar `["ganho-perda-maximos", "chance-de-lucro"]` no
  `ResumoEstrutura` e `["custos-ir", "delta", "gamma", "theta", "vega"]` no `DetalhesEstrutura`;
- o teste "números, gregas e avisos…" se divide entre o `DetalhesEstrutura` e o
  `AvisosEstrutura`.

No `Montador.test.tsx`, o teste "salvar e registrar ficam logo abaixo das pernas, antes do resumo
e do gráfico" vira
`test("o resultado vem antes das pernas, e registrar e salvar ficam embaixo delas")`. Ele confere
esta ordem: gráfico → `Preço de PETRK541` → `Registrar como executada` → `Nome da simulação`. O
`Registrar` tem a classe `botao-principal`.

O teste novo `test("sem perna, a dica de começar abre a coluna da direita")` confere que o
`.montador-resultado` tem `firstElementChild` com o texto `/Escolha um modelo pronto/`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `npm --prefix frontend exec -- vitest run src/componentes/CartaoResultado.test.tsx src/componentes/ResumoEstrutura.test.tsx src/paginas/Montador.test.tsx`
Expected: FAIL. O `./CartaoResultado` não existe, e o `ResumoEstrutura` ainda mostra os custos e
as gregas.

- [ ] **Step 3: Implementar**

`CartaoResultado` é uma `<section className="cartao cartao-resultado">` com, nesta ordem:

1. o `h2` de hoje (nome, "vence dd/mm/aaaa · preços …"), que sai do Montador com o mapa
   `FONTES`;
2. o `ResumoEstrutura`;
3. o `GraficoPayoff`;
4. o `AvisosEstrutura`;
5. o botão `button.link` com `aria-expanded` e
   `{aberto && <DetalhesEstrutura analise={analise} />}`.

Os três números ficam em `.numeros.numeros-grandes`. O "Chance de lucro" mantém a `dica` e o
`termo` de hoje.

No Montador, a coluna `.montador-resultado` (o `ref` da rolagem fica nela) tem, nesta ordem:

1. `{analise !== null && <CartaoResultado analise={analise} />}`;
2. `<section className="cartao cartao-pernas">`, com o `TabelaPernas` e o `.acoes-montador`.
   Dentro dele vem primeiro o `Registrar como executada`, com `className="botao-principal"`,
   depois o nome e o `Salvar simulação`;
3. as simulações salvas, como hoje.

Sem perna, o `TabelaPernas` já mostra a dica e fica em primeiro, porque a análise é nula. Os
imports de `GradeCenarios`, `GraficoPayoff` e `ResumoEstrutura` saem do Montador.

- [ ] **Step 4: Rodar e ver passar**

Run: `npm --prefix frontend exec -- vitest run src/componentes src/paginas/Montador.test.tsx && npm --prefix frontend exec -- tsc --noEmit`
Expected: todos passam.

---

### Task 5: Cartões, o ponto de quebra e a documentação

**Files:**
- Modify:
  - `frontend/src/tema.css`;
  - `frontend/src/paginas/Montador.tsx` (classe `cartao` no `.montador-cadeia`);
  - `frontend/src/aprender/Telas.tsx`;
  - `README.md`, `docs/ROADMAP.md` e `docs/superpowers/HANDOFF-2026-11-02.md`.

**Interfaces:**
- Consumes: as classes da Task 4.

- [ ] **Step 1: CSS**

- `.cartao` tem `background: var(--painel)`, `border: 1px solid var(--borda)`,
  `border-radius: 6px` e `padding: 0.75rem 1rem`.
- `.montador-resultado` tem `display: flex`, `flex-direction: column` e `gap: 1rem`.
- O `.montador-corpo > *` tem `min-width: 0`, e o `h2` do `.cartao-resultado` fica com
  `margin-top: 0`.
- `.numeros-grandes strong` tem `font-size: 1.6rem`, e `.cartao-resultado .grafico-payoff` tem
  `height: 260px`.
- O `@media (min-width: 1780px)` dá lugar a `@media (min-width: 1280px)`, com
  `grid-template-columns: minmax(0, max-content) minmax(480px, 1fr)`. O comentário acima dele
  fica com a conta da Decisão 6 e diz que, com IV, delta e negócios abertos, a cadeia rola dentro
  do cartão.
- No `Montador.tsx`, o comentário "Abaixo de 1780 px…" passa a dizer 1280 px.

- [ ] **Step 2: Textos**

O texto do Montador em `Telas.tsx` fica assim, com os links de termos que já existem:

> Onde você monta uma operação, por um modelo pronto ou série a série, pelo + da cadeia. O
> vencimento do topo vale para a cadeia e para o modelo. A cadeia mostra só compra e venda;
> "mostrar IV, delta e negócios" abre o resto. Ao lado ficam a frase do resultado, o [ganho e a
> perda máximos](ganho-perda-maximos), a [chance de lucro](chance-de-lucro) e o gráfico; "ver
> detalhes" abre os [custos](custos-ir), os dias úteis, as gregas e a grade de cenários. Embaixo
> das pernas você registra a operação como executada ou salva a simulação.

Uma linha em cada um destes:

- **`README.md`,** no parágrafo do **Montador**: "A tela abre simples: a cadeia enxuta ao lado
  do resultado, e os custos, as gregas e a grade em 'ver detalhes'."
- **`docs/ROADMAP.md`,** um item depois da Semana 5: "Montador simples (2026-11-10)", com os
  links do desenho e deste plano e com "falta conferir no Windows a 1366 e 1920 px".
- **HANDOFF,** um §12 de uma linha, com a branch, o desenho, o plano e o mesmo pendente.

- [ ] **Step 3: Rodar**

Run: `npm --prefix frontend run verificar`
Expected: todos passam, inclusive o `Comece.test.tsx` (seções e links de "Telas do app").

---

### Task 6: Gate inteiro e a conferência na tela

**Files:** nenhum, a não ser que a conferência ache um defeito. Nesse caso, a correção volta para
a tarefa dona, com teste.

- [ ] **Step 1: Gates**

Run:

```bash
npm --prefix frontend run verificar && npm --prefix frontend run build && \
$VENV/ruff check . && $VENV/ruff format --check . && $VENV/mypy && $VENV/lint-imports && \
PYTHONPATH=src $VENV/python -m pytest -q --cov=options_engine
```

Expected:

- o frontend passa (eram 274 testes e agora são mais);
- o build sai em `src/options_engine/adapters/inbound/web/static`;
- o ruff, o mypy e o lint-imports passam;
- o pytest passa com cobertura ≥ 95%, e o golden do backend não muda (critério 7).

- [ ] **Step 2: Conferência no Linux**

Abrir o app pelo atalho, que roda o worktree -dev com o build do Step 1. Com PETR4 e o modelo
"put coberta", conferir os critérios do §7 do desenho:

| Janela | O que conferir | Critérios |
|---|---|---|
| 1366 × 768 | A frase, os 3 números e o gráfico ficam à vista sem rolar a página. | 1 |
| 1279 e 1281 px de largura | Empilhado e lado a lado, respectivamente, sem rolagem horizontal da página. | — |
| 1920 × 1080 | Lado a lado; "mostrar IV, delta e negócios" rola dentro do cartão da cadeia. | — |
| Qualquer uma | As cores dos links e dos botões. | 8 |
| Qualquer uma | O Mercado com a cadeia completa. | 3 |

Anotar o que se viu no §12 do HANDOFF.

- [ ] **Step 3: Pendente do autor**

O §12 do HANDOFF fica com o pedido de conferir no Windows (Segoe UI), a 1366 e 1920 px, os
critérios 1 e 2. Se a cadeia enxuta passar de uns 560 px lá, o ponto de quebra sobe.

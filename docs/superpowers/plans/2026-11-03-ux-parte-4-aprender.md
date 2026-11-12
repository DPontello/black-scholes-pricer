# UX parte 4: aba Aprender — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uma aba "Aprender" com quatro sub-abas (Comece aqui, Operações, Termos, Telas do app), com as 18 operações explicadas com exemplo numérico e gráfico, um glossário com busca e "?" pelo app que levam ao termo.

**Architecture:** os exemplos saem do domínio: `domain/learn/examples.py` monta, para cada modelo de `TEMPLATES`, uma `Strategy` real com PETR4 a R$ 50,00, strikes de R$ 2 em R$ 2 e prêmios de Black-Scholes, e calcula cenários, empates, ganho e perda máximos e a curva com `expiry_pnl`/`expiry_summary` (os mesmos do Montador). Um router sem perfil serve `GET /api/aprender/exemplos`. Os textos (o que é, quando usar, o que pode dar errado, termos, telas) ficam em módulos de conteúdo do frontend; o exemplo é montado na tela a partir dos números da API, sem número escrito à mão no texto.

**Tech Stack:** Python 3.12+ (FastAPI, pydantic), React + TypeScript (Vite, Vitest, Testing Library, ECharts já no projeto).

**Spec:** [`docs/superpowers/specs/2026-11-03-ux-book-aprender-design.md`](../specs/2026-11-03-ux-book-aprender-design.md), §6 (e §2, §5 para os "?" do Book).

## Global Constraints

- Português simples nos textos; comentário só para um porquê não óbvio.
- **Nenhum agente faz `git commit`, `merge` ou `push`**: o autor commita. **Os textos financeiros passam pela revisão do autor antes do merge** (spec §6.4).
- Worktree `/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer-dev`, branch `feat/ux-aprender`. Python: `PY=/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin/python` com `PYTHONPATH=src`; gates como nas partes anteriores (pytest das suítes tocadas, mypy, ruff, ruff format, import-linter; `npm --prefix frontend run verificar`).
- **Exemplo fixo** (decisão do spec): ativo `PETR4`, spot **R$ 50,00**, strikes `50 + 2 × passo` (o `offset` de cada `TemplateLeg`), lote **100** por unidade de `ratio`, ação **100** quando o modelo tem perna de ação (comprada a R$ 50,00), prêmio = `round(bs_price(50, K, 21/252, 0.14, 0.30, is_call=…), 2)`, vencimento a 21 dias úteis. Marcado na tela como "exemplo, sem custos nem IR".
- **Cenários do exemplo:** preço no vencimento R$ 45,00 (cai 10%), R$ 50,00 (fica) e R$ 55,00 (sobe 10%); curva de R$ 30,00 a R$ 70,00 com 81 pontos.
- "Perde até" é valor positivo, `max(0, -mínimo)`; `None` = sem limite (mesma regra do Book).
- Os "?" levam a `/aprender/termos#<id>` com os ids da tabela da Task 4.
- Sem dependência nova.

## Review Focus

1. **Aprender sem perfil aberto**: a aba abre pela tela de perfis e mostra tudo; o "Montar no Montador" fica desabilitado com o motivo. Teste na Task 2 e na Task 3.
2. **Estrutura de perda ou ganho sem limite** (straddle/strangle vendidos, compra de call, put protetora): o exemplo diz "sem limite" e o gráfico não inventa teto. Testes nas Tasks 1 e 3.
3. **Modelo do Montador que não cabe na cadeia** (iron condor sem 5 strikes): "Montar no Montador" abre o Montador e mostra a mensagem de erro de hoje, sem quebrar. Teste na Task 6.
4. **Endereço com modelo ou termo que não existe** (`/aprender/operacoes/xyz`, `#termo-inexistente`): abre a primeira operação / a lista inteira, sem tela em branco. Testes nas Tasks 3 e 4.
5. **Busca no glossário sem resultado ou com acento** ("volatilidade" acha "vol"; "exercicio" acha "exercício"): a busca ignora acento e maiúsculas, e "nenhum termo encontrado" aparece quando não acha. Teste na Task 4.

---

### Task 1: exemplos das 18 operações no domínio e na API

**Files:**
- Create: `src/options_engine/domain/learn/__init__.py`, `src/options_engine/domain/learn/examples.py`
- Create: `src/options_engine/adapters/inbound/web/aprender.py` (router)
- Modify: `src/options_engine/config/web_app.py` (incluir o router, sem exigir perfil)
- Test: `tests/learn/test_examples.py`, `tests/web/test_aprender_api.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, slots=True) class ExampleLeg: option_type: OptionType; side: Side; strike: float; premium: float; quantity: int`
  - `@dataclass(frozen=True, slots=True) class Example: key: str; name: str; family: Family; spot: float; legs: tuple[ExampleLeg, ...]; stock_quantity: int; net_premium: float; scenarios: tuple[tuple[float, float], ...]; breakevens: tuple[float, ...]; max_gain: float | None; max_loss: float | None; curve: tuple[tuple[float, float], ...]` — `net_premium` > 0 recebe, < 0 paga (só opções); `stock_quantity` 0 ou 100; `max_loss` positivo.
  - `example(template: Template) -> Example` e `examples() -> tuple[Example, ...]` (na ordem de `TEMPLATES`).
  - `GET /api/aprender/exemplos` → lista com `chave, nome, familia, spot, pernas:[{tipo, lado, strike, premio, quantidade}], acoes, premio_liquido, cenarios:[{preco, resultado}], empates:[float], ganho_maximo: float|null, perda_maxima: float|null, curva:[[preco, resultado]]`. Responde sem perfil aberto.

- [ ] **Step 1: Testes que falham** (`tests/learn/test_examples.py`)
  - `test_todo_modelo_tem_exemplo`: `[e.key for e in examples()] == [t.key for t in TEMPLATES]`.
  - `test_venda_coberta`: legs = uma call vendida de strike 52,00 com prêmio `round(bs_price(50, 52, 21/252, 0.14, 0.30, is_call=True), 2)` (= 1,14), quantidade 100; `stock_quantity == 100`; `net_premium == 114.0`; cenários `[(45, -386.0), (50, 114.0), (55, 314.0)]`; `breakevens == (48.86,)` (com tolerância de 1e-9); `max_gain == 314.0`; `max_loss == 4886.0`.
  - `test_resultado_vem_do_dominio`: para cada exemplo, montar a `Strategy` pelo `Template.build` com as pernas do exemplo e conferir que cada cenário e cada ponto da curva é igual a `expiry_pnl(strategy, preco)` e que `(breakevens, max_gain, -min)` batem com `expiry_summary(strategy)` (o mínimo convertido em perda positiva).
  - `test_sem_limite`: `straddle_vendido.max_loss is None`, `compra_call.max_gain is None`, `put_protetora.max_gain is None`.
  - `test_strikes_seguem_o_passo_do_modelo`: `iron_condor_vendido` tem strikes `(46, 48, 52, 54)`.
  - API (`tests/web/test_aprender_api.py`): `GET /api/aprender/exemplos` sem perfil → 200, 18 itens, o da venda coberta com `"premio_liquido": 114.0`, `"cenarios": [{"preco": 45.0, "resultado": -386.0}, …]`, `"perda_maxima": 4886.0`; o do straddle vendido com `"perda_maxima": null`.

- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** O símbolo das pernas é sintético (`PETR4` + tipo e strike, só para a `Strategy` validar); termos com vencimento fixo de exemplo e estilo europeu. Domínio stdlib-only (import-linter).
- [ ] **Step 4: Rodar e ver passar** (suítes tocadas + mypy, ruff, format, import-linter).

### Task 2: a aba e as rotas

**Files:**
- Create: `frontend/src/paginas/Aprender.tsx`, `frontend/src/paginas/Aprender.test.tsx`
- Create: `frontend/src/api/aprender.ts` (tipo `Exemplo` e `carregarExemplos()`)
- Modify: `frontend/src/App.tsx` (rotas com e sem perfil), `frontend/src/componentes/Shell.tsx` (item "Aprender" entre Carteira e Alertas), `frontend/src/paginas/Perfis.tsx` (link "Como usar o app")

**Interfaces:**
- Produces: rotas `/aprender` (→ `/aprender/comece`), `/aprender/comece`, `/aprender/operacoes`, `/aprender/operacoes/:modelo`, `/aprender/termos`, `/aprender/telas`, nas duas árvores de rota do `App` (com e sem perfil). Sub-abas como `NavLink`s; o conteúdo de cada sub-aba é um componente (Tasks 3, 4 e 5), nesta task com um corpo provisório.

- [ ] **Step 1: Testes que falham**
  - com perfil: o menu tem "Aprender" entre "Carteira" e "Alertas"; `/aprender` mostra a sub-aba "Comece aqui" ativa; clicar em "Operações", "Termos" e "Telas do app" troca o endereço.
  - sem perfil: a tela de perfis tem o link "Como usar o app" para `/aprender/comece`, e `/aprender/termos` abre (não redireciona para `/perfis`).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Sem perfil, a página aparece sem o menu lateral, com um link "voltar aos perfis".
- [ ] **Step 4: Rodar e ver passar.**

### Task 3: sub-aba Operações

**Files:**
- Create: `frontend/src/aprender/operacoes.ts` (textos), `frontend/src/aprender/Operacoes.tsx`, `frontend/src/aprender/Operacoes.test.tsx`, `frontend/src/aprender/GraficoExemplo.tsx`
- Modify: `frontend/src/paginas/Aprender.tsx` (liga a sub-aba), `frontend/src/tema.css`

**Interfaces:**
- Consumes: `carregarExemplos()` (Task 2/1).
- Produces: `TEXTOS_OPERACOES: Record<string, { etiquetas: string[]; oQueE: string; quandoUsar: string; comoMontar: string; oQuePodeDarErrado: string; noApp: string }>` com as 18 chaves de `TEMPLATES`; o componente `Termo({ id, children })` vem da Task 4 (nesta task, os termos dos textos ainda sem link).

- [ ] **Step 1: Testes que falham**
  - a lista à esquerda tem as 4 famílias e as 18 operações, na ordem do catálogo; `/aprender/operacoes` abre a primeira (venda coberta); `/aprender/operacoes/iron_condor_vendido` abre a dele; `/aprender/operacoes/xyz` abre a primeira, sem erro.
  - a venda coberta mostra os blocos "O que é", "Quando usar", "Como montar", "Exemplo", "O que pode dar errado", "No app"; o exemplo diz "PETR4 a R$ 50,00", "vende 100 calls de strike R$ 52,00 a R$ 1,14", "recebe R$ 114,00", a tabela de cenários com R$ 45,00 → "perde R$ 386,00", R$ 50,00 → "ganha R$ 114,00", R$ 55,00 → "ganha R$ 314,00", "empata em R$ 48,86", "ganho máximo R$ 314,00", "perda máxima R$ 4.886,00", e o aviso "exemplo, sem custos nem IR".
  - straddle vendido: "perda máxima sem limite".
  - o gráfico (`role="img"` com nome "Resultado no vencimento de <operação>") aparece.
  - "Montar uma venda coberta no Montador": com perfil, navega para `/montador?modelo=venda_coberta`; sem perfil, desabilitado com "abra um perfil primeiro".
  - `TEXTOS_OPERACOES` tem as 18 chaves de `TEMPLATES` e nenhum texto vazio (teste de completude contra a lista da API falsa com as 18 chaves).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** O "Exemplo" é montado dos números da API (pernas, prêmio líquido, cenários, empates, máximos), formatado com `formatacao.ts`. O gráfico usa ECharts como o `GraficoPayoff` (linha do resultado, linha do zero, marca do spot). Os textos seguem os fatos da tabela abaixo, em frases curtas e simples; nenhum número no texto (os números vêm do exemplo). Para cada operação:

  | chave | precisa ter | cenário | risco em uma frase |
  |---|---|---|---|
  | venda_coberta | a ação | parado ou subindo devagar | perde se a ação cair (o prêmio só amortece); acima do strike, é obrigado a vender |
  | put_coberta | caixa para comprar a ação | parado ou subindo | se cair abaixo do strike, compra a ação mais cara que o mercado |
  | trava_alta_put | margem para a perda máxima | não cair | perde a largura da trava menos o crédito se cair |
  | trava_baixa_call | margem para a perda máxima | não subir | perde a largura menos o crédito se subir |
  | compra_call | o prêmio | alta forte | perde o prêmio se não subir além do empate |
  | compra_put | o prêmio | queda forte | perde o prêmio se não cair além do empate |
  | trava_alta_call | o débito | alta moderada | perde o débito se não subir; o ganho tem teto |
  | trava_baixa_put | o débito | queda moderada | perde o débito se não cair; o ganho tem teto |
  | straddle_comprado | o prêmio das duas | movimento grande, para qualquer lado | perde tudo se a ação ficar parada |
  | straddle_vendido | margem alta | parado | perda sem limite se a ação andar muito |
  | strangle_comprado | o prêmio das duas | movimento grande | perde tudo se ficar na faixa |
  | strangle_vendido | margem alta | dentro da faixa | perda sem limite se sair da faixa |
  | iron_condor_vendido | margem para a perda máxima | dentro da faixa | perde a largura menos o crédito se sair da faixa |
  | iron_condor_comprado | o débito | fora da faixa | perde o débito se ficar na faixa |
  | borboleta_comprada | o débito | parar perto do strike do meio | perde o débito se se afastar |
  | borboleta_vendida | margem para a perda máxima | se afastar do meio | perde se parar perto do meio |
  | put_protetora | a ação | quer manter a ação com seguro | o custo do seguro; o seguro vence |
  | collar | a ação | quer seguro barato | abre mão da alta acima da call vendida |

  O bloco "No app" diz em que família do Book a operação aparece; as três que o Book não varre (`straddle_vendido`, `iron_condor_comprado`, `borboleta_vendida`) dizem que só se montam no Montador.
- [ ] **Step 4: Rodar e ver passar.**

### Task 4: sub-aba Termos e o componente de termo

**Files:**
- Create: `frontend/src/aprender/termos.ts`, `frontend/src/aprender/Termos.tsx`, `frontend/src/aprender/Termos.test.tsx`, `frontend/src/componentes/Termo.tsx`, `frontend/src/componentes/Ajuda.tsx`, `frontend/src/componentes/Termo.test.tsx`
- Modify: `frontend/src/aprender/operacoes.ts` e `Operacoes.tsx` (termos dos textos viram links), `frontend/src/paginas/Aprender.tsx`

**Interfaces:**
- Produces:
  - `TERMOS: { id: string; titulo: string; texto: string; exemplo: string; onde: string }[]` com os ids abaixo.
  - `Termo({ id, children })`: o texto sublinhado que leva a `/aprender/termos#<id>`.
  - `Ajuda({ id })`: um "?" pequeno (botão-link com `aria-label="O que é <titulo>?"`) que leva a `/aprender/termos#<id>`.

  Ids (estes exatos; os "?" da Task 6 usam estes): `call`, `put`, `strike`, `premio`, `vencimento`, `dias-uteis`, `lote`, `exercicio`, `atribuicao`, `po`, `americana-europeia`, `delta`, `gamma`, `theta`, `vega`, `iv`, `iv-30`, `hv-21`, `iv-rank`, `percentil`, `vol-cara-barata`, `spread`, `negocios`, `preco-executavel`, `preco-de-zerar`, `ao-vivo-fim-de-dia`, `cadastro`, `cotahist`, `custos-ir`, `anualizado`, `retorno-sobre-risco`, `chance-de-lucro`, `probabilidade-de-exercicio`, `empate`, `ganho-perda-maximos`.

- [ ] **Step 1: Testes que falham**
  - a lista mostra todos os termos em ordem alfabética do título; cada termo tem o título como `heading` e um elemento com `id` igual ao id;
  - a busca filtra por título e texto, ignorando acento e maiúsculas ("exercicio" acha "Exercício"; "VOL" acha "Vol cara, normal e barata"); sem resultado, "Nenhum termo encontrado";
  - `/aprender/termos#delta` rola até o termo e o destaca (classe ou `aria-current`); um `#` inexistente mostra a lista inteira sem erro;
  - `Termo` e `Ajuda` renderizam links para `/aprender/termos#<id>`; `Ajuda` tem o nome acessível "O que é <título>?";
  - todo id da lista acima existe em `TERMOS` (teste de completude).
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar.** Cada termo: uma a três frases simples, um exemplo curto com PETR4 e onde aparece no app. "Chance de lucro" diz que é calculada pelo modelo e **sem custos nem IR**; "Ganho e perda máximos" dizem que são líquidos de custos e IR no Book e no Montador. Nos textos das operações (Task 3), os termos do glossário viram `Termo`.
- [ ] **Step 4: Rodar e ver passar.**

### Task 5: sub-abas Comece aqui e Telas do app

**Files:**
- Create: `frontend/src/aprender/Comece.tsx`, `frontend/src/aprender/Telas.tsx`, `frontend/src/aprender/Comece.test.tsx`
- Modify: `frontend/src/paginas/Aprender.tsx`

- [ ] **Step 1: Testes que falham**
  - Comece aqui tem os passos, nesta ordem: "Crie o seu perfil", "Baixe os arquivos da semana" (com link para Arquivos B3), "Abra o Tryd", "Veja as melhores operações no Book", "Confira e ajuste no Montador", "Registre o que executou na Carteira", "No vencimento" (com o que acontece com pó, exercício e atribuição);
  - Telas do app tem uma seção por aba do menu (Mercado, Montador, Book, Carteira, Aprender, Alertas, Arquivos B3) e uma para o indicador do topo ("Ao vivo (Tryd)", "Atrasado", "Fim de dia (B3)").
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** em frases curtas, com `Termo` nos termos do glossário. A rotina da B3 repete o que a aba Arquivos B3 diz (o `pesquisa-pregao.zip` e o COTAHIST anual, uma vez por semana).
- [ ] **Step 4: Rodar e ver passar.**

### Task 6: os "?" pelo app e o Montador com modelo no endereço

**Files:**
- Modify: `frontend/src/paginas/Book.tsx`, `frontend/src/componentes/CartaoDestaque.tsx`, `frontend/src/componentes/TabelaFamilia.tsx`, `frontend/src/componentes/TabelaCadeia.tsx`, `frontend/src/componentes/ResumoEstrutura.tsx`, `frontend/src/paginas/Carteira.tsx` (só onde o rótulo já existe), `frontend/src/paginas/Montador.tsx`
- Test: os testes dos mesmos arquivos

- [ ] **Step 1: Testes que falham**
  - Book: o link "o que é vol barata ou cara?" ao lado das etiquetas vai a `#vol-cara-barata`; no cartão, "?" em "ganha até" e "perde até" (`#ganho-perda-maximos`) e em "chance de lucro" (`#chance-de-lucro`); na tabela compacta, "?" nos cabeçalhos Ganha até, Perde até e Chance de lucro;
  - cadeia: "?" nos cabeçalhos IV (`#iv`) e Delta (`#delta`) (uma vez por cabeçalho, não por coluna repetida de calls e puts — escolha do implementador, desde que não polua);
  - Montador: `/montador?modelo=venda_coberta` escolhe o modelo quando a cadeia chega ("aguardando a cadeia" antes); com um modelo que não cabe na cadeia, aparece a mensagem de erro que o Montador já tem; `?modelo=xyz` é ignorado.
- [ ] **Step 2: Rodar e ver falhar.**
- [ ] **Step 3: Implementar** com `Ajuda` (Task 4). O modelo do endereço é aplicado uma vez só.
- [ ] **Step 4: Rodar e ver passar.**

### Task 7: conferência e entrega para revisão dos textos (controlador)

- [ ] **Step 1:** build, reiniciar o app, prints da aba Aprender (as quatro sub-abas, uma operação de cada família) em 1366 e 1920 px, com e sem perfil.
- [ ] **Step 2:** gate completo.
- [ ] **Step 3:** entregar ao autor os textos para revisão (as 18 operações, os termos, Comece aqui e Telas) antes do commit; aplicar as correções que ele pedir.

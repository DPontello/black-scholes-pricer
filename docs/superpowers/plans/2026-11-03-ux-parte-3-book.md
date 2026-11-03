# UX parte 3: Book mais simples — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o Book abre em "Melhores operações de hoje", com o melhor de cada família em cartões curtos (o que fazer, um número grande, ganha até / perde até / chance de lucro e uma frase curta), as abas viram tabelas compactas com linha expansível, e o preset, as referências e as exclusões ficam recolhidos.

**Architecture:** o `BookService` passa a analisar o pedido de cada item com um `StrategyBuilderService` montado sobre o **fim de dia** (os mesmos preços do book) e leva o resultado no vencimento (`BookOutcome`) junto da `BookEntry`; uma frase curta por estrutura sai do domínio (`domain/book/frases.py`). A API do book ganha `resultado` e `porque_curto`. No frontend, a página `Book` é refeita com dois componentes novos (`CartaoDestaque`, `TabelaFamilia`); o `ItemBook` sai.

**Tech Stack:** Python 3.12+ (FastAPI, pydantic), React + TypeScript (Vite, Vitest, Testing Library).

**Spec:** [`docs/superpowers/specs/2026-11-03-ux-book-aprender-design.md`](../specs/2026-11-03-ux-book-aprender-design.md), §5 (e §2 para a entrega).

## Global Constraints

- Português em código, comentários, testes e textos; comentário só para um porquê não óbvio.
- **Nenhum agente faz `git commit`, `merge` ou `push`**: o autor commita.
- Worktree `/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer-dev`. Python: `PY=/var/home/HugoPontello/Desktop/Programação/black-scholes-pricer/.venv/bin/python` com `PYTHONPATH=src`. Por tarefa: pytest das suítes tocadas, `$PY -m mypy`, `$PY -m ruff check .`, `$PY -m ruff format --check .`, `$(dirname $PY)/lint-imports --no-cache`; frontend `npm --prefix frontend run verificar`. Gate completo no fim da parte.
- **As regras do Book não mudam** (famílias, critérios, filtros, presets, ordem dentro de cada família). Só a apresentação e os números novos.
- **Destaque = `itens[0]` da família** na ordem que a API já devolve (autor, 03/11); só item executável vira destaque (os `itens` já são só os executáveis; `referencias` são os outros).
- **Ganha até / perde até / chance de lucro** são **líquidos** (`net_max_gain`, `net_max_loss`, `probability_of_profit` do `ExpiryResult` do Montador), com os **preços do fim de dia** do book. `None` = sem limite. "Perde até" é mostrado como valor positivo.
- Vol em palavras: regime `baixa` → **barata**, `neutra` → **normal**, `alta` → **cara**; com `regime_pela_hv`, a etiqueta diz "(pela HV)".
- Nenhum número que o Book mostra hoje some: todos os `numeros` e a frase longa (`porque`) ficam na linha expandida.
- Os "?" (links para o glossário) **não** entram nesta parte (spec §2: entram com a aba Aprender).

## Review Focus

1. **Item cuja análise falha** (série sem preço, vencimento fora do calendário, erro de domínio): `resultado` sai `null` e o cartão/linha mostra "—", sem derrubar o book. Teste na Task 1.
2. **Família sem nenhum item executável** (Volatilidade costuma vir vazia): o cartão diz "Nada hoje em Volatilidade" com o motivo curto e a aba continua acessível. Teste na Task 3.
3. **Ganho ou perda sem limite** (straddle/strangle comprados; strangle vendido; put protetora com a ação): "sem limite", nunca `R$ 0` nem "—". Testes nas Tasks 1 e 3.
4. **Book vazio** (sem COTAHIST, `pregao: null`, todos os ativos indisponíveis): a página diz o motivo e não mostra cartões quebrados. Teste na Task 3.
5. **Book mais lento**: a análise por item custa ~15 ms (medido em 03/11); com ~20 itens, ~0,3 s. Sem teste; o controlador mede o `GET /api/book` antes e depois na Task 4.

---

### Task 1: resultado no vencimento de cada item do book

**Files:**
- Modify: `src/options_engine/application/ports/book.py` (`BookOutcome` novo; `BookEntry.outcome`)
- Modify: `src/options_engine/application/use_cases/book.py` (`BookService`: parâmetro `builder`, `_view`/`_entry` analisam o pedido)
- Modify: `src/options_engine/config/web_app.py` (um segundo `StrategyBuilderService` sobre o `end_of_day`, passado ao `BookService`)
- Modify: `src/options_engine/adapters/inbound/web/book.py` (`ResultadoOut`, `ItemOut.resultado`)
- Test: `tests/application/test_book.py` (com o falso de `tests/application/_book_falso.py`), `tests/web/test_book_api.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, slots=True) class BookOutcome: max_gain: float | None; max_loss: float | None; probability_of_profit: float` — `max_gain = net_max_gain`, `max_loss = abs(net_max_loss)` (positivo), `None` = sem limite.
  - `BookEntry.outcome: BookOutcome | None = None` (último campo, com padrão).
  - `BookService(..., builder: StrategyBuilderUseCase | None = None)` (keyword, último). Sem `builder`, `outcome` fica `None`.
  - JSON do item: `"resultado": {"ganha_ate": float | null, "perde_ate": float | null, "chance_de_lucro": float, "ganha_ate_texto": str, "perde_ate_texto": str, "chance_texto": str} | null`. Textos: `R$ 350,11` (formato do `format_metric` de reais), `sem limite` quando `null`, `62,0%`.

- [ ] **Step 1: Testes que falham**
  - `test_item_do_book_leva_o_resultado_liquido_do_montador`: com um `builder` falso que devolve um `BuilderAnalysis` com `at_expiry=ExpiryResult(net_max_gain=350.11, net_max_loss=-16433.11, probability_of_profit=0.62, ...)`, a `BookEntry` do item tem `outcome == BookOutcome(350.11, 16433.11, 0.62)`; o falso recebe o `request` do item (mesmo `BuilderRequest`).
  - `test_ganho_sem_limite_vira_none`: `net_max_gain=None` → `outcome.max_gain is None`.
  - `test_analise_que_falha_deixa_o_resultado_vazio`: o falso levanta `UnderlyingUnavailableError` (ou devolve `at_expiry=None`) → `outcome is None`, e o book segue com o item.
  - `test_sem_builder_nao_ha_resultado`: `BookService` sem `builder` → `outcome is None` em todos os itens.
  - API: o item com `outcome=BookOutcome(350.11, 16433.11, 0.62)` sai com `"resultado": {"ganha_ate": 350.11, "perde_ate": 16433.11, "chance_de_lucro": 0.62, "ganha_ate_texto": "R$ 350,11", "perde_ate_texto": "R$ 16.433,11", "chance_texto": "62,0%"}`; com `max_gain=None`, `"ganha_ate": null` e `"ganha_ate_texto": "sem limite"`; com `outcome=None`, `"resultado": null`.

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar**
  - No `BookService`, analisar itens **e** referências (as referências podem falhar por falta de preço; aí `None`). Exceções do domínio (`DomainError`) viram `None`; não capturar exceção genérica.
  - No `config/web_app.py`, o segundo `StrategyBuilderService` é igual ao do Montador, trocando o `market` pelo `end_of_day` (o `EndOfDayMarket` que já é montado ali).

- [ ] **Step 4: Rodar e ver passar** (suítes tocadas + mypy, ruff, format, import-linter).

### Task 2: frase curta por estrutura

**Files:**
- Create: `src/options_engine/domain/book/frases.py`
- Modify: `src/options_engine/adapters/inbound/web/book.py` (`ItemOut.porque_curto`)
- Test: `tests/book/test_frases.py`, `tests/web/test_book_api.py`

**Interfaces:**
- Produces: `short_reason(template_key: str) -> str` em `domain/book/frases.py`; JSON do item: `"porque_curto": str`.

- [ ] **Step 1: Testes que falham**
  - `test_toda_estrutura_do_catalogo_tem_frase_curta`: para cada `modelo.key` de `TEMPLATES` (`domain/model/templates.py`), `short_reason(chave)` é um texto não vazio, termina em ponto e **não tem dígito** (a frase não repete números).
  - `test_frase_da_venda_coberta`: `short_reason("venda_coberta") == "Renda com as suas ações: recebe o prêmio e aceita vender no strike."`.
  - `test_chave_desconhecida_e_erro`: `short_reason("x")` levanta `KeyError`.
  - API: o item de venda coberta sai com `"porque_curto"` igual à frase acima.

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar** com este texto exato (o autor revisa na entrega; as chaves são as do catálogo):

  | chave | frase |
  |---|---|
  | `venda_coberta` | Renda com as suas ações: recebe o prêmio e aceita vender no strike. |
  | `put_coberta` | Renda com caixa: recebe o prêmio e aceita comprar a ação no strike. |
  | `trava_alta_put` | Renda com risco limitado: recebe um crédito e já sabe a perda máxima. |
  | `trava_baixa_call` | Renda com risco limitado: recebe um crédito e já sabe a perda máxima. |
  | `compra_call` | Call barata pela vol: ganha se a ação subir. |
  | `compra_put` | Put barata pela vol: ganha se a ação cair. |
  | `trava_alta_call` | Aposta na alta com perda limitada. |
  | `trava_baixa_put` | Aposta na queda com perda limitada. |
  | `straddle_comprado` | Vol barata: ganha se a ação andar muito para qualquer lado. |
  | `straddle_vendido` | Vol cara: ganha se a ação ficar parada; a perda não tem limite. |
  | `strangle_comprado` | Vol barata: ganha se a ação sair da faixa para qualquer lado. |
  | `strangle_vendido` | Vol cara: ganha se a ação ficar na faixa; a perda não tem limite. |
  | `iron_condor_vendido` | Vol cara: ganha se a ação ficar na faixa, com perda limitada. |
  | `iron_condor_comprado` | Vol barata: ganha se a ação sair da faixa, com perda limitada. |
  | `borboleta_comprada` | Vol cara: ganha se a ação parar perto do strike do meio. |
  | `borboleta_vendida` | Vol barata: ganha se a ação se afastar do strike do meio. |
  | `put_protetora` | Seguro para as suas ações até o vencimento. |
  | `collar` | Seguro barato: protege a queda e abre mão de parte da alta. |

  Se o catálogo tiver uma chave com outro nome, use o nome do catálogo e relate a diferença.

- [ ] **Step 4: Rodar e ver passar.**

### Task 3: a página do Book refeita

**Files:**
- Modify: `frontend/src/api/book.ts` (`ItemBook.resultado`, `ItemBook.porque_curto`)
- Create: `frontend/src/componentes/CartaoDestaque.tsx`, `frontend/src/componentes/CartaoDestaque.test.tsx`
- Create: `frontend/src/componentes/TabelaFamilia.tsx`, `frontend/src/componentes/TabelaFamilia.test.tsx`
- Modify: `frontend/src/paginas/Book.tsx`, `frontend/src/paginas/Book.test.tsx`
- Delete: `frontend/src/componentes/ItemBook.tsx`, `frontend/src/componentes/ItemBook.test.tsx` (o que eles testavam passa para os componentes novos)
- Modify: `frontend/src/tema.css`

**Interfaces:**
- Consumes: `resultado` e `porque_curto` das Tasks 1 e 2.
- Produces: `CartaoDestaque({ familia: Familia; rotulo: string; item: ItemBook | null; motivoVazio: string })`; `TabelaFamilia({ familia: FamiliaBook })`.

- [ ] **Step 1: Testes que falham**
  - `Book.test.tsx`:
    - `test("o título é Melhores operações de hoje, com o pregão")`: `getByRole("heading", { name: "Melhores operações de hoje" })` e o texto do pregão.
    - `test("o preset fica fechado e abre no ajustar")`: o campo "Delta mínimo" não está visível até clicar em "ajustar"; o texto "Critérios: Moderado" aparece. O teste antigo de trocar o preset passa a clicar em "ajustar" antes.
    - `test("a vol vira etiquetas com palavras")`: contexto com `regime: "baixa"` → "BOVA11 · vol barata"; `"alta"` → "vol cara"; `"neutra"` → "vol normal"; `regime_pela_hv: true` → "(pela HV)"; contexto com `motivo` → a etiqueta mostra o motivo.
    - `test("um cartão por família, com o primeiro item")`: quatro cartões na ordem Renda, Volatilidade, Direcionais, Proteção; o de Renda mostra o `nome` e o `ativo` do `itens[0]`.
    - `test("família sem item diz nada hoje com o motivo")`: Volatilidade com `itens: []` e `referencias` não vazias → "Nada hoje em Volatilidade" e "sem preço de compra e venda agora"; com `referencias: []` e `exclusoes` não vazias → "nenhuma série passou nos filtros"; com tudo vazio → "nada passou nos filtros do preset".
    - `test("book sem pregão diz o motivo e não mostra cartões")`: `pregao: null`, famílias vazias → a mensagem de importar o COTAHIST e nenhum cartão.
    - Os testes antigos de referências, exclusões, visão e erro seguem, ajustados ao lugar novo (referências dentro de um `<details>` recolhido).
  - `CartaoDestaque.test.tsx`:
    - mostra a família, "venda coberta · BOVA11 · vence 06/11/2026 (4 dias úteis)", a linha "vender 100 BOVAK168W1 a 1,12 · comprar 100 BOVA11", o número grande (`criterio.texto` com `criterio.rotulo`), "ganha até R$ 350,11", "perde até R$ 16.433,11", "chance de lucro 62,0%", o `porque_curto` e o botão "Abrir no montador";
    - `resultado: null` → os três números mostram "—";
    - `ganha_ate: null` → "ganha até sem limite";
    - os `rotulos` aparecem pequenos;
    - "Abrir no montador" navega para `/montador?ativo=BOVA11` com o `pedido` no estado da rota (o mesmo comportamento do `ItemBook` de hoje).
  - `TabelaFamilia.test.tsx`:
    - uma linha por item com: operação (nome, ativo e strikes), vence (data e dias úteis), critério, ganha até, perde até, chance e "abrir";
    - clicar na linha expande o detalhe com todos os `numeros` (rótulo e texto) e o `porque` longo; clicar de novo fecha;
    - referências ficam num `<details>` "Referências sem preço de compra e venda agora (N)" e exclusões em "Fora do book por dado ruim (N)", os dois fechados.

- [ ] **Step 2: Rodar e ver falhar.**

- [ ] **Step 3: Implementar**
  - Ordem da página: título e pregão · "Critérios: <preset> · ajustar ▸" (abre o `EditorPreset` de hoje) · avisos de indisponíveis · etiquetas de vol · "O melhor de cada família" (4 cartões em grade de colunas automáticas, mín. ~280 px) · abas com contagem (`Renda (N)`) · `TabelaFamilia` da aba (a Direcionais mantém o formulário "com visão" no topo).
  - O nome do preset vem de `perfil.book.preset` (`conservador`, `moderado`, `agressivo`, `personalizado`, com a primeira letra maiúscula).
  - Linha das pernas no cartão: `vender`/`comprar` + quantidade + ticker + "a" + prêmio (`formatarPreco`), separadas por " · "; a ação entra como "comprar 100 BOVA11" (ou "… da carteira").
  - Estado por texto além da cor; perda em `--baixa`, número grande em `--alta`.

- [ ] **Step 4: Rodar e ver passar** (`npm --prefix frontend run verificar`).

### Task 4: conferência (controlador)

- [ ] **Step 1:** `npm --prefix frontend run build`, reiniciar o app e medir o `GET /api/book` (tempo) contra o de antes da parte.
- [ ] **Step 2:** prints do Book em 1280, 1366, 1920 e 2560 px: sem tabela cortada, sem painel esticado, cartões legíveis; um cartão de cada família (ou "Nada hoje"), uma linha expandida.
- [ ] **Step 3:** gate completo e entrega ao autor, com as 18 frases curtas para revisão.

# App de opções — Semana 3 (Book e Análise) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o histórico de IV (IV de 30 dias úteis por pregão, HV 21, IV rank e percentil) calculado dos COTAHIST da biblioteca; o book de recomendações das quatro famílias para a lista do perfil, por regras transparentes e com presets salvos no perfil, cada item com o porquê e "abrir no montador"; e a aba Análise no Mercado com o preço, a IV contra a HV, o smile e a estrutura a termo.

**Architecture:** o domínio ganha `domain/analytics` (IV de 30 dias, rank, percentil, regime de vol) e `domain/book` (item, presets e um módulo puro por família sobre a cadeia). Um adapter lê os COTAHIST em fluxo e guarda a IV de cada pregão em sqlite. Em `application/`, o `BookService` usa sempre a cadeia de fim de dia e o `MarketAnalysisService` usa a cadeia do momento com o histórico. Rotas novas na API e duas telas React (Book e a aba Análise), com ECharts.

**Tech Stack:** o das semanas 1 e 2, sem dependência nova.

**Spec:** [`specs/2026-11-02-semana-3-book-analise-design.md`](../specs/2026-11-02-semana-3-book-analise-design.md), que detalha o desenho geral [`specs/2026-10-28-app-opcoes-design.md`](../specs/2026-10-28-app-opcoes-design.md).

## Global Constraints

- **Commits só com a autorização do autor**, um por tarefa, com a identidade `Hugo Pontello <136363953+DPontello@users.noreply.github.com>` e sem linha de coautoria. Branch a partir da `development` (`feat/app-semana-3`); merge na `development` com `--no-ff`; nunca apagar branches.
- Português em código, testes (`test_...` em pt-BR), mensagens de tela e de erro. **Comentários só para um porquê não óbvio** (pedido do autor).
- `domain/` e `application/` stdlib-only (import-linter). `dependencies = []` continua vazio.
- Lado de book ausente é `None` (ADR-0003); prêmio pelo lado certo (ADR-0004); custos e IR pela ADR-0005; call americana como europeia só rotulada e put americana sem avaliação de hoje (ADR-0002).
- Vol em BUSINESS_252: τ = dias úteis / 252; taxa do CDI convertida para contínua pelo `RiskFreeRate`, nunca à mão.
- Nenhum dado real do Tryd ou da B3 no repositório; testes com `tmp_path` e fixtures sintéticas (`tests/data/cotahist`, `tests/application/_mercado_falso.py`).
- Constantes desta semana: IV no prazo de **30 dias úteis**; vencimento mínimo de **5 dias úteis** no histórico; janela do rank de **252 pregões**, mínimo de **60**; regime alta com rank >= 50% e IV >= HV, baixa com rank <= 30% e IV <= HV (sem rank, margem de 10% na IV contra a HV); **5 itens** por estrutura; presets da spec §3.2.
- Gates ao fim de cada task, com `PYTHONPATH=src` e o venv (`.venv/Scripts/` no Windows, `.venv/bin/` no Linux):
  `python -m pytest -q -p no:cacheprovider --cov && python -m mypy && python -m ruff check . && python -m ruff format --check . && lint-imports --no-cache`
  e, nas tasks com frontend, `npm --prefix frontend run verificar` e `npm --prefix frontend run build`.

## Review Focus

1. **Unidades da vol:** variância total em τ de dias úteis / 252 na interpolação de 30 dias; extrapolação marcada; buraco nunca interpolado. Task 1.
2. **Iliquidez premiada:** só EXECUTAVEL no book; filtros de liquidez em todas as pernas; INDICATIVO e TEORICO só nas referências. Tasks 4 a 8.
3. **Sinal e risco:** perda ilimitada (strangle vendido) só no Arrojado e rotulada; risco máximo do preset só nas estruturas sem ação. Tasks 5 e 8.
4. **Dado parado como ao vivo:** o book sempre diz o pregão do fim de dia; "abrir no montador" reprecifica pela cadeia do momento. Tasks 8 e 10.
5. **Perfil antigo:** o campo `book` é opcional na leitura do perfil. Task 3.

---

## Parte A — Histórico de IV

### Task 1: IV de 30 dias, rank, percentil e regime de vol

**Files:**
- Create: `src/options_engine/domain/analytics/__init__.py`, `domain/analytics/volatility.py`
- Test: `tests/analytics/__init__.py`, `tests/analytics/test_volatility.py`

**Interfaces:**
- Produces: `ExpiryVol(business_days: int, vol: float)`; `iv_at_horizon(points: Sequence[ExpiryVol], horizon_days: int = 30, min_days: int = 5) -> HorizonVol | None`, com `HorizonVol(vol, extrapolated: bool)`, interpolando a variância total linearmente em τ.
- Produces: `iv_rank(history: Sequence[float], today: float) -> float | None` e `iv_percentile(...)` na janela de 252, `None` com menos de 60.
- Produces: `VolRegime` (`ALTA`, `BAIXA`, `NEUTRA`) e `vol_regime(iv: float, hv: float, rank: float | None) -> tuple[VolRegime, bool]`, com o `bool` dizendo se o regime veio só da IV contra a HV.

- [ ] **Step 1: Testes que falham**, com números à mão:
  - 20 e 40 dias úteis a 30% e 34%: a IV de 30 sai da variância total, não da média das vols;
  - só vencimentos depois de 30 dias: vale o mais perto, extrapolado;
  - vencimento com menos de 5 dias fica fora;
  - rank e percentil numa série de 100 pregões; com 59 pregões, `None`;
  - os três regimes, e o regime sem rank pela margem de 10%.
- [ ] **Step 2: Implementar** (stdlib, `fsum`).

### Task 2: Histórico de IV pelos COTAHIST da biblioteca

**Files:**
- Create: `src/options_engine/adapters/outbound/cotahist/vol_history.py`
- Modify: `src/options_engine/application/ports/outbound.py` (`VolHistoryPort`), `adapters/outbound/cotahist/parser.py` só se a leitura por pregão precisar de um gancho
- Test: `tests/adapters/cotahist/test_vol_history.py`

**Interfaces:**
- Produces: `DailyVol(session: date, close: float, iv30: float | None, extrapolated: bool, hv21: float | None)` e `VolHistoryPort.history(symbol) -> tuple[DailyVol, ...] | str` (o `str` é o motivo: sem COTAHIST, ativo desconhecido).
- Produces: `CotahistVolHistory(loader: LibraryLoader, calendar, cdi_annual: Callable[[], float])`, com a leitura em fluxo (`iter_cotahist` com `keep` no à vista e nas opções) e o cache sqlite `vol_history.sqlite` na raiz da biblioteca, por (pregão, ativo).

- [ ] **Step 0: Conferir no anual real** (local, sem commitar o arquivo) se os registros vêm ordenados por pregão; anotar no ledger. Se não vierem, agrupar em memória só as raízes pedidas.
- [ ] **Step 1: Testes que falham** com a fixture de 17 pregões:
  - IV 30 de PETR4 num pregão conferida contra o smile do adapter COTAHIST daquele pregão;
  - séries rejeitadas no adapter (book cruzado, strike corrigido) ficam fora;
  - segunda leitura sai do cache, sem reler o arquivo; um diário novo calcula só o pregão novo;
  - sem COTAHIST, o motivo.
- [ ] **Step 2: Implementar.**

## Parte B — Book

### Task 3: Presets do book no domínio e no perfil

**Files:**
- Create: `src/options_engine/domain/book/__init__.py`, `domain/book/presets.py`
- Modify: `src/options_engine/domain/model/profile.py` (`Profile.book: BookSettings | None = None`), `adapters/outbound/storage/profiles.py` (campo `book` opcional no JSON), `application/use_cases/profiles.py` e `application/ports/inbound.py` (`set_book_settings`), `adapters/inbound/web/profiles.py` (`PUT /api/perfil/book`)
- Test: `tests/book/__init__.py`, `tests/book/test_presets.py`, `tests/adapters/storage/test_profiles.py`, `tests/web/test_profiles_api.py`

**Interfaces:**
- Produces: `BookPreset` (`CONSERVADOR`, `MODERADO`, `ARROJADO`) e `BookSettings(preset, delta_min, delta_max, min_trades, max_spread_pct, max_risk, expiries, protection_floor, allow_unlimited_loss)`, com `BookSettings.default(preset)` pelos valores da spec §3.2 e validação das faixas.
- Produces: `PUT /api/perfil/book` com o preset e os valores; `GET /api/perfil` passa a trazer o `book`.

- [ ] **Step 1: Testes que falham:** os três presets com os valores da spec; valores inválidos recusados (delta fora de 0 a 1, mínimo acima do máximo); perfil sem o campo lido como Moderado; ida e volta do JSON; a rota salva e devolve.
- [ ] **Step 2: Implementar.**

### Task 4: Item do book, contexto de vol e a família Renda

**Files:**
- Create: `src/options_engine/domain/book/model.py`, `domain/book/renda.py`
- Test: `tests/book/test_model.py`, `tests/book/test_renda.py`

**Interfaces:**
- Produces: `BookFamily` (`RENDA`, `VOLATILIDADE`, `DIRECIONAIS`, `PROTECAO`), `BookLeg`, `Metric(label, value, unit)`, `BookItem(family, template_key, underlying, expiry, business_days, legs, stock, criterion: Metric, metrics: tuple[Metric, ...], reason: str)`, `VolContext(underlying, iv30, hv21, iv_rank, iv_percentile, regime, regime_from_hv)` e `BookExclusion(underlying, reason)`.
- Produces: `renda_items(ranking: IncomeRanking, context: VolContext | None) -> tuple[BookItem, ...]`, convertendo o ranking da Sprint 5 em itens com o porquê.

- [ ] **Step 1: Testes que falham:** venda coberta e trava de crédito do ranking viram itens com o critério certo e o porquê com os números; referências e exclusões do ranking passam adiante.
- [ ] **Step 2: Implementar.**

### Task 5: Família Volatilidade

**Files:**
- Create: `src/options_engine/domain/book/volatilidade.py`
- Test: `tests/book/test_volatilidade.py`

**Interfaces:**
- Produces: `volatility_items(chain: OptionChain, context: VolContext, settings: BookSettings, schedule: CostSchedule, valuation_date: date, calendar) -> tuple[tuple[BookItem, ...], tuple[BookItem, ...], tuple[BookExclusion, ...]]` (itens, referências, exclusões).
- Venda de vol: iron condor vendido (vendidas na faixa de delta, compradas 1 strike mais fora), borboleta comprada (miolo no dinheiro, asas a 1 e 2 strikes) e, com `allow_unlimited_loss`, strangle vendido. Compra de vol: straddle comprado no dinheiro e strangle comprado na faixa de delta.
- Usa `expiry_summary`, `net_result_breakdown` e `probability_of_profit` do domínio, como o montador.

- [ ] **Step 1: Testes que falham** com a cadeia falsa (PETR4 a 30, vol 30%):
  - regime alta lista só as vendas, baixa só as compras, neutra as duas, rotuladas;
  - ganho/risco e breakevens em desvios-padrão contra o cálculo à mão de um iron condor;
  - strangle vendido só com `allow_unlimited_loss`;
  - perna sem book vai para as referências; risco acima do máximo fica fora.
- [ ] **Step 2: Implementar.**

### Task 6: Família Direcionais (sem visão e com visão)

**Files:**
- Create: `src/options_engine/domain/book/direcionais.py`
- Test: `tests/book/test_direcionais.py`

**Interfaces:**
- Produces: `cheap_options(chain, context, settings, ...)` (sem visão) e `directional_items(chain, view: DirectionalView, settings, ...)` (com visão), com `DirectionalView(underlying, direction: Direction (ALTA, BAIXA), target: float, expiry: date)`.
- Com visão: compra a seco e travas de débito de 1 a 3 strikes de largura, ordenadas pelo resultado líquido no alvo sobre o risco líquido; probabilidade de chegar ao alvo pela IV (lognormal).

- [ ] **Step 1: Testes que falham:** sem visão, só séries com IV abaixo da HV e rank <= 30%, rotuladas como não direcionais; com visão de alta para 33, a trava e a call ordenadas pelo resultado no alvo / risco calculado à mão; alvo do lado errado do spot é recusado com o motivo.
- [ ] **Step 2: Implementar.**

### Task 7: Família Proteção

**Files:**
- Create: `src/options_engine/domain/book/protecao.py`
- Test: `tests/book/test_protecao.py`

**Interfaces:**
- Produces: `protection_items(chain, position: ProtectedPosition, settings, ...)`, com `ProtectedPosition(underlying, quantity, average_price: float | None, hypothetical: bool)`.
- Put protetora e collar com piso >= `protection_floor` x spot; critério: custo mensal equivalente; collar com a call vendida na faixa de delta.

- [ ] **Step 1: Testes que falham:** custo mensal da put protetora e do collar contra contas à mão; piso abaixo do preset fica fora; posição hipotética rotulada; collar de custo negativo (crédito) ordenado antes.
- [ ] **Step 2: Implementar.**

### Task 8: `BookService`

**Files:**
- Create: `src/options_engine/application/ports/book.py`, `application/use_cases/book.py`
- Test: `tests/application/test_book.py`

**Interfaces:**
- Produces: `BookUseCase` com `book(settings: BookSettings, underlyings: Sequence[str]) -> BookView` e `directional(settings, view: DirectionalView) -> BookFamilyView`.
- `BookView(session: date | None, source: DataSource, contexts, families: Mapping[BookFamily, BookFamilyView], unavailable: tuple[BookExclusion, ...])`, com `BookFamilyView(items, references, exclusions)`; cada item com o `BuilderRequest` para o montador.
- `BookService(end_of_day: OptionChainPort, vol_history: VolHistoryPort, income: RankIncomeOpportunitiesUseCase, portfolio: PortfolioUseCase, calendar, tz, schedules)`: a cadeia é sempre a de fim de dia; a posição da Proteção vem das ações compradas do perfil (`open_operations().totals`), senão 100 hipotéticas.

- [ ] **Step 1: Testes que falham:** o book de dois ativos com as quatro famílias; ativo sem cadeia vira indisponível com o motivo e os outros seguem; o pedido do item abre no `StrategyBuilderService` falso sem erro; preset Conservador muda o book; a fonte é sempre `FIM_DE_DIA`, com o pregão.
- [ ] **Step 2: Implementar.**

### Task 9: API do book

**Files:**
- Create: `src/options_engine/adapters/inbound/web/book.py`
- Modify: `src/options_engine/config/web_app.py` (`CotahistVolHistory`, `BookService` com o `EndOfDayMarket`)
- Test: `tests/web/test_book_api.py`, `tests/config/test_web_app.py`

**Interfaces:**
- Produces: `GET /api/book` (perfil aberto, preset dele, lista dele) e `POST /api/book/direcional`; o item leva `pedido` no mesmo formato do `AnaliseIn` do montador.

- [ ] **Step 1: Testes que falham** para as duas rotas, sem perfil (404) e sem COTAHIST (motivo, sem itens); teste da composição com a fixture.
- [ ] **Step 2: Implementar.**

### Task 10: Tela do Book

**Files:**
- Create: `frontend/src/api/book.ts`, `frontend/src/paginas/Book.tsx`, `frontend/src/componentes/EditorPreset.tsx`, `frontend/src/componentes/ItemBook.tsx`
- Modify: `frontend/src/App.tsx` (rota `/book` no lugar do "em breve"), `frontend/src/paginas/Montador.tsx` (abre o `pedido` que vem pelo estado da rota), `frontend/src/api/cliente.ts` (perfil com `book`), `frontend/src/tema.css`
- Test: `*.test.tsx` de cada componente novo e `Montador.test.tsx`

**Interfaces:**
- Uma aba por família, o contexto de vol de cada ativo no topo (IV, HV, rank, regime), o preset editável com "voltar ao padrão", a fonte "fim de dia (B3) do pregão X" e, em cada item, o critério, os números, o porquê e "abrir no montador". As Direcionais têm o formulário da visão (ativo, alta ou baixa, alvo, vencimento).

- [ ] **Step 1: Testes que falham:** trocar o preset salva e recarrega o book; "abrir no montador" leva o pedido e o montador o analisa; referências aparecem rotuladas à parte; o formulário da visão manda o alvo.
- [ ] **Step 2: Implementar**, `verificar` e `build`.

## Parte C — Análise de mercado

### Task 11: `MarketAnalysisService` e API

**Files:**
- Modify: `src/options_engine/application/ports/inbound.py` (`MarketAnalysis`), `application/use_cases/market_view.py` ou `application/use_cases/market_analysis.py` (novo, se ficar grande), `adapters/inbound/web/market.py` (`GET /api/mercado/analise/{ativo}`), `config/web_app.py`
- Test: `tests/application/test_market_analysis.py`, `tests/web/test_market_api.py`

**Interfaces:**
- Produces: `MarketAnalysis(symbol, history: tuple[DailyVol, ...], today: VolContext, smiles: tuple[SmileView, ...], term_structure: tuple[ExpiryVol, ...], source, timestamp)`; o smile e a estrutura a termo pela cadeia do momento, a IV 30 de hoje comparada com o histórico.

- [ ] **Step 1: Testes que falham:** estrutura a termo e smile com a cadeia falsa; rank do dia contra um histórico falso; sem histórico, o motivo e o resto da análise; a rota devolve os números crus.
- [ ] **Step 2: Implementar.**

### Task 12: Aba Análise no Mercado

**Files:**
- Create: `frontend/src/api/analise.ts`, `frontend/src/componentes/AnaliseAtivo.tsx`, `frontend/src/componentes/GraficoVol.tsx`, `frontend/src/componentes/GraficoSmile.tsx`
- Modify: `frontend/src/paginas/Mercado.tsx` (abas Cadeia e Análise), `frontend/src/tema.css`
- Test: `AnaliseAtivo.test.tsx`, `GraficoVol.test.tsx`, `GraficoSmile.test.tsx`

**Interfaces:**
- Gráfico do fechamento e da IV 30 contra a HV 21 no ano (pregões extrapolados marcados), cartões do dia, smile por vencimento e estrutura a termo, com a fonte e o rótulo da taxa constante.

- [ ] **Step 1: Testes que falham:** os cartões mostram rank e percentil, e "histórico curto" quando vêm vazios; o gráfico recebe as séries com os buracos como `null`; o smile troca com o vencimento escolhido.
- [ ] **Step 2: Implementar**, `verificar` e `build`.

### Task 13: Ponta a ponta e documentação

**Files:**
- Create: `docs/superpowers/ledger-semana-3.md`
- Modify: `docs/superpowers/HANDOFF-2026-11-02.md`, `docs/ROADMAP.md`, `README.md`

- [ ] **Step 1: Ponta a ponta** com APPDATA e pasta de perfil temporárias, os arquivos reais da B3 (anual de 2026, diário e Cadastro de 28/10) e `--sem-ponte`:
  - histórico de IV de PETR4 e VALE3, com IV 30, HV 21, rank e percentil de três pregões conferidos à mão;
  - book com as quatro famílias e os três presets; um item de cada família aberto no montador;
  - Direcionais com visão para um alvo de PETR4;
  - aba Análise de PETR4.
- [ ] **Step 2: Ao vivo com o Tryd** (no pregão): a aba Análise com a cadeia ao vivo e o montador reprecificando um item do book.
- [ ] **Step 3: Documentação:** o que mudou, o que fica para a semana 4 e as decisões no ledger.

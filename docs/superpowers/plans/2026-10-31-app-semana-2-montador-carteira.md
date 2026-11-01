# App de opções — Semana 2 (Montador e Carteira) — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** montar qualquer estrutura das quatro famílias e ver o resultado completo (payoff no vencimento e hoje, gregas, breakevens, máximos, custos, IR, grade de cenários e probabilidade), salvar simulações e registrar operações na carteira, com P&L ao vivo pelo preço de zerar, encerramento, exercício, atribuição, ações à mão e pó automático no vencimento.

**Architecture:** o domínio ganha a perna de ação no `Strategy`, uma avaliação "hoje" com vol por perna (call americana aproximada como europeia, rotulada) e custos por perna; a carteira é um módulo puro novo (`domain/portfolio`), em que a posição é recalculada a partir dos eventos de cada operação. Serviços em `application/`, um JSON por operação na pasta do perfil, rotas novas na API FastAPI e duas telas React (Montador e Carteira) com ECharts.

**Tech Stack:** o da semana 1, mais `echarts` 5 no frontend.

**Spec:** [`specs/2026-10-31-semana-2-montador-carteira-design.md`](../specs/2026-10-31-semana-2-montador-carteira-design.md), que detalha o desenho geral [`specs/2026-10-28-app-opcoes-design.md`](../specs/2026-10-28-app-opcoes-design.md).

## Global Constraints

- **Commits só com a autorização do autor**, um por tarefa, com a identidade `Hugo Pontello <136363953+DPontello@users.noreply.github.com>` e sem linha de coautoria. Branch a partir da `development` (`feat/app-semana-2`); merge na `development` com `--no-ff`; nunca apagar branches.
- Português em código, testes (`test_...` em pt-BR), mensagens de tela e de erro. **Comentários só para um porquê não óbvio** (pedido do autor): nada de docstring longa nem de comentário que repete o código.
- `domain/` e `application/` stdlib-only (import-linter). `dependencies = []` continua vazio.
- Direção só no `Side`, quantidade sempre `>= 1` (CONVENTIONS §4), também na perna de ação. Unidades canônicas nas gregas (`theta_per_year`, `vega_per_vol_unit`); por dia e por ponto de vol só na tela.
- Lado de book ausente é `None` (ADR-0003); prêmio pelo lado certo do book (ADR-0004); custos e IR pela ADR-0005; call americana como europeia só com o rótulo (ADR-0002).
- Nenhuma carteira, simulação ou dado real do Tryd ou da B3 no repositório; testes com `tmp_path` e fixtures sintéticas.
- Tempo injetado (`Clock`); nada de `datetime.now()` no domínio.
- Constantes desta semana: eixo do payoff `AXIS_POINTS = 101` de 0,5 a 1,5 x spot (o mesmo do `income/profile`); grade com choques de spot `(-0.20, -0.10, -0.05, 0, 0.05, 0.10, 0.20)` e de vol `(-0.10, -0.05, 0, 0.05, 0.10)`; recálculo do montador no máximo 1 por segundo; versão do arquivo de operação `1`.
- Gates ao fim de cada task (todos verdes), com `PYTHONPATH=src` e o venv (`.venv/Scripts/` no Windows, `.venv/bin/` no Linux):
  `python -m pytest -q -p no:cacheprovider --cov && python -m mypy && python -m ruff check . && python -m ruff format --check . && lint-imports --no-cache`
  e, nas tasks com frontend, `npm --prefix frontend run verificar`.

## Review Focus

1. **Sinal da perna de ação:** short == -long também com ação (propriedade); venda coberta e collar contra valores calculados à mão. Tasks 2 e 4.
2. **Prêmio no custo ou na venda da ação no exercício**, nos quatro casos da Receita, conferidos no texto da IN RFB 1.585/2015 antes de codar. Task 9.
3. **Ação contada duas vezes:** perna "da carteira" não cria ação nova; ações livres descontam as que cobrem call vendida aberta. Tasks 9 e 11.
4. **Pó indevido:** sem o fechamento do pregão do vencimento, nada vira pó; no dinheiro ou dentro, só aviso. Task 9.
5. **Carteira corrompida:** escrita atômica, um arquivo por operação, arquivo ilegível listado e nunca sobrescrito. Task 10.
6. **Dado parado como ao vivo:** P&L com a fonte e a qualidade do preço; perna fora da assinatura aparece "sem cotação ao vivo". Task 12.

---

## Parte A — Montador

### Task 1: Lote do Cadastro na cadeia

**Files:**
- Modify: `src/options_engine/adapters/outbound/cotahist/instruments.py` (`InstrumentInfo.lot: int | None`, lido de `AllcnRndLot`)
- Modify: `src/options_engine/adapters/outbound/b3files/loaded.py` (`LoadedLibrary.lot(symbol) -> int | None`)
- Modify: `src/options_engine/application/ports/inbound.py` (`SeriesRow.lot: int | None`), `application/use_cases/market_view.py` (recebe `lots: Callable[[str], int | None]`), `config/web_app.py`, `adapters/inbound/web/market.py` (`SerieOut.lote`)
- Modify: `frontend/src/api/aoVivo.ts` (`Serie.lote`)
- Test: `tests/adapters/cotahist/test_instruments.py`, `tests/application/test_market_view.py`, `tests/web/test_market_api.py`

**Interfaces:**
- Produces: `SeriesRow.lot` e `SerieOut.lote` (`None` quando o Cadastro não traz o lote).

- [ ] **Step 1: Testes que falham:** `AllcnRndLot` 100, 1 e 10 viram `lot`; vazio ou ilegível vira `None`; a cadeia da API traz `lote`.
- [ ] **Step 2: Implementar** e rodar os gates.

### Task 2: Perna de ação no `Strategy` e payoff no vencimento

**Files:**
- Modify: `src/options_engine/domain/model/strategy.py`, `domain/kernel/payoff.py`, `domain/simulation/engine.py`
- Test: `tests/domain/test_strategy.py`, `tests/kernel/test_payoff.py`, `tests/domain/test_simulation_payoff.py`

**Interfaces:**
- Produces: `StockLeg(symbol: str, side: Side, quantity: int, price: float | None = None)`, com `signed_quantity` e `mirrored()`.
- Produces: `Strategy.stock_legs: tuple[StockLeg, ...] = ()` (no máximo uma); `Strategy.create(name, legs, stock_legs=())`. Invariantes: ao menos uma perna de qualquer tipo; `stock_legs[0].symbol == underlying` das opções; opções com o mesmo vencimento. `Strategy.underlying` passa a valer também só com ação; `expiry` levanta `EmptyStrategyError` sem opção.
- Produces: no kernel, `payoff(s_t, legs, stock=0.0)`, `breakevens(legs, offset, stock=0.0)` e `payoff_extrema(legs, offset, stock=0.0)` com o termo linear `stock` (quantidade assinada de ações). O `payoff_extrema` já devolve `None` para extremo ilimitado; com a ação, a inclinação da cauda direita passa a incluí-la.
- Produces: `payoff_at_expiry`, `pnl`, `payoff_profile` e `net_premium_cashflow` com a perna de ação (`ações x (S - preço)` com o sinal; o preço entra no fluxo de caixa).

- [ ] **Step 1: Testes que falham:**
  - propriedade (hypothesis): `pnl(espelhada, S) == -pnl(original, S)` com ação;
  - venda coberta (ação a 30, call 32 vendida a 1,00, 100 ações): resultado 300 acima de 32, breakeven 29, perda máxima 2.900 (S = 0), ganho máximo 300;
  - collar com extremos finitos; call vendida a seco com perda `None` (ilimitada);
  - ação de outro ativo e duas pernas de ação são recusadas.
- [ ] **Step 2: Implementar** sem quebrar os testes atuais (estratégia só de opções segue igual).

### Task 3: Fábricas e catálogo de modelos

**Files:**
- Modify: `src/options_engine/domain/model/factories.py`
- Create: `src/options_engine/domain/model/templates.py`
- Test: `tests/domain/test_factories.py`, `tests/domain/test_templates.py`

**Interfaces:**
- Produces (fábricas que validam a forma e levantam `InvalidStrategyError`, como as atuais): `long_call`, `long_put`, `covered_call` (ação comprada + call vendida, mesmas quantidades), `cash_secured_put`, `protective_put` (ação comprada + put comprada), `collar` (ação comprada + put comprada + call vendida, strike da put < strike da call). Travas de débito e de crédito usam `vertical_spread`, que já existe.
- Produces: `Family` (`RENDA`, `DIRECIONAIS`, `VOLATILIDADE`, `PROTECAO`); `Template(key, family, name, legs: tuple[TemplateLeg, ...], stock: Side | None)`, com `TemplateLeg(option_type, side, ratio, offset)`. `offset` é o passo de strike a partir do no dinheiro (0, +1, -1...). `TEMPLATES: tuple[Template, ...]` com os modelos da spec §2.1, e `suggest_strikes(template, strikes, spot) -> tuple[float, ...]`.

- [ ] **Step 1: Testes que falham:** cada fábrica aceita a forma certa e recusa a errada (lado, tipo, quantidade e ordem dos strikes); cada modelo do catálogo, aplicado à cadeia sintética, gera um `Strategy` válido pela fábrica da família; `suggest_strikes` pega o strike mais perto do spot e os vizinhos, e recusa cadeia sem strikes suficientes.
- [ ] **Step 2: Implementar.**

### Task 4: Avaliação "hoje" com vol por perna, gregas e grade

**Files:**
- Create: `src/options_engine/domain/simulation/valuation.py`
- Test: `tests/simulation/test_valuation.py`

**Interfaces:**
- Produces: `LegMarket(vol: float)` por perna de opção (na ordem de `strategy.legs`); `today_value(strategy, spot, tau, r, vols) -> float`; `today_curve(strategy, spots, tau, r, vols) -> tuple[float, ...]` (P&L, com o fluxo de caixa da montagem); `structure_greeks(strategy, spot, tau, r, vols) -> Greeks` (ação: delta = quantidade assinada); `scenario_grid(strategy, spot, tau, r, vols, spot_shocks, vol_shocks) -> StressGridResult` (o choque de vol soma à vol de cada perna; vol resultante <= 0 vira célula `None`).
- Produces: `Valuation.american_call_approximated: bool`. Call americana entra como europeia (ADR-0002); put americana levanta `UnsupportedExerciseStyleError` com mensagem para a tela.
- As funções atuais de `engine.py` (vol única, europeu-only) ficam como estão: a CLI e o painel continuam usando.

- [ ] **Step 1: Testes que falham:**
  - com a mesma vol em todas as pernas e opções europeias, os números batem com `mark_to_model_value`, `pnl_curve`, `portfolio_greeks` e `stress_grid` (regressão);
  - com vols diferentes, o valor é a soma das pernas, cada uma com a sua vol;
  - call americana sai com o rótulo; put americana levanta;
  - a célula central da grade é o valor de hoje;
  - delta da ação.
- [ ] **Step 2: Implementar** reaproveitando o kernel (`black_scholes`) e o `fsum` em ordem determinística.

### Task 5: Probabilidade de lucro e custos por perna

**Files:**
- Create: `src/options_engine/domain/simulation/probability.py`
- Modify: `src/options_engine/domain/income/costs.py`
- Test: `tests/simulation/test_probability.py`, `tests/income/test_costs.py`

**Interfaces:**
- Produces: `probability_of_profit(strategy, spot, tau, r, sigma) -> float`: lognormal risco-neutra; soma das faixas de spot com resultado bruto > 0 no vencimento, achadas pelos breakevens.
- Produces: `estimate_order_costs(schedule, *, option_legs: Sequence[tuple[float, int]], stock_trades: Sequence[tuple[float, int]] = ()) -> OrderCosts` (prêmio ou preço por unidade e quantidade de cada perna; uma ordem por perna) e `estimate_exercise_costs_by_leg(schedule, *, exercised: Sequence[tuple[float, int]]) -> OrderCosts`. As funções atuais passam a chamar essas, com o mesmo resultado.
- Produces: `net_result_at_expiry(strategy, spot, schedule) -> float`: bruto - montagem - exercício no cenário - IR estimado (limitado ao resultado do prêmio, ADR-0005).

- [ ] **Step 1: Testes que falham:**
  - call comprada: probabilidade = `N(d2)` no breakeven;
  - put vendida e iron condor: a probabilidade bate com a integral numérica do resultado positivo (tolerância de `tests/_tolerances.py`);
  - fica em [0, 1];
  - custos da borboleta 1-2-1 = soma por perna;
  - as funções antigas dão o mesmo resultado que antes (os testes atuais seguem verdes);
  - o líquido da venda coberta bate com `covered_call_metrics` nos extremos.
- [ ] **Step 2: Implementar.**

### Task 6: Serviço do montador

**Files:**
- Modify: `src/options_engine/application/ports/inbound.py`
- Create: `src/options_engine/application/use_cases/strategy_builder.py`
- Test: `tests/application/test_strategy_builder.py`

**Interfaces:**
- Produces: `BuilderLegInput(symbol, side, quantity, price: float | None)`; `BuilderStockInput(side, quantity, price: float | None, origin: Literal["compra", "carteira"])`; `BuilderRequest(underlying, legs, stock: BuilderStockInput | None)`.
- Produces: `BuilderAnalysis`:
  - `source` e `timestamp`;
  - pernas com o preço usado e a origem (`EXECUTAVEL` / `INDICATIVO` / `TEORICO` / `DIGITADO`);
  - `net_premium` e `max_gain` / `max_loss` (`None` = ilimitado), `breakevens`;
  - `probability_of_profit`, `costs` (montagem), `income_tax` (estimado no ganho máximo), `net_max_gain`;
  - `expiry_curve` (bruto e líquido por spot) e `today_curve` (ou `today_unavailable_reason`);
  - `greeks`, `grid` e `warnings` (fora do lote, call americana aproximada, perna sem preço).
- Produces: `StrategyBuilderUseCase.analyze(request) -> BuilderAnalysis` e `templates() -> tuple[Template, ...]`. Implementado por `StrategyBuilderService(market: MarketPort, calendar, tz, schedules: Sequence[CostSchedule], cdi_annual: Callable[[], float], lots: Callable[[str], int | None])`.
- Regras: preço ausente vem do lado executável da cotação da série na cadeia (`executable_premium`), senão o teórico pelo smile; perna sem preço nenhum entra em `warnings` e o resultado sai parcial (só o vencimento bruto, se houver). Ação "da carteira" exige `price` até a Task 12 ligar o preço médio do perfil.

- [ ] **Step 1: Testes que falham** com o mercado falso de `tests/application/test_market_view.py` (generalizado para um módulo `_mercado_falso.py`):
  - preço pelo lado certo em compra e venda;
  - preço digitado vira `DIGITADO`;
  - aviso de lote;
  - série que não está na cadeia vira erro de domínio claro;
  - call americana aproximada no aviso;
  - put americana sem curva de hoje, com o motivo;
  - fonte da cadeia propagada.
- [ ] **Step 2: Implementar.**

### Task 7: API do montador, simulações e pasta do perfil

**Files:**
- Modify: `src/options_engine/application/ports/inbound.py`, `application/use_cases/profiles.py` (`active_folder() -> Path`; `create` recusa pasta vazia ou relativa: hoje a API aceita `""` e grava na pasta de onde o app abriu)
- Create: `src/options_engine/adapters/outbound/storage/simulations.py`, `src/options_engine/adapters/inbound/web/builder.py`
- Modify: `src/options_engine/config/web_app.py`, `adapters/inbound/web/errors.py`
- Test: `tests/adapters/storage/test_simulations.py`, `tests/web/test_builder_api.py`, `tests/application/test_profiles.py`

**Interfaces:**
- Produces: `GET /api/montador/modelos`; `POST /api/montador/analise` (corpo: `ativo`, `pernas: [{ticker, lado, quantidade, preco?}]`, `acao?: {lado, quantidade, preco?, origem}`); `GET /api/simulacoes`, `POST /api/simulacoes` (`nome` + o corpo da análise), `GET /api/simulacoes/{id}`, `DELETE /api/simulacoes/{id}`.
- Produces: `JsonSimulationRepository(folder: Path)`: um arquivo por simulação em `simulacoes/`, `"versao": 1`, escrita atômica (`write_json_atomic`), ilegível listado com o motivo.
- Valores na API em decimal (CONVENTIONS); gregas por dia e por ponto de vol já convertidas, com o nome da unidade no campo (`theta_dia`, `vega_ponto`).

- [ ] **Step 1: Testes que falham:**
  - análise com 200 e a forma do corpo;
  - perna inválida dá 422 `RequisicaoInvalida`;
  - sem perfil aberto dá 404;
  - simulação gravada e lida de volta;
  - arquivo ilegível listado e preservado;
  - perfil com pasta vazia recusado.
- [ ] **Step 2: Implementar.**

### Task 8: Frontend do Montador

**Files:**
- Modify: `frontend/package.json` (`echarts` com versão exata, de pelo menos duas semanas, por exemplo `5.5.1`)
- Create: `frontend/src/api/montador.ts`, `frontend/src/paginas/Montador.tsx`, `frontend/src/componentes/TabelaPernas.tsx`, `frontend/src/componentes/GraficoPayoff.tsx`, `frontend/src/componentes/GradeCenarios.tsx`, `frontend/src/componentes/ResumoEstrutura.tsx`
- Modify: `frontend/src/App.tsx` (rota `/montador`), `frontend/src/componentes/TabelaCadeia.tsx` (`onEscolherSerie?`), `frontend/src/paginas/Mercado.tsx` ("Montar com este ativo"), `frontend/src/tema.css`
- Test: `*.test.tsx` de cada componente novo (ECharts trocado por um falso no `setup.ts`)

**Interfaces:**
- A tela segue a §2.3 da spec: cadeia à esquerda (a do Mercado, com clique para pôr perna), modelos por família, tabela de pernas editável, resumo em português, gráfico (vencimento bruto e líquido, hoje tracejado), gregas e grade. O recálculo pede `POST /api/montador/analise` quando as pernas mudam e a cada mensagem nova da cadeia, no máximo 1 por segundo.
- "Registrar como executada" fica desabilitado com "na Parte B" até a Task 14.

- [ ] **Step 1: Testes que falham:**
  - escolher um modelo preenche as pernas pela sugestão;
  - clicar numa série da cadeia põe a perna;
  - editar o preço marca "digitado";
  - o resumo mostra "ilimitado" quando o máximo é `null`;
  - o aviso de lote aparece.
- [ ] **Step 2: Implementar**, rodar `npm --prefix frontend run verificar` e `build`.

---

## Parte B — Carteira

### Task 9: Domínio da carteira

**Files:**
- Create: `src/options_engine/domain/portfolio/__init__.py`, `model.py`, `positions.py`, `exercise.py`, `expiry.py`
- Test: `tests/portfolio/` (novo; `__init__.py`, um arquivo por módulo)

**Interfaces:**
- Produces (`model.py`):
  - `OptionLegRef(symbol, terms: OptionTerms)` e `StockLegRef(symbol, origin: StockOrigin)`, com `StockOrigin` (`COMPRA`, `CARTEIRA`);
  - eventos `Execution(leg, on: date, side: Side, quantity, price, costs: float | None)`, `Exercise(leg, on, quantity)`, `Assignment(leg, on, quantity)` e `Expired(leg, on)`;
  - `Operation(id, underlying, name, family, created_on, legs, events)`, com validação: perna existe; não se fecha mais do que está aberto; exercício só em perna comprada; atribuição só em vendida.
- Produces (`positions.py`): `open_legs(operation) -> tuple[OpenLeg, ...]` (perna, lado, quantidade aberta, preço médio de entrada); `realized_result(operation, schedule) -> float`; `consolidate(operations) -> tuple[AssetTotal, ...]` (por ticker: quantidade líquida, preço médio ponderado); `free_shares(operations, symbol) -> int` (ações em carteira menos as que cobrem call vendida aberta).
- Produces (`exercise.py`): `stock_from_option(option_type, side, strike, premium, quantity) -> StockMovement(side, quantity, price)`, pela regra da Receita da spec §3.2.
- Produces (`expiry.py`): `expiry_outcome(option_leg, close: float | None) -> ExpiryOutcome` (`PO`, `REGISTRAR_EXERCICIO`, `AGUARDANDO_FECHAMENTO`). Pó só fora do dinheiro estrito.

- [ ] **Step 0: Conferir a IN RFB 1.585/2015** (o artigo sobre exercício de opções) e anotar no ledger o trecho e o link que fundamentam os quatro casos. Divergência da spec para e volta ao autor.
- [ ] **Step 1: Testes que falham:**
  - duas execuções de abertura dão o preço médio;
  - encerramento parcial dá o realizado proporcional;
  - fechar mais do que o aberto é recusado;
  - os quatro casos de exercício e atribuição, com números à mão;
  - atribuição de call com ação "da carteira" baixa a posição de ações pelo preço médio dela;
  - ações livres descontam a cobertura;
  - pó só fora do dinheiro estrito; no dinheiro ou dentro sai `REGISTRAR_EXERCICIO`; sem fechamento sai `AGUARDANDO_FECHAMENTO`;
  - consolidação de duas operações do mesmo ativo.
- [ ] **Step 2: Implementar** (stdlib-only; somas com `fsum`).

### Task 10: Repositório de operações

**Files:**
- Create: `src/options_engine/adapters/outbound/storage/operations.py`
- Test: `tests/adapters/storage/test_operations.py`

**Interfaces:**
- Produces: `JsonOperationRepository(folder: Path)` com `list() -> tuple[Operation | UnreadableFile, ...]`, `save(operation)` e `load(id)`. Arquivo `operacoes/<AAAA-MM-DD>_<ATIVO>_<id8>.json`, `"versao": 1`, escrita atômica e regravado a cada evento. Ids `uuid4().hex` gerados no serviço.
- Produces: `UnreadableFile(path, reason)`. JSON inválido, versão desconhecida e campo faltando são listados assim e nunca sobrescritos: `save` de um id cujo arquivo está ilegível levanta erro.

- [ ] **Step 1: Testes que falham:**
  - ida e volta de uma operação com todos os tipos de evento;
  - arquivo truncado listado e intacto;
  - versão 2 listada como desconhecida;
  - dois perfis em pastas diferentes não se enxergam.
- [ ] **Step 2: Implementar.**

### Task 11: Serviço da carteira

**Files:**
- Modify: `src/options_engine/application/ports/inbound.py`, `application/ports/outbound.py` (`OperationRepository`)
- Create: `src/options_engine/application/use_cases/portfolio.py`
- Test: `tests/application/test_portfolio.py`

**Interfaces:**
- Produces: `PortfolioUseCase` com:
  - `register(RegisterOperation) -> Operation` (pernas + execuções de abertura; ação "da carteira" exige ações livres);
  - `add_stock(symbol, quantity, average_price, on) -> Operation`;
  - `close(id, leg, quantity, price, on, costs=None)`, `exercise(id, leg, quantity, on)` e `assign(id, leg, quantity, on)`;
  - `open_operations() -> PortfolioView` (operações abertas com pernas, totais por ativo e avisos de vencimento) e `history()`;
  - `process_expiries(closes: Callable[[str, date], float | None]) -> tuple[ExpiryNotice, ...]`, que grava o pó automático e devolve os avisos.
- `PortfolioService(repository_for: Callable[[], OperationRepository], clock, calendar, schedules)`: o repositório vem da pasta do perfil ativo (`ProfileUseCase.active_folder()`).
- O `process_expiries` roda ao abrir a carteira e a cada importação de COTAHIST. Só considera pregões de vencimento já encerrados (depois das 18h do dia, no fuso da B3).

- [ ] **Step 1: Testes que falham** com um repositório em memória: registrar e listar; encerrar tudo move para o histórico; ações livres insuficientes recusadas; pó gravado uma vez só (idempotente); aviso de "registre o exercício"; perfil trocado troca a pasta.
- [ ] **Step 2: Implementar.**

### Task 12: Cotação das pernas e assinatura da carteira

**Files:**
- Modify: `src/options_engine/application/ports/outbound.py` (`OptionQuotePort.get_option_quotes(symbols) -> Mapping[str, OptionQuote | str]`, incluído no `MarketPort`; `watch(..., portfolio_symbols: Sequence[str] = ())`)
- Modify: `adapters/outbound/tryd/feed.py` (cotação por ticker pelo quadro e pelos termos do Cadastro; assinatura na ordem ativos → carteira → cadeia), `adapters/outbound/b3files/end_of_day.py` (pelo pregão do COTAHIST), `adapters/outbound/fallback_market.py`
- Modify: `application/use_cases/market_view.py` (`follow` com as pernas da carteira), `application/use_cases/portfolio.py` (marcação pelo preço de zerar), `application/use_cases/strategy_builder.py` (ação "da carteira" com o preço médio do perfil)
- Test: `tests/adapters/tryd/test_feed.py`, `tests/adapters/b3files/test_end_of_day.py`, `tests/adapters/test_fallback_market.py`, `tests/application/test_portfolio.py`, `tests/application/test_strategy_builder.py`

**Interfaces:**
- Produces: `PortfolioView` com, por perna aberta, o preço de zerar (bid para a comprada, ask para a vendida), a qualidade, a fonte e o P&L não realizado; o teórico ao lado quando faltar o lado de zeragem; total executável por operação e por ativo.
- Série fora da assinatura (limite) ou sem dado: motivo "sem cotação ao vivo", nunca o preço velho.

- [ ] **Step 1: Testes que falham:**
  - a ordem de assinatura com limite pequeno mantém a carteira e corta a cadeia;
  - preço de zerar pelo lado certo;
  - sem bid a comprada fica sem preço executável e com o teórico rotulado;
  - fim de dia rotulado;
  - montador com ação "da carteira" usa o preço médio.
- [ ] **Step 2: Implementar.**

### Task 13: API da carteira e WebSocket

**Files:**
- Create: `src/options_engine/adapters/inbound/web/portfolio.py`
- Modify: `src/options_engine/adapters/inbound/web/market.py` (mensagem `carteira`), `config/web_app.py`, `adapters/inbound/web/errors.py`
- Test: `tests/web/test_portfolio_api.py`, `tests/web/test_market_api.py`

**Interfaces:**
- Produces:
  - `GET /api/carteira`, `GET /api/carteira/historico`;
  - `POST /api/carteira/operacoes` (registrar), `POST /api/carteira/acoes` (à mão);
  - `POST /api/carteira/operacoes/{id}/encerrar`, `/exercer` e `/atribuir`.
- Produces: no WebSocket `/api/ao-vivo`, a mensagem `{"tipo": "carteira", "dados": ...}`, enviada só quando muda, com as pernas da carteira entrando no `follow`.
- Erros de regra (fechar mais do que o aberto, ações livres insuficientes, arquivo ilegível) saem em 422 com o formato único `{"erro", "mensagem"}`.

- [ ] **Step 1: Testes que falham** para cada rota e para a mensagem `carteira`, que só sai quando muda.
- [ ] **Step 2: Implementar.**

### Task 14: Frontend da Carteira

**Files:**
- Create: `frontend/src/api/carteira.ts`, `frontend/src/paginas/Carteira.tsx`, `frontend/src/componentes/FormOperacao.tsx`, `frontend/src/componentes/DialogoEncerrar.tsx`, `frontend/src/componentes/DialogoExercicio.tsx`, `frontend/src/componentes/AdicionarAcoes.tsx`
- Modify: `frontend/src/App.tsx` (rota `/carteira`), `frontend/src/paginas/Montador.tsx` ("Registrar como executada" abre o `FormOperacao` preenchido), `frontend/src/api/aoVivo.ts` (mensagem `carteira`), `frontend/src/tema.css`
- Test: `*.test.tsx` de cada componente novo

**Interfaces:**
- A tela segue a §3.5 da spec: uma linha por operação que se abre nas pernas, total por ativo embaixo, aba Histórico, avisos de vencimento, preço com fonte e qualidade.

- [ ] **Step 1: Testes que falham:**
  - o formulário vindo do montador traz pernas e preços;
  - encerrar parcial manda a quantidade certa;
  - o aviso "registre o exercício" leva ao diálogo;
  - perna sem preço executável mostra o teórico rotulado;
  - o total por ativo soma as operações.
- [ ] **Step 2: Implementar**, `verificar` e `build`.

### Task 15: Ponta a ponta e documentação

**Files:**
- Create: `docs/superpowers/ledger-semana-2.md` (decisões e pendências desta semana, no formato do da semana 1)
- Modify: `docs/superpowers/HANDOFF-2026-10-28.md` (ou um HANDOFF novo da semana 2), `docs/ROADMAP.md` (a fase atual ainda diz "tarefas 1 a 10"), `README.md`

- [ ] **Step 1: Ponta a ponta** com APPDATA e pasta de perfil temporários, os arquivos reais da B3 e `--sem-ponte`:
  - montar uma venda coberta, uma trava, um iron condor e um collar pelos modelos;
  - salvar e reabrir uma simulação;
  - registrar uma venda coberta com ação comprada junto e outra com ação "da carteira";
  - encerrar parte e registrar uma atribuição;
  - conferir o pó automático com um vencimento passado da fixture.
- [ ] **Step 2: Ao vivo com o Tryd** (no pregão): P&L da carteira pelo preço de zerar e assinatura das pernas.
- [ ] **Step 3: Documentação:** o que mudou, o que ficou para a semana 3 e as decisões no ledger.

# Roadmap — Options Analytics Engine

> **Status:** Sprint 3 **concluída em 2026-10-25** (tag `v0.3.0`) — hexágono formal: ports inbound/outbound como Protocols, 3 use cases (`PriceOptionService`, `AnalyzeStrategyPayoffService`, `StressTestService`), contrato `PricingModel` batch-first materializado, adapters outbound (mock GBM seedado, calendário B3 estático com guarda de cobertura, taxa fixa CDI, clock, random), suíte de contrato herdável do `MarketDataPort`, composition root manual e smoke `python -m options_engine` reprodutível por seed. Gates verificados localmente: 2063 testes, cobertura 100% em `application/` e `adapters/` (≥ 90% exigido), import-linter com contrato de camadas. Emendas datadas no ARCH §4.2 (command sem campo redundante; payoff via `SpotAxis`). Próxima: **Sprint 5 (Painel de Renda)**, antecipada para antes da Sprint 4 pela [ADR-0001](adr/0001-renda-antes-da-api.md) em 2026-10-26.
>
> **Premissas:** Python 3.12+, stdlib-only no core até a Sprint 4, arquitetura hexagonal desde o commit inicial (o layout `domain/ → application/ → adapters/` nasce na Sprint 1, ainda que parcialmente vazio — refatorar layout de pacote depois é custo puro). Esforço relativo: **S** (≤ 3 dias-pessoa), **M** (4–7), **L** (8–12), assumindo 1 dev sênior em dedicação parcial de portfólio.
>
> **Regra de corte entre sprints:** nenhuma sprint começa sem a anterior ter tag de release e CI verde.
>
> **Caminho crítico: Sprint 2** — modelagem de sinal/direção das legs e semântica payoff vs. P&L. É onde o review mais rigoroso deve acontecer.

## Decisões de negócio ratificadas (mesa de operações, 2026-07-02)

Estas decisões estavam registradas como "em aberto" na Entrega 1 e foram fechadas pela mesa. Nenhuma é mais bloqueante:

| # | Decisão | Resolução |
|---|---|---|
| 1 | Day count default | **`BUSINESS_252`** (aderência B3). Parâmetro **com default** — continua parametrizado, nunca hardcoded; `CALENDAR_365` disponível para validação contra literatura (Hull). |
| 2 | Escopo de instrumentos | **Europeias apenas no MVP.** Exercício americano (ações B3) estritamente na Fase 6, via seam já preparado (`ExerciseStyle` + `supports()`). **Emenda 2026-10-26 ([ADR-0002](adr/0002-calls-americanas-como-europeias.md)):** calls americanas de ação aceitas como aproximação europeia (`q = 0`, com marca de aproximação); puts americanas continuam rejeitadas. |
| 3 | Direção do Iron Condor | Factories aceitam **ambas as direções** (crédito e débito). Teste de vega **condicionado à direção** (vendido = short vega não-crescente sob vol up; comprado = espelho). |
| 4 | Origem do prêmio da leg | **Opcional, informado pelo chamador.** Sem prêmio → sistema calcula apenas payoff bruto (`payoff_at_expiry`); P&L líquido (`pnl`) exige prêmio. |
| 5 | Posição vencida no grid | **Intrínseco descontado** (ramo fechado da tabela normativa de fronteiras do kernel). |
| 6 | Legs da mesma estrutura | **Mesmo subjacente e mesmo vencimento obrigatórios na Fase 1** (invariantes do agregado; relaxáveis em fase futura — calendar spreads, cross-asset). |
| 7 | Calendário de feriados | **Arquivo estático versionado** no repo (mock simples para o MVP). |
| 8 | Exibição das gregas | Kernel mantém unidades canônicas (Θ/ano, vega por 1.00 de vol). **Toda conversão de visualização (Θ/dia útil, vega/ponto) é do adapter de apresentação, Sprint 4.** |

## Decisões de negócio do Painel de Renda (mesa de operações, 2026-10-26)

Registradas como ADRs em [`docs/adr/`](adr/README.md). Itens marcados como pendentes não bloqueiam o início da Sprint 5, mas precisam ser fechados antes do seu fim.

| # | Decisão | Resolução | ADR |
|---|---|---|---|
| 9 | Prioridade | **Sprint 5 (renda) antes da Sprint 4 (API).** | [0001](adr/0001-renda-antes-da-api.md) |
| 10 | Calls americanas de ação | **Precificadas como europeias** (`q = 0`, marca de aproximação); puts americanas rejeitadas. Emenda a decisão nº 2. | [0002](adr/0002-calls-americanas-como-europeias.md) |
| 11 | Cadeia de opções | **`OptionChainPort` novo**; lado de book ausente é `None`, nunca `0`; vol do subjacente = vol realizada, vol por série = implícita. | [0003](adr/0003-option-chain-port.md) |
| 12 | Livro vazio | **Perna vendida usa bid, comprada usa ask**; `last` do pregão = `INDICATIVO`; sem negócio = `TEORICO`; só `EXECUTAVEL` entra no ranking padrão. Filtros de liquidez: **sem padrão**, opcionais no comando. | [0004](adr/0004-preco-executavel-e-livro-vazio.md) |
| 13 | Rendimento | **Put coberta = prêmio / strike; anualização composta 252 du; excesso sobre o CDI; custos (emolumentos B3, corretagem Necton, IR 15%) parametrizáveis.** Pendentes: base da venda coberta, retorno da trava, tamanho de referência, ordenação padrão. | [0005](adr/0005-metricas-de-rendimento.md) |
| 14 | Fontes de dados | **COTAHIST na fase 1**; brapi descartada; intraday via Necton (MT5 → ProfitDLL → RTD) fora da Sprint 5. | [0006](adr/0006-fontes-de-dados-de-opcoes.md) |
| 15 | Painel | **Relatório HTML estático**, stdlib, acionado pela CLI. | [0007](adr/0007-painel-html-estatico.md) |
| 16 | Universo e filtros | **Lista de ativos informada pelo usuário**; filtros padrão: delta entre 0,15 e 0,35 (em módulo) e os 2 próximos vencimentos — todos parametrizáveis. | — |

---

## Sprint 1 — Fundação Matemática (Esforço: **M**) → tag `v0.1.0`

### Objetivo

Entregar o kernel numérico de Black-Scholes europeu como **funções puras stdlib-only**, com a suíte de V&V (golden-master + property-based + diferenças finitas) construída **junto com** o código — não depois — e todo o tooling de qualidade (lint, type check, CI, import-linter) operante desde o primeiro commit funcional. Ao fim da sprint, o coração matemático do projeto é confiável, auditável e imutável em contrato.

### Escopo IN

- Pacote `domain/kernel/`: funções puras, sem classes de estado, sem I/O, sem dependência externa.
- `norm_cdf(x)` via `math.erf` e `norm_pdf(x)` — **nenhuma** tabela ou aproximação polinomial caseira (A&S 7.1.26 proibida no core).
- `bs_outputs(s, k, tau, r, sigma, q=0.0, *, is_call)` — **`q` (carry) na assinatura desde o dia 1 com default 0.0** — retornando preço + gregas analíticas **delta, gamma, theta, vega e rho** a partir de intermediários `(d1, d2, N(d1), N(d2), n(d1), df)` computados **uma única vez** (padrão *intermediates*; ~6× menos `erf`/`log`/`sqrt`).
- **Fronteiras conforme a tabela normativa** (ver `ARCHITECTURE.md`):
  - Entradas **ilegais** (`s ≤ 0`, `k ≤ 0`, `sigma < 0`, `tau < 0`) → `InvalidKernelInputError`, filha de `DomainError` — **nunca `ValueError` cru** (na Sprint 4 vira HTTP 422 estruturado, não 500 opaco).
  - Limites **legais** (`tau = 0`, `sigma = 0`) → ramos em forma fechada no kernel (intrínseco / ativo determinístico), gregas com convenção documentada (Γ = 0 no vencimento ATM por convenção explícita), `math.isfinite` garantido em todas as saídas.
- Suíte de testes montada em paralelo ao código:
  - **Golden-master:** casos verificados por máquina em 2026-07-02 (Hull 42/40/10%/20%/0.5 → c=4.759422, p=0.808599; ATM 100/100/5%/20%/1 → c=10.450584; deep OTM/ITM; near-expiry; Hull Δ=0.521602; Haug c=2.133368), com fonte citada por caso e **tolerância pertencente ao oráculo**: **5e-3 contra Hull (2 casas publicadas)**, 5e-5 contra Haug (4 casas), 5e-4 contra gregas de livro. *Nunca 1e-4 contra livro de 2 casas — evidência: |4.759422 − 4.76| = 5.8e-4 reprovaria o próprio Hull.*
  - **Property-based (Hypothesis):** paridade put-call `C − P = S·e^(−qT) − K·e^(−rT)` (tol 1e-12), bounds, monotonicidade da call em S/σ/T (não escrever monotonia em T para a put — não vale), Δ_call ∈ (0,1), Δ_put ∈ (−1,0), Γ ≥ 0, vega ≥ 0, Γ/vega call ≡ put, homogeneidade de grau 1, convergência ao intrínseco em τ→0⁺ e σ→0⁺.
  - **Diferenças finitas centrais:** gregas analíticas vs. FD com `h = eps^(1/3)·escala` (h ótimo verificado empiricamente: erro 6.1e-12 no delta ATM), tolerância rel 1e-6; gamma via diferença central do delta analítico (tol 1e-5).
  - **Job `oracle` no CI (ambiente separado):** ~10k parâmetros pseudo-aleatórios com seed fixa vs. `scipy.stats.norm` — scipy **nunca** entra no `pyproject.toml` do core (`tests/oracle/requirements.txt` próprio). *QuantLib e mutation testing ficam para a fase de hardening (S5–6), não aqui.*
- Tooling: `pytest`, `hypothesis`, `ruff` (lint + format), `mypy --strict`, `import-linter` (contrato de camadas), `pyproject.toml` único, GitHub Actions em push/PR.
- `CONVENTIONS.md`: unidades canônicas (taxas/vol em decimal, τ em fração de ano, θ/ano, vega/1.00), tolerâncias por oráculo, fontes dos golden, **day count default `BUSINESS_252` registrado como decisão ratificada**.

### Escopo OUT

- Qualquer classe de domínio (VOs, Strategy) — Sprint 2.
- Implied volatility, dividendos discretos, exercício americano — fora do MVP (ver tabela final).
- Conversão dias úteis → fração de ano (`TradingCalendar`) — Sprint 2/3.
- Qualquer otimização de performance (vetorização, caching) — só com benchmark, Sprint 4+.
- QuantLib como segundo oráculo e `mutmut` — hardening pós-v1.0.

### Entregáveis

1. `src/options_engine/domain/kernel/` com `distributions.py`, `black_scholes.py`, 100% tipado, docstrings com fórmula e referência bibliográfica (Hull, cap./edição).
2. `tests/kernel/` com golden-master parametrizado (fonte citada por caso), suíte Hypothesis, teste de diferenças finitas e testes de fronteira (tabela normativa).
3. `tests/_tolerances.py` — política de tolerância codificada como constantes nomeadas; nenhum teste declara tolerância inline.
4. `.github/workflows/ci.yml` (matriz 3.12/3.13): ruff → mypy → import-linter → pytest+cov → job oracle.
5. `pyproject.toml` com mypy strict escopado, ruff configurado, deps de dev pinadas.
6. `CONVENTIONS.md`.

### Critérios de Aceite (verificáveis)

- [ ] `pytest -q` verde com ≥ 15 casos golden parametrizados, cada um citando fonte, com tolerância da tabela (5e-3 Hull / 5e-5 Haug / 5e-4 gregas).
- [ ] `pytest -q -k property` executa as propriedades com ≥ 200 exemplos por propriedade; paridade put-call fecha em rel 1e-12.
- [ ] Teste FD passa com `h = eps^(1/3)·escala` documentado no código (comentário explicando a curva em U).
- [ ] Teste negativo por entrada ilegal: `InvalidKernelInputError` (filha de `DomainError`) para `s≤0`, `k≤0`, `sigma<0`, `tau<0`.
- [ ] Testes de fronteira: `tau=0` → intrínseco exato (igualdade permitida no ramo fechado); `sigma=0` → forward determinístico; `tau=1e-10` → finito, sem NaN/inf.
- [ ] `mypy --strict` zero erros; `ruff check` e `ruff format --check` limpos; `lint-imports` verde.
- [ ] `pytest --cov` reporta **100% de linhas no kernel** (pequeno e puro; menos é inaceitável aqui).
- [ ] Job `oracle` (scipy) verde no CI; scipy ausente do pyproject do pacote.
- [ ] Inspeção: imports do `domain/` restritos a stdlib (`math`, `dataclasses`, `typing`, `enum`).
- [ ] CI verde no GitHub Actions; tag `v0.1.0`.

### Riscos

- **Tolerância mal calibrada:** golden do Hull é arredondado a 2 casas — tolerância apertada gera flaky, frouxa mascara bug. Mitigação: tolerância por oráculo em `_tolerances.py` + FD como segunda linha de defesa.
- **Scope creep matemático** ("implied vol é só um Newton-Raphson"): cortar ativamente — Fase 5.
- **Convenção de unidades implícita** virando bug silencioso: `CONVENTIONS.md` + unidade no nome dos campos (`theta_per_year`, `vega_per_vol_unit`).

### Definition of Done

Código em `master` via PR com CI verde; kernel em 100% de linhas; `CONVENTIONS.md` publicado; nenhum `# type: ignore` sem justificativa; tag `v0.1.0`.

---

## Sprint 2 — Domínio e Simulação (Esforço: **L**) → tag `v0.2.0`

### Objetivo

Modelar o domínio (VOs, entidades, Composite de estruturas) e entregar o motor de simulação: payoff no vencimento, curva de P&L a mercado, grid de estresse spot × vol e agregação de gregas de portfólio. Ao fim da sprint, o motor responde "quanto vale e quanto arrisca esta estrutura" — ainda sem nenhuma borda de I/O.

### Escopo IN

- **Value Objects** (frozen dataclasses, invariantes no `__post_init__`): `OptionType`, `ExerciseStyle`, `Side`, `OptionTerms`, `DayCountConvention` (**default `BUSINESS_252`**, `CALENDAR_365` disponível), `TimeToExpiry`, `RiskFreeRate` (com `compounding` e `as_continuous()` — CDI base 252 → contínua explícita e testável), `Volatility` (com base de anualização — mesma disciplina da taxa), `MarketSnapshot` (atômico: spot, bid/ask/mid, taxa, vol, timestamp tz-aware), `Greeks` (**incluindo rho**), `PricingResult` (carrega inputs junto — auditoria), `StressScenario`, `ScenarioGrid`, `PayoffProfile` (breakevens; max gain/loss como `float | None`).
- `ExerciseStyle.AMERICAN` declarado no enum mas **rejeitado** com `UnsupportedExerciseStyleError` (decisão 2: europeu-only no MVP, sem fingir suporte).
- Entidades/agregado: `OptionContract` (identidade = ticker), `StrategyLeg` (VO; **`quantity > 0` + `Side` — direção nunca em quantidade negativa**; **prêmio opcional** conforme decisão 4), `Strategy` como Aggregate Root/Composite (`Strategy.create()` valida tudo na construção; sem `add_leg` mutável).
- **Invariantes do agregado (decisão 6):** ≥ 1 leg; **mesmo subjacente e mesmo vencimento obrigatórios** (`MixedUnderlyingError` / `MixedExpiryError`), documentados como restrição de fase reversível.
- **Factories nomeadas** com validação geométrica **e de composição** (tipos/sides das pernas, não só ordem de strikes): `iron_condor()` (**ambas as direções — crédito e débito, decisão 3**), `straddle()`, `strangle()`, `butterfly()`. Violação → `InvalidStrategyError`.
- Motor de payoff: **`payoff_at_expiry`** (bruto) e **`pnl`** (líquido de prêmio — só quando prêmio informado) como funções **distintas por nome**; curva de P&L mark-to-model (reprecifica legs via kernel com τ remanescente); **posição vencida no grid = intrínseco descontado (decisão 5)**.
- Grid de estresse spot × vol parametrizável; agregação de gregas do portfólio (soma ponderada, incluindo rho — casa com `rate_shift`).
- **Breakevens em forma fechada** do Iron Condor (`K2 − crédito líquido`, `K3 + crédito líquido`) expostos no `PayoffProfile` e testados exatamente.
- Hierarquia de exceções com raiz `DomainError` (pré-requisito do mapeamento HTTP da Sprint 4) — catálogo único em `domain/model/errors.py`.

### Escopo OUT

- Ports/adapters e fontes de preço externas — Sprint 3 (preços de entrada fornecidos pelo chamador).
- Rolagem, exercício antecipado, eventos corporativos, superfícies de vol (vol flat por subjacente é **restrição consciente do MVP, documentada**).
- Otimização do grid — Sprint 4+, só com benchmark.
- Persistência.

### Entregáveis

1. `domain/model/` completo (VOs, entidades, agregado, factories, exceções) dependendo apenas de `domain/kernel/` e stdlib.
2. `domain/kernel/payoff.py` + motor de simulação (payoff, P&L, stress grid, agregador).
3. Suíte espelhando a estrutura, com golden geométrico por estrutura nomeada.
4. `CONVENTIONS.md` atualizado (semântica payoff vs. P&L, prêmio opcional, unidades do grid).

### Critérios de Aceite (verificáveis)

- [ ] Golden geométrico por factory: condor com 4 vértices e platôs; butterfly com pico em K2; straddle com V em K (`pytest -q tests/domain`).
- [ ] Property: `payoff(strategy) == Σ payoff(leg)` e `greeks(portfólio) == Σ qty·greeks(leg)`; **`short == −long` ponto a ponto** (anti-inversão de P&L); Δ de straddle ATM ≈ 0.
- [ ] Breakevens do condor batem com a forma fechada (tolerância de auto-consistência).
- [ ] Teste de vega **condicionado à direção**: condor vendido não-crescente sob vol up; comprado, o espelho (decisão 3).
- [ ] `pnl` exige prêmio; sem prêmio, apenas `payoff_at_expiry` disponível — testado (decisão 4).
- [ ] Célula do grid com posição vencida retorna intrínseco descontado, sem NaN (decisão 5).
- [ ] `InvalidStrategyError` para strikes fora de ordem **e** para composição errada de pernas; `MixedUnderlyingError`/`MixedExpiryError` para violação da decisão 6; `UnsupportedExerciseStyleError` para AMERICAN.
- [ ] `mypy --strict` zero erros; `lint-imports` verde; `grep -rE "import (fastapi|pydantic|numpy|pandas)" src/` vazio.
- [ ] `pytest --cov=domain` ≥ 95% branch (kernel mantido em 100% linhas).
- [ ] CI verde; tag `v0.2.0`.

### Riscos

- **Maior risco do projeto: sinal/direção das legs** — erro aqui inverte P&L silenciosamente. Mitigação: irrepresentável no tipo (`quantity > 0` + `Side`) + property `short == −long` + goldens geométricos conhecidos de cor.
- **Confusão payoff vs. P&L:** nomes distintos (`payoff_at_expiry` / `pnl`) e docstrings com definição formal.
- **Over-engineering do Composite:** manter raso (Leg → Strategy); sem estruturas de estruturas no MVP.

### Definition of Done

DoD da Sprint 1, mais: hierarquia `DomainError` documentada; zero import de framework em `src/` (verificado por import-linter no CI); tag `v0.2.0`.

---

## Sprint 3 — Ports & Adapters (Esforço: **M**) → tag `v0.3.0`

### Objetivo

Formalizar a fronteira hexagonal: ports como Protocols, `MockOrderBookAdapter` (GBM com seed injetável), use cases de aplicação, composition root manual e **contract tests** que qualquer adapter futuro deve passar. Ao fim da sprint, trocar o mock por um feed real é escrever um adapter novo — zero mudança em domínio/aplicação.

### Escopo IN

- **Ports outbound** (Protocols, contrato único e canônico): `MarketDataPort.get_snapshot(symbol) -> MarketSnapshot` (**sem** `subscribe()` — entra só na fase websocket); `Clock.now() -> datetime` tz-aware; `TradingCalendar.business_days_between(start, end)`; `RandomSource` seedável.
- **Contrato de precificação batch-first** (único, no domínio): `PricingModel.price_many(Sequence[PricingRequest]) -> Sequence[PricingResult]` + `supports(terms)` + `model_id`; método escalar como açúcar derivado. τ entra **resolvido** no request (application resolve tempo; modelo permanece puro).
- `MockOrderBookAdapter`: GBM com `random.Random(seed)` stdlib, **seed obrigatória no construtor**, parâmetros injetáveis (S₀, μ, σ, dt, spread), produzindo snapshot atômico com bid/ask/mid; vol do snapshot é parâmetro de configuração do mock (sinalizado: vol de referência, não estimada do book).
- `FixedRateAdapter` (CDI flat com `compounding` explícito — nunca `float` nu) e `StaticHolidayCalendar` (**arquivo estático versionado, decisão 7**).
- **Use cases**: `PriceOptionUseCase`, `AnalyzeStrategyPayoffUseCase`, `StressTestUseCase` — ports por construtor, retornam tipos de domínio, orquestração pura.
- **Composition root manual** (`config/composition.py`): DI por construtor, sem framework/container.
- **Contract tests** (suíte única herdável `MarketDataPortContract`): spot > 0, bid ≤ mid ≤ ask, spread ≥ 0, timestamps tz-aware monotônicos, taxa com compounding explícito, símbolo desconhecido → `UnknownSymbolError` (nunca `KeyError`/`None`), snapshot imutável. Determinismo por seed testado na subclasse do mock (adapters reais não prometem isso).
- Teste estatístico leve do GBM: média/variância do log-retorno com seed fixa (determinístico, não flaky).

### Escopo OUT

- FastAPI, HTTP, serialização — Sprint 4.
- Adapter de dados reais (B3, websocket) — pós-MVP; o contract test é o que o torna barato.
- Container de DI, config por env — YAGNI.
- Persistência de ticks.

### Entregáveis

1. `application/` com ports (inbound + outbound) e use cases.
2. `adapters/outbound/` com mock, taxa fixa, calendário estático, `SystemClock`, `SeededRandomSource`.
3. `config/composition.py` + smoke `python -m options_engine` precificando um Iron Condor via mock (documentação executável).
4. `tests/contract/` com a suíte herdável aplicada ao mock.
5. Diagrama hexagonal (Mermaid/ASCII) no README.

### Critérios de Aceite (verificáveis)

- [ ] `pytest -q tests/contract` verde com o mock plugado na suíte de contrato.
- [ ] Mesma seed ⇒ sequências de snapshots idênticas; seeds distintas ⇒ distintas (`pytest -q -k seed`).
- [ ] Teste estatístico do GBM determinístico com seed fixa.
- [ ] Use cases testados com fakes dos ports (unit) e com o mock real (integração leve); `grep -r "adapters" src/options_engine/application/` vazio.
- [ ] Smoke roda e imprime preço + gregas + payoff de um condor, reprodutível dada a seed (documentado no README).
- [ ] `mypy --strict` zero erros; cobertura ≥ 90% em `application/` e `adapters/`.
- [ ] CI verde; tag `v0.3.0`.

### Riscos

- **Port desenhado a partir do mock** (leaky abstraction: "próximo tick do GBM" no contrato). Mitigação: assinatura nasce dos use cases; contract test não contém nada específico de GBM.
- **Teste estatístico flaky** se alguém remover a seed fixa — comentário-guarda no teste.
- **Tempo não-determinístico**: sem `Clock` injetado, τ flutua em teste — está no escopo IN por isso; não cortar.

### Definition of Done

DoD anteriores, mais: contract tests documentados como gate para qualquer adapter futuro; direção de dependências no CI; smoke executável; tag `v0.3.0`.

---

## Sprint 5 — Painel de Renda (Esforço: **L**) → tag `v0.4.0`

> Antecipada para antes da Sprint 4 pela [ADR-0001](adr/0001-renda-antes-da-api.md). Decisões de negócio: nº 9 a 16 (tabela acima).

### Objetivo

Comparar oportunidades de **renda com opções** — venda coberta, put coberta e travas de crédito — entre vários ativos, com dados reais de fim de dia da B3, volatilidade implícita por série, preço executável pelo lado correto do book e rendimento bruto e líquido comparável ao CDI, num relatório HTML estático.

### Pré-requisitos

- Tag `v0.3.0` criada e CI verde (regra de corte).
- **Spike de verificação (timebox: 1 dia, primeira tarefa da sprint)** — fecha as premissas das ADRs antes de qualquer código que dependa delas:
  - ajuste de strike por proventos em dinheiro na B3 (ADR-0002 — se não se confirmar, a ADR é reaberta);
  - layout vigente do COTAHIST e fonte do estilo de exercício por série (ADR-0006);
  - tabela de emolumentos da B3 e de corretagem da Necton para opções; tratamento de IR (ADR-0005).
- Pendências da mesa (ADR-0004 e ADR-0005) podem ser fechadas durante a sprint; o código nasce parametrizado.

### Escopo IN

- **Kernel — volatilidade implícita:** `implied_vol(price, s, k, tau, r, q, *, is_call)` com Newton salvaguardado e bisseção como fallback, checagem prévia dos limites de não-arbitragem e retorno rico `ImpliedVolResult(sigma, status, iterations, method)` — preço fora dos limites ou não convergência viram **status**, nunca exceção nem `NaN`.
- **Domínio — cadeia e preço executável:** VOs `OptionQuote` e `OptionChain` (ADR-0003); enum de qualidade `EXECUTAVEL` / `INDICATIVO` / `TEORICO` e `executable_premium(quote, side)` (ADR-0004); interpolação do smile por vencimento para o preço `TEORICO`.
- **Domínio — precificação:** `supports()` aceita CALL + AMERICAN com marca de aproximação; PUT + AMERICAN segue rejeitada (ADR-0002).
- **Domínio — renda (`domain/income/`):** métricas em forma fechada por estrutura — prêmio executável, rendimento no período, anualizado (252 du), excesso sobre o CDI, bruto e líquido de custos, proteção, breakeven, ganho máximo, perda máxima, delta e N(d2) rotulado como probabilidade risco-neutra, liquidez. Travas de crédito reutilizam `Strategy`, payoff, breakevens e `stress_grid` existentes (factory nova de trava vertical, nas duas direções).
- **Port outbound:** `OptionChainPort.get_chain(underlying_symbol) -> OptionChain` + suíte de contrato herdável `OptionChainPortContract`.
- **Adapter outbound:** `CotahistOptionChainAdapter` (parser de largura fixa, fator de cotação, zero → `None`, cache por pregão em `sqlite3`, vol realizada do subjacente).
- **Configuração de custos:** tabelas de emolumentos e corretagem e alíquota de IR versionadas com data de vigência (ADR-0005).
- **Use case:** `RankIncomeOpportunitiesService` com command (`underlyings`, estruturas, filtros: faixa de delta, número de vencimentos, mínimo de negócios, spread máximo, critério de ordenação) devolvendo candidatos ordenados com qualidade e motivo de exclusão quando aplicável.
- **Adapter de apresentação:** relatório HTML estático via `python -m options_engine` (ADR-0007), com conversões de exibição só ali (decisão nº 8) e escape de todo texto externo.
- **Documentação:** ARCH §4.1 (port novo), CONVENTIONS (unidades de rendimento, vol realizada vs implícita), README (como gerar o painel).

### Escopo OUT

- Dados intraday e adapters Necton (MT5, ProfitDLL, RTD) — ADR-0006.
- Perna de ação no agregado `Strategy` (gráfico de payoff da venda coberta) — as métricas de venda coberta e put coberta são em forma fechada nesta sprint.
- Precificação americana exata (Fase 6), dividendos discretos.
- Margem real da B3 (largura da trava como proxy de risco), cálculo fiscal (o IR é estimativa por operação).
- Persistência de histórico além do cache de pregões; API REST (Sprint 4); envio de ordens.

### Entregáveis

1. `implied_vol` no kernel com V&V próprio.
2. VOs de cadeia, regra de preço executável e módulo `domain/income/`.
3. `OptionChainPort` + suíte de contrato + `CotahistOptionChainAdapter` com cache.
4. `RankIncomeOpportunitiesService` + configuração de custos.
5. Relatório HTML gerado pela CLI, reprodutível para um pregão fixo (fixture COTAHIST versionada em `tests/data/`).
6. ADRs 0002–0007 com premissas verificadas (ou reabertas) e pendências fechadas.

### Critérios de Aceite (verificáveis)

- [ ] Ida e volta preço → volatilidade implícita → preço dentro da tolerância do oráculo em toda a faixa testada; scipy como oráculo em `tests/oracle/`.
- [ ] Preço abaixo do intrínseco descontado ou acima do limite superior → status próprio, sem exceção e sem `NaN` (teste dedicado).
- [ ] `pytest -q tests/contract` verde com o adapter COTAHIST plugado na `OptionChainPortContract`.
- [ ] Teste de fronteira: campo zerado na fonte chega ao domínio como `None` (nunca `0.0`).
- [ ] Tabela da ADR-0004 coberta linha a linha por testes do domínio (cada situação × perna vendida/comprada).
- [ ] CALL + AMERICAN precificada com marca de aproximação; PUT + AMERICAN → `UnsupportedExerciseStyleError`.
- [ ] Métricas de rendimento com golden cases calculados à mão (put coberta, venda coberta, trava de alta com put, trava de baixa com call), brutos e líquidos.
- [ ] `python -m options_engine` gera o HTML para o pregão da fixture; teste verifica que a saída é idêntica para a mesma entrada.
- [ ] Grep-guard do core continua vazio; `mypy --strict` zero erros; ruff limpo; import-linter com contratos mantidos; cobertura ≥ 95% global e kernel em 100%.
- [ ] CI verde; tag `v0.4.0`.

### Casos de Teste (mínimo)

- **Positivos:** cadeia completa com bid e ask → ranking só com `EXECUTAVEL`, ordenado pelo critério configurado; put coberta com prêmio / strike; anualização composta com `du` do calendário B3 atravessando feriado.
- **Negativos:** ativo desconhecido → `UnknownSymbolError`; book cruzado (`bid > ask`) rejeitado pelo contrato; PUT americana rejeitada; arquivo COTAHIST truncado ou com linha de tamanho errado → erro explícito com número da linha.
- **Borda:** vencimento hoje (0 du → sem anualização, valor intrínseco); série só com bid usada como perna comprada (fora do ranking); trava com crédito ≥ largura (arbitragem/dado inconsistente → excluída com motivo); volatilidade implícita sem convergência (série exibida como `TEORICO` ou excluída, nunca com número inventado); subjacente sem preço utilizável → fora do painel do dia com motivo.

### Riscos

- **Ranking que premia iliquidez:** maior rendimento costuma estar na série de spread largo. Mitigação: preço executável por lado (ADR-0004) + filtros de liquidez.
- **Assincronia de fim de dia:** último negócio da opção bem anterior ao fechamento da ação distorce a volatilidade implícita. Mitigação: `last` só como `INDICATIVO`.
- **Premissa da ADR-0002 não se confirmar** no spike: venda coberta volta a depender da Fase 6. Mitigação: spike é a primeira tarefa.
- **Volatilidade implícita alta tem motivo** (balanço, evento): o painel mostra números, não recomendação; sem filtro de eventos nesta sprint.
- **Escopo L em dedicação parcial:** timebox — kernel + domínio + adapter primeiro (60%), apresentação depois (40%).

### Definition of Done

DoD anteriores, mais: spike registrado nas ADRs; pendências da mesa fechadas; suíte de contrato do `OptionChainPort` documentada como gate para os adapters intraday; relatório HTML reprodutível documentado no README; tag `v0.4.0`.

---

## Sprint 4 — API e Polimento de Portfólio (Esforço: **M**) → tag `v1.0.0`

> Executada **depois da Sprint 5** ([ADR-0001](adr/0001-renda-antes-da-api.md)). Os endpoints passam a poder expor também o use case de renda.

### Objetivo

Expor o motor via FastAPI como **adapter inbound fino** (pydantic só na borda, domínio intocado), mapear exceções de domínio para HTTP e transformar o repositório em peça de portfólio: benchmark documentado, README com diagrama e badges, ADRs das decisões-chave.

### Escopo IN

- `adapters/inbound/rest/`: app FastAPI, routers, DTOs pydantic com mapeamento explícito DTO ⇄ domínio (DTO nunca entra em `application/`).
- Endpoints: `POST /price`; `POST /strategies/payoff` (body — evita explosão de query params); `POST /stress`.
- **Endpoints de cálculo como `def` síncrono** (regra/ADR: *async é para I/O; CPU-bound nunca inline no event loop* — threadpool do Starlette mantém o loop vivo; simulações pesadas futuras em `ProcessPoolExecutor`).
- **Mapeamento de exceções:** `DomainError` e filhas → 422 com corpo estruturado `{error_code, message, details}` (inclusive `InvalidKernelInputError`, `UnsupportedExerciseStyleError`); inesperado → 500 opaco. Contrato de erro no OpenAPI.
- **Adapter de apresentação das gregas (decisão 8):** conversões Θ/dia útil (÷252), vega/ponto (÷100) etc. vivem **exclusivamente aqui**, dirigidas por `DayCountConvention`; kernel permanece canônico. Campos de resposta carregam a unidade no nome.
- Composition root da API reutilizando `config/composition.py` (mock por default; troca por env é 1 linha).
- **Benchmark documentado** (`BENCHMARKS.md`): preço+gregas unitário e grid N×M típico, com hardware/versões; requisito de referência: grid 50×50 × 4 legs < 300 ms p95 em CPython puro. Entrega é a medição honesta + análise, não otimização.
- **README de portfólio:** pitch, diagrama Mermaid, quickstart (`uvicorn` + `curl` retornando o caso HULL), badges (CI, coverage, python, ruff, mypy), seção de trade-offs linkando ADRs.
- **ADRs** (`docs/adr/`, MADR curto), ≥ 6: (1) float64 vs Decimal; (2) stdlib-only no core; (3) contrato batch-first; (4) hexagonal + composition root manual sem DI framework; (5) **day count default `BUSINESS_252` — decisão ratificada pela mesa em 2026-07-02** (contexto B3 vs literatura 365); (6) async/CPU-bound; (7) pydantic só na borda; (8) escopo europeu-only com rejeição explícita de americano (contexto B3: ações americanas, índice europeias) — já emendado pela [ADR-0002](adr/0002-calls-americanas-como-europeias.md) para calls de ação; a ADR da S4 registra a decisão original e aponta a emenda. Numeração continua após a série 0001–0007 da S5.
- Testes da borda: `TestClient` cobrindo happy path por endpoint + cada classe de erro + payload inválido (422 pydantic).

### Escopo OUT

- Autenticação, rate limiting, CORS de produção — nota no README.
- WebSocket/streaming — pós-MVP.
- Docker/deploy — opcional pós-MVP.
- Versionamento de API, paginação — YAGNI.

### Entregáveis

1. `adapters/inbound/rest/` completo + testes de API.
2. `BENCHMARKS.md` com metodologia, hardware e números.
3. README final com Mermaid, badges e quickstart validado em ambiente limpo.
4. ≥ 6 ADRs em `docs/adr/`.
5. OpenAPI coerente com schemas de erro.

### Critérios de Aceite (verificáveis)

- [ ] `pytest -q tests/api` verde: 3 endpoints (happy path) + ≥ 1 teste por classe de erro (payload inválido → 422 pydantic; `InvalidStrategyError` → 422 com `error_code`; AMERICAN → 422 com code próprio).
- [ ] Guard no CI: `grep -rE "import pydantic|from pydantic|import fastapi|from fastapi" src/options_engine/domain/ src/options_engine/application/` **vazio** — o critério mais importante da sprint.
- [ ] `uvicorn` sobe e o `curl` do quickstart retorna 200 com o caso HULL coerente com o golden da Sprint 1.
- [ ] Resposta da API expõe gregas canônicas **e** convertidas com unidade no nome do campo (decisão 8), testado.
- [ ] `/docs` renderiza os 3 endpoints com schemas de request/response/erro.
- [ ] Benchmark reprodutível na ordem de grandeza registrada em `BENCHMARKS.md`.
- [ ] `mypy --strict` zero erros no repo inteiro; ruff limpo; cobertura global ≥ 90%, kernel mantido em 100%.
- [ ] ≥ 6 ADRs com Status/Contexto/Decisão/Consequências.
- [ ] CI verde; tag `v1.0.0` com changelog.

### Riscos

- **Vazamento de pydantic para o domínio** por conveniência — o grep-guard existe exatamente para isso.
- **`async def` chamando cálculo síncrono** — funciona no unit test e no curl isolado, trava a API no primeiro acesso concorrente; a ADR async/CPU-bound é pré-requisito da sprint.
- **Benchmark virar micro-otimização prematura:** qualquer otimização exige número "antes" em `BENCHMARKS.md`.
- **Polimento consumir a sprint:** timebox — API e exception mapping primeiro (60%), portfólio depois (40%).

### Definition of Done

Repo inteiro passa lint + mypy strict + testes no CI; guard de framework ativo no pipeline; README executável do zero por terceiro; ADRs mergeadas; release `v1.0.0` com changelog.

---

## Fora do MVP — e onde entra

| Item | Por que está fora | Sprint futura | Pré-requisitos / seam preparado |
|---|---|---|---|
| **Implied volatility** (Newton salvaguardado + fallback Brent; ref. Jäckel, *Let's Be Rational*) | Política de convergência e bounds são mini-projeto próprio | **S5 — Painel de Renda** (antecipada, ADR-0001) | Kernel expõe vega; retorno rico `(sigma, converged, iterations, method)`; V&V próprio (round-trip preço→IV→preço) |
| **Dividendos discretos / proventos B3** | Yield contínuo `q` **já está na assinatura do kernel desde a S1** — sem quebra de contrato | **A replanejar após a S5** (fora do Painel de Renda, ADR-0001) | Golden cases com dividendos |
| **Hardening de V&V** (QuantLib como 2º oráculo, `mutmut` ≥ 90%, nightly Hypothesis 10k) | Pacote nível banco sem slot no MVP; gate sem slot é ficção | **A replanejar após a S5** | `mutmut` não roda em Windows — gate exclusivo do CI Linux |
| **Opções americanas** (binomial CRR / Bjerksund-Stensland) | Modelo numérico distinto; decisão 2 fixa a Fase 6 | **S6** | Seam pronto: `ExerciseStyle` + `supports()`; V&V próprio (convergência de malha). Calls de ação já aceitas como aproximação europeia desde a S5 (ADR-0002) |
| **Monte Carlo** | Custo alto e redundante para europeias vanilla | **S7** | Segundo motor atrás do mesmo `PricingModel` batch-first; BS analítico vira golden do MC; provável ADR revendo stdlib-only (NumPy) |
| **Persistência** (estratégias salvas, histórico) | Stateless por design até haver caso de uso real | **S8** | `StrategyRepositoryPort` + SQLite; contract tests da S3 como molde |

**Ordem de execução a partir de 2026-10-26 (ADR-0001): S5 (Painel de Renda) → S4 (API) → 6 → 7 → 8**; dividendos discretos e hardening de V&V são replanejados ao fim da S5.

## Resumo de esforço e dependências

| Sprint | Esforço | Depende de | Entrega-âncora |
|---|---|---|---|
| 1 — Fundação Matemática | M | — | Kernel BS (+q, +rho) + V&V + CI (`v0.1.0`) |
| 2 — Domínio e Simulação | **L** (caminho crítico) | S1 | Composite + payoff/P&L + stress grid (`v0.2.0`) |
| 3 — Ports & Adapters | M | S2 | Hexágono formal + mock GBM + contract tests (`v0.3.0`) |
| 5 — Painel de Renda | L | S3 | Volatilidade implícita + cadeia COTAHIST + métricas de renda + relatório HTML (`v0.4.0`) |
| 4 — API e Polimento | M | **S5** (ADR-0001) | FastAPI na borda + benchmark + ADRs (`v1.0.0`) |

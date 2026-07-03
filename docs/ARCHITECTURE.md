# Arquitetura — Options Analytics Engine

> **Status:** aprovado pela mesa em 2026-07-02 (Entrega 1 de viabilidade técnica).
> **Escopo deste documento:** desenho arquitetural, modelagem de domínio e contratos (interfaces). Plano de testes em [`VV-PLAN.md`](VV-PLAN.md); fases de execução em [`ROADMAP.md`](ROADMAP.md).
> **Stack:** Python 3.12+. Core 100% stdlib (`math.erf`/`erfc`); FastAPI entra apenas na Sprint 4, como adapter.

---

## 1. Arquitetura Hexagonal e a Regra de Dependência

```
                        COMPOSITION ROOT (config/composition.py)
                        wiring manual, sem framework de DI — único módulo que conhece tudo
                                    │ instancia e injeta
        INBOUND (driving)           ▼                       OUTBOUND (driven)
   ┌──────────────────┐   ┌─────────────────────────┐   ┌──────────────────────┐
   │ CLI      (S3)    │──▶│   APPLICATION LAYER      │──▶│ MockOrderBookAdapter │
   │ FastAPI  (S4,    │   │  Use Cases (orquestração)│   │ SystemClock          │
   │  adapter fino)   │   │  Ports = Protocols       │   │ SeededRandomSource   │
   └──────────────────┘   └───────────┬─────────────┘   │ B3HolidayCalendar    │
                                      ▼                  └──────────────────────┘
                          ┌─────────────────────────┐
                          │      DOMAIN LAYER        │   model/   VOs, entidades, agregados
                          │  (stdlib only, zero I/O) │   pricing/ PricingModel (Strategy)
                          │                          │   kernel/  functional core (floats puros)
                          └─────────────────────────┘
```

**Regra de dependência (não negociável, sempre apontando para dentro):**

| Camada | Pode importar | Nunca importa |
|---|---|---|
| `domain` | apenas stdlib | `application`, `adapters`, qualquer framework, qualquer I/O |
| `application` | `domain` | `adapters`, fastapi, pydantic, numpy |
| `adapters` | `application` + `domain` | — (implementam ports; substituíveis sem tocar no núcleo) |
| `config` | tudo | — (único ponto de wiring; instanciação explícita, sem container de DI) |

**Enforcement mecânico, um só:** `import-linter` no CI com contrato de camadas (`domain` não importa `application`; `application` não importa `adapters`; `domain` e `application` não importam fastapi/pydantic/numpy). Regra de arquitetura que não quebra o build é sugestão, não regra. Não há mecanismos redundantes (AST-walker, grep) — uma única fonte de verdade de enforcement.

**Risco arquitetural vigiado desde o dia 1:** a tentação de deixar o `MarketSnapshot` "saber" de onde veio (JSON do feed, schema da B3). Isso mata a hexagonalidade silenciosamente. O snapshot é um VO de domínio; a tradução feed→VO acontece exclusivamente dentro do adapter.

---

## 2. Modelagem Tática — VO vs Entity vs Aggregate

Critério único e objetivo:

- **Value Object:** igualdade **estrutural**. Imutável por construção (`@dataclass(frozen=True, slots=True)`), sem identidade, sem ciclo de vida. Invariantes validadas no `__post_init__` — **estado inválido é irrepresentável**.
- **Entity:** igualdade por **identidade**. Atributos idênticos com identidades diferentes são coisas diferentes.
- **Aggregate:** fronteira de consistência. Invariantes multi-objeto vivem na raiz, e só ela é referenciável de fora.

### 2.1 Catálogo de Value Objects

| VO | Racional |
|---|---|
| `OptionType` (enum CALL/PUT) | Elimina o antipadrão `is_call: bool` e strings mágicas no domínio. (No *kernel*, `is_call: bool` keyword-only é aceitável — lá circulam primitivos por design; a fronteira converte.) |
| `ExerciseStyle` (enum EUROPEAN/AMERICAN) | Primeira classe porque na B3 o estilo varia por instrumento e determina se Black-Scholes é matematicamente válido. Decisão ratificada: MVP é europeu-only; AMERICAN existe no enum e é **rejeitado explicitamente** (`UnsupportedExerciseStyleError`) — nunca precificado errado em silêncio. |
| `Side` (enum BUY/SELL) | Direção de uma leg. Valor puro. |
| `OptionTerms` | Termos econômicos (strike, expiry, tipo, estilo) **sem o ticker**. Dois contratos de termos idênticos são economicamente intercambiáveis — igualdade estrutural é a semântica correta. A identidade (ticker) pertence à Entity `OptionContract`. |
| `DayCountConvention` | **Nunca um `252` hardcoded.** Constantes `BUSINESS_252` (B3 — **default ratificado pela mesa**) e `CALENDAR_365` (Hull/literatura, usado nos golden tests). Armadilha que o VO torna auditável: vol anualizada e τ devem estar na mesma base — misturar produz preço errado sem nenhum erro de runtime. |
| `TimeToExpiry` | `year_fraction: float` + a `DayCountConvention` que o produziu (auditoria; impede misturar bases). Invariante: `year_fraction >= 0`. Construído via factory que recebe `Clock` + `TradingCalendar` (BUS/252 exige contar dias úteis). |
| `RiskFreeRate` | `rate: float` + `compounding` (enum `CONTINUOUS` / `BUSINESS_DAILY_252`). Crítico no Brasil: BS assume capitalização contínua; CDI é efetiva anual base 252. `as_continuous() -> float` é método explícito e testável (`r_cont = ln(1 + cdi)`), nunca uma linha enterrada num adapter. **Taxa como `float` nu é proibida em qualquer port.** |
| `Volatility` | `value: float` + base de anualização (`BUSINESS_252` / `CALENDAR_365`). Mesma disciplina da taxa: vol como `float` nu no snapshot repetiria exatamente o erro que o `RiskFreeRate` existe para impedir. Restrição consciente do MVP: **vol flat por subjacente** (sem smile/por-strike) — sinalizada, não escondida. |
| `MarketSnapshot` | Foto **atômica e imutável** do mercado: spot, `bid`/`ask`/`mid`, `RiskFreeRate`, `Volatility`, timestamp tz-aware. Atomicidade garante que preço + gregas + grid inteiro usam dados coerentes entre si — o spot não muda no meio do cálculo. |
| `Greeks` | `delta, gamma, theta_per_year, vega_per_vol_unit, rho` — **unidade no nome do campo** (defesa estrutural contra "falsos bugs" de convenção). Rho entra desde o dia 1: o `StressScenario` tem `rate_shift`, logo a grega correspondente existe. Agregável por soma ponderada. |
| `PricingResult` | Preço + `Greeks` + `model_id` + os inputs usados (`MarketSnapshot`, `TimeToExpiry`). Carregar inputs junto ao output dá rastreabilidade e reprodutibilidade de graça: todo número do sistema é reconstruível a posteriori. |
| `StrategyLeg` | Termos + símbolo + `side` + `quantity` + `premium: float \| None`. **Invariante: `quantity > 0` — a direção vive em `side`, nunca em quantidade negativa** (`SELL/-10` é ambiguidade que inverte P&L silenciosamente; o tipo a torna irrepresentável). Prêmio **opcional, informado pelo chamador** (decisão ratificada): sem prêmio, o sistema calcula apenas payoff bruto. |
| `StressScenario` | Choque nomeado e imutável: `spot_shift` multiplicativo, `vol_shift` aditivo em pontos de vol, `rate_shift`. `label` permite relatório auditável. |
| `ScenarioGrid` | Especificação declarativa do grid (`spot_min`, `spot_max`, `steps`, eixo de vol). Separar **especificação** (VO barato) de **materialização** (floats no kernel) é parte do functional core (§5). |
| `PayoffProfile` | Pontos + breakevens + max gain/loss (`float \| None`, onde `None` = ilimitado — explícito no tipo, não convenção mágica). Distingue **`payoff_at_expiry`** (bruto) de **`pnl`** (líquido de prêmio) — nomes diferentes porque são semânticas diferentes. |

**O que deliberadamente NÃO é VO:** preço/strike como `Decimal`/`Money`. Veredito fechado (ADR): o kernel opera em `float64` IEEE-754 — padrão da indústria para analytics de derivativos. `Decimal` pertence a contabilidade/liquidação, é 50–100× mais lento e não melhora um modelo cujo erro dominante é o próprio modelo.

### 2.2 Entidades e Agregados

**`OptionContract` — Entity.** Identidade = ticker (ex.: `PETRA250`). Termos idênticos com tickers distintos são instrumentos distintos, com books separados. Igualdade e hash exclusivamente pelo símbolo. Atributos imutáveis pós-listagem — o que autoriza `StrategyLeg` a carregar uma cópia dos `terms` (para o cálculo puro) mais o `symbol` (rastreabilidade) sem risco de snapshot stale.

**`Strategy` — Aggregate Root, padrão Composite.** Raiz agrega `tuple[StrategyLeg, ...]`: Iron Condor = 4 legs, Straddle = 2, opção seca = 1. O motor trata qualquer estrutura uniformemente como soma ponderada (`side` × `quantity`) — nenhum `isinstance` em lugar nenhum; a estrutura é dados, não subclasse. Construção completa e validada via `Strategy.create(name, legs)`; sem `add_leg` mutável no MVP.

**Invariantes do agregado (na construção, decisões ratificadas pela mesa):**

1. `len(legs) >= 1` — `EmptyStrategyError`.
2. `quantity > 0` em toda leg (garantido pelo VO, reafirmado na raiz).
3. **Mesmo subjacente obrigatório** em todas as legs (fase 1) — `MixedUnderlyingError`. Restrição reversível; relaxar depois é fácil, introduzir depois quebra dados.
4. **Mesmo vencimento obrigatório** (fase 1) — calendar spreads são extensão futura sinalizada.
5. Factories nomeadas validam geometria **e composição**: `iron_condor()` exige `K1 < K2 < K3 < K4` **e** os tipos/sides corretos das 4 pernas (put spread + call spread). `iron_condor()` **aceita ambas as direções** (crédito/vendido e débito/comprado — decisão ratificada); os testes de comportamento sob vol são condicionados à direção.

---

## 3. O Contrato de Precificação — a decisão irreversível do projeto

**Existe UM contrato de precificação, ele vive no domínio, e é batch-first.**

```python
@runtime_checkable
class PricingModel(Protocol):
    """Strategy pattern intra-domínio. Unidades canônicas fazem parte do contrato:
    tau em anos, sigma anualizada decimal, theta_per_year, vega_per_vol_unit, q decimal."""

    @property
    def model_id(self) -> str: ...          # "black-scholes-v1" → auditoria no PricingResult

    def supports(self, terms: OptionTerms) -> bool: ...
    # BS NÃO precifica exercício americano (ações B3). supports() permite ao use case
    # falhar explicitamente (UnsupportedExerciseStyleError) em vez de retornar preço errado.

    def price_many(
        self,
        requests: Sequence[PricingRequest],   # terms + snapshot + time_to_expiry resolvido
    ) -> Sequence[PricingResult]: ...
```

Por que batch-first é inegociável no dia 1: um port escalar `price(request)` condena qualquer backend vetorizado futuro a receber um item por vez — NumPy chamado 10.000 vezes com arrays de tamanho 1 é *mais lento* que pure Python — e consertar depois quebra todos os adapters, use cases e testes. O custo de fazer certo hoje é **zero**: a implementação inicial é um loop, e o método escalar de conveniência é açúcar derivado (`price(r) = price_many([r])[0]`). Não há um segundo nível de abstração (`NumericalBackend` separado): para um workload de 20–150 ms, dois níveis é over-engineering; a assinatura batch já preserva o caminho de vetorização (PurePython → NumPy → Numba/Rust atrás da mesma interface, escolhidos no composition root, migração por benchmark).

Nota de pureza: o τ entra **resolvido** no request. Calcular τ exige `Clock` + `TradingCalendar` — se isso acontecesse dentro do modelo, ele deixaria de ser referencialmente transparente. A application layer resolve o tempo; o modelo permanece puro.

---

## 4. Ports (contratos — assinaturas apenas)

Todos em `typing.Protocol` (structural typing: o adapter não precisa importar nada do domínio para "ser" um port); `runtime_checkable` onde os contract tests precisarem de `isinstance`.

### 4.1 Outbound (driven) — `application/ports/outbound.py`

```python
@runtime_checkable
class MarketDataPort(Protocol):
    """Fonte de dados de mercado. Fase 1: MockOrderBookAdapter. Futuro: B3 feed, websocket
    — mesmo contrato. Streaming/subscribe NÃO entra na fase 1: método que nenhum adapter
    implementa quebra ISP e os contract tests; entra na fase websocket."""

    def get_snapshot(self, underlying_symbol: str) -> MarketSnapshot: ...


@runtime_checkable
class Clock(Protocol):
    """Abstrai 'agora'. Testes injetam FixedClock → time-to-expiry 100% determinístico.
    datetime.now() espalhado pelo código é o assassino nº 1 de testes de pricing."""

    def now(self) -> datetime: ...   # SEMPRE tz-aware (UTC interno; conversão nas bordas)


@runtime_checkable
class TradingCalendar(Protocol):
    """Obrigatório para BUS/252: contar dias úteis exige feriados B3.
    Fase 1 (decisão ratificada): arquivo estático versionado no repositório."""

    def business_days_between(self, start: date, end: date) -> int: ...


@runtime_checkable
class RandomSource(Protocol):
    """Aleatoriedade injetável e SEMPRE seedável. Serve o gerador de order book mockado
    hoje e o Monte Carlo amanhã. random.random() global no domínio é proibido."""

    def gaussians(self, n: int) -> tuple[float, ...]: ...
    def uniform(self, low: float, high: float) -> float: ...
```

### 4.2 Inbound (use cases) — `application/ports/inbound.py`

```python
@dataclass(frozen=True, slots=True)
class PriceOptionCommand:
    underlying_symbol: str
    terms: OptionTerms


class PriceOptionUseCase(Protocol):
    def execute(self, command: PriceOptionCommand) -> PricingResult: ...


class AnalyzeStrategyPayoffUseCase(Protocol):
    """Retorna payoff_at_expiry (bruto) sempre; pnl (líquido) apenas quando
    todas as legs têm prêmio informado (decisão ratificada #4)."""
    def execute(self, strategy: Strategy, grid: ScenarioGrid) -> PayoffProfile: ...


class StressTestUseCase(Protocol):
    def execute(
        self, strategy: Strategy, scenarios: Sequence[StressScenario]
    ) -> StressTestReport: ...
```

Os adapters inbound (CLI hoje, FastAPI na Sprint 4) dependem **apenas** destes Protocols. O endpoint FastAPI será ~10 linhas de tradução HTTP→command — prova concreta de que o framework é adapter, não fundação.

---

## 5. Functional Core, Imperative Shell

Conflito clássico: DDD pede objetos ricos; um grid 50×50 × 4 legs são ~10k avaliações de kernel — instanciar VOs em cada uma é suicídio de performance em CPython. Resolução estratificada — **a API real do kernel:**

```python
# domain/kernel/distributions.py — funções puras, stdlib only
def norm_cdf(x: float) -> float: ...   # 0.5 * erfc(-x / sqrt(2)) — preserva precisão nas caudas
def norm_pdf(x: float) -> float: ...

# domain/kernel/black_scholes.py
class BSOutputs(NamedTuple):
    price: float
    delta: float
    gamma: float
    theta_per_year: float       # calendário; conversões de exibição são do adapter (decisão #8)
    vega_per_vol_unit: float    # por 1.00 de vol; por ponto = ÷100 no adapter
    rho: float                  # por 1.00 de taxa

def d1_d2(s: float, k: float, tau: float, r: float, sigma: float,
          q: float = 0.0) -> tuple[float, float]: ...

def bs_price(s: float, k: float, tau: float, r: float, sigma: float,
             q: float = 0.0, *, is_call: bool) -> float: ...

def bs_outputs(s: float, k: float, tau: float, r: float, sigma: float,
               q: float = 0.0, *, is_call: bool) -> BSOutputs: ...
# Computa (d1, d2, N(d1), N(d2), n(d1), descontos) UMA vez; preço e 5 gregas derivam
# dos mesmos intermediários (~6× menos erf/log/sqrt). Intermediário não vaza pelo port.
```

`q` (carry/dividend yield contínuo) está na assinatura **desde o dia 1 com default 0.0** — o modelo do MVP não usa dividendos, mas adicioná-lo depois seria quebra de contrato do kernel; agora custa zero.

O shell (use cases + `PricingModel` concreto) faz a fronteira: desembrulha VOs em floats **uma vez** na entrada (`rate.as_continuous()`, `ttx.year_fraction`), roda o loop quente sobre primitivos, re-embrulha em VOs **uma vez** na saída. Por quê:

1. **DDD preservado onde importa.** VOs e invariantes protegem as *fronteiras* — onde erros de significado acontecem (252 vs 365, CDI vs contínua, CALL vs PUT). Dentro do kernel não há significado a proteger: é matemática sobre reais.
2. **Testabilidade máxima nos dois estratos.** Kernel validado ponto a ponto contra golden-masters (funções puras, sem setup); shell testado com `FixedClock` + snapshots sintéticos.
3. **Otimização sem refactor de domínio.** NumPy/Numba trocam o interior das funções do kernel; nenhum VO, port ou use case muda.
4. **Pureza = reprodutibilidade = auditoria.** Mesmos floats de entrada, mesmo preço de saída, sempre.

---

## 6. Tabela Normativa de Fronteiras do Kernel

Norma única referenciada por arquitetura, V&V e roadmap — resolve "quem valida o quê":

| Entrada | Classificação | Quem trata | Comportamento contratado |
|---|---|---|---|
| `s <= 0`, `k <= 0`, `sigma < 0`, `tau < 0`, não-finitos | **Ilegal** | Kernel levanta `InvalidKernelInputError` (filha de `DomainError`) como **defesa em profundidade**; a partir da Sprint 2, os VOs tornam essas entradas irrepresentáveis antes de chegar ao kernel | Exceção tipada do domínio — nunca `ValueError` cru (na Sprint 4 vira HTTP 422 estruturado, não 500 opaco) |
| `tau = 0` exato | **Limite legal** | Kernel, ramo fechado | Preço = intrínseco `max(±(s−k), 0)`; Δ = degrau (0/1 para call, 0/−1 para put; ATM exato: convenção documentada); Γ, vega, Θ, rho = 0 **por convenção documentada** (Γ ATM no vencimento é matematicamente um delta de Dirac — reportar 0 é decisão, não acidente). Ratificado (#5): posição vencida dentro de um grid = **intrínseco descontado**. |
| `sigma = 0` exato | **Limite legal** | Kernel, ramo fechado | Ativo determinístico: `preço = e^(−r·tau) · max(±(F−k), 0)` com `F = s·e^((r−q)·tau)` |
| `tau → 0⁺`, `sigma → 0⁺` | Legal | Kernel, fórmula normal | Contínuo com os ramos exatos; `math.isfinite` garantido em todas as saídas |
| Exercício AMERICAN | Legal no domínio, fora do modelo | `supports()` no use case | `UnsupportedExerciseStyleError` — nunca preço silenciosamente errado (fase 6: binomial) |

Hierarquia de exceções (`domain/model/errors.py`): raiz `DomainError`; filhas `InvalidKernelInputError`, `InvalidDomainValueError` (invariante de VO violada na construção), `EmptyStrategyError`, `MixedUnderlyingError`, `MixedExpiryError` (decisão nº 6), `InvalidStrategyError`, `UnsupportedExerciseStyleError`, `MissingPremiumError` (decisão nº 4: `pnl` sem prêmio), `MixedAnnualizationBaseError` (vol e τ em bases distintas — a armadilha do CONVENTIONS §2 tornada detectável), `UnknownSymbolError`. Catálogo canônico único — pré-requisito do mapeamento HTTP da Sprint 4.

---

## 7. Layout de Pacotes

```
black-scholes-pricer/
├── pyproject.toml
├── docs/                        # este documento, VV-PLAN.md, ROADMAP.md, adr/
├── src/options_engine/
│   ├── domain/                  # stdlib only — verificado por import-linter no CI
│   │   ├── model/               # enums, conventions, market, contracts, strategy,
│   │   │                        #   scenarios, results, errors
│   │   ├── pricing/             # PricingModel (Protocol) + black_scholes.py (Sprint 2)
│   │   └── kernel/              # functional core: distributions.py, black_scholes.py, payoff.py
│   ├── application/
│   │   ├── ports/               # inbound.py, outbound.py
│   │   └── use_cases/
│   ├── adapters/
│   │   ├── inbound/             # cli/ (S3), rest/ (FastAPI, S4)
│   │   └── outbound/            # mock_orderbook/, system_clock.py, seeded_random.py,
│   │                            #   b3_calendar.py (arquivo estático versionado)
│   └── config/
│       └── composition.py       # composition root — wiring explícito, sem DI framework
└── tests/
    ├── _tolerances.py           # única fonte de tolerâncias (ver VV-PLAN.md)
    ├── data/golden/             # valores de referência verificados, com proveniência
    ├── kernel/                  # golden + properties + boundaries + finite-diff
    ├── domain/                  # invariantes de VOs e agregados (S2)
    ├── application/             # use cases com fakes (S3)
    ├── contract/                # suíte de contrato dos ports (S3)
    └── oracle/                  # CI job separado; requirements próprio (scipy) — nunca no core
```

---

## 8. MockOrderBookAdapter e Contract Tests

**Onde se pluga:** `adapters/outbound/mock_orderbook/`, implementando `MarketDataPort`. Recebe `RandomSource` (seed **obrigatória** no construtor) e `Clock` — o mock é 100% determinístico em teste por construção. Gera preços via passeio geométrico browniano (stdlib `random.Random`), com spread configurável produzindo bid/ask/mid. A vol do snapshot é **parâmetro de configuração** do mock (o mock gera preços; a vol que o pricer consome é de referência, não estimada do book — estimá-la é extensão futura sinalizada).

**Contrato semântico que TODO feed (mock, B3, websocket) deve honrar** — type hints garantem forma, não comportamento:

1. `get_snapshot` retorna `MarketSnapshot` com `spot > 0`, `volatility > 0`, `bid <= mid <= ask`.
2. `timestamp` sempre tz-aware; snapshots sucessivos com timestamps monotônicos não-decrescentes.
3. `risk_free_rate` sempre com `compounding` explícito; conversão para contínua é do domínio, nunca do feed.
4. Símbolo desconhecido → `UnknownSymbolError` (exceção de domínio), nunca `None`, nunca exceção de lib HTTP vazando pelo port.
5. `get_snapshot` é consulta, não comando (sem efeitos colaterais observáveis).

**Uma única suíte de contract tests herdável** (`tests/contract/`): classe abstrata com os testes escritos uma vez contra o Protocol; cada implementação herda e fornece só a fixture de construção (`class TestMockOrderBook(MarketDataPortContract)`). Determinismo por seed é testado na subclasse do mock, não no contrato (adapters reais não prometem isso). Quando o adapter B3 real chegar, ele nasce com a bateria de conformidade pronta — o Adapter pattern verificável, não só desejado.

---

## 9. Decisões de Negócio Ratificadas (mesa, 2026-07-02)

| # | Decisão | Resposta da mesa | Onde se materializa |
|---|---|---|---|
| 1 | Day count default | **`BUSINESS_252`** (aderência B3) | `DayCountConvention`; golden tests do Hull continuam usando frações de ano diretas (`CALENDAR_365` onde aplicável) |
| 2 | Escopo de instrumentos | **Europeias only no MVP**; americano estritamente na Fase 6 | `ExerciseStyle` + `supports()` + `UnsupportedExerciseStyleError` |
| 3 | Direção do Iron Condor | **Aceita ambas** (crédito e débito); teste de vega **condicionado à direção** | Factory `iron_condor()`; propriedades de vol em `tests/domain/` |
| 4 | Origem do prêmio da leg | **Opcional, informado pelo chamador**; sem prêmio → apenas payoff bruto | `StrategyLeg.premium: float \| None`; `payoff_at_expiry` vs `pnl` |
| 5 | Posição vencida no grid | **Intrínseco descontado** | Ramo `tau = 0` do kernel (tabela §6) |
| 6 | Legs da estrutura | **Mesmo subjacente e mesmo vencimento obrigatórios** (fase 1) | Invariantes do agregado `Strategy` (`MixedUnderlyingError` etc.) |
| 7 | Calendário de feriados | **Arquivo estático versionado** (mock simples no MVP) | `adapters/outbound/b3_calendar.py` + `tests/data/` |
| 8 | Exibição das gregas | **Kernel canônico inalterado**; conversões (Θ/dia, vega/ponto) no adapter de apresentação (Sprint 4) | Nomes com unidade (`theta_per_year`, `vega_per_vol_unit`); mappers do adapter inbound |

**Restrições conscientes do MVP (sinalizadas, não escondidas):** vol flat por subjacente (sem smile — cada strike de um Iron Condor real tem vol própria; primeira extensão natural junto com implied vol na Fase 5); sem dividendos no modelo (mas `q` na assinatura desde o dia 1); sem persistência; sem streaming.

Cada decisão acima deve virar ADR curto em `docs/adr/` quando a sprint correspondente a materializar.

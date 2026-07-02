# CONVENTIONS — Unidades Canônicas e Convenções do Motor

> Convenção divergente é a fonte nº 1 de "falso bug" em pricing (risco A5 da
> análise de riscos): um theta de −0.012 e um de −3.02 são ambos "razoáveis"
> dependendo de ser por dia útil ou por ano. Este documento é a fonte única
> de verdade. **Toda assinatura pública carrega a unidade no nome do campo**
> (`theta_per_year`, `vega_per_vol_unit`) — critério de code review, não boa
> vontade.

## 1. Unidades canônicas do kernel

O kernel (`domain/kernel/`) opera EXCLUSIVAMENTE nestas unidades. Conversões
de exibição pertencem ao adapter de apresentação (Sprint 4, decisão
ratificada nº 8) — nunca ao kernel, nunca ao domínio.

| Grandeza | Unidade canônica | Exemplo | Nunca |
|---|---|---|---|
| `s`, `k` (spot, strike) | unidade monetária do subjacente, float64 | `42.0` | `Decimal`, centavos inteiros |
| `tau` | **fração de ano** (adimensional), `>= 0` | `0.5` = meio ano | dias crus (`126`, `183`) |
| `r` (taxa livre de risco) | **capitalização contínua**, decimal | `0.10` = 10% a.a. contínua | CDI efetiva anual direto no kernel |
| `sigma` (volatilidade) | anualizada, decimal, mesma base de anualização de `tau` | `0.20` = 20% | pontos percentuais (`20`) |
| `q` (carry / dividend yield) | contínuo, decimal, default `0.0` | `0.04` | proventos discretos (fase futura) |
| `theta_per_year` | ∂V/∂t por **ano calendário** | `-6.414` | por dia (÷252 ou ÷365 é exibição) |
| `vega_per_vol_unit` | por **1.00** de sigma | `37.52` | por ponto de vol (÷100 é exibição) |
| `rho` | por **1.00** de taxa | `53.23` | por ponto-base |

Referência executável: docstring de `src/options_engine/domain/kernel/black_scholes.py`
(as unidades fazem parte do contrato da função).

## 2. Day count — política ratificada

**Decisão da mesa (2026-07-02, nº 1): default `BUSINESS_252`** (padrão
B3/CDI), sempre **parametrizado, nunca hardcoded** — `ACT/365` disponível
para compatibilidade com a literatura (Hull publica em anos calendário).

- O kernel **não conhece dias**: recebe `tau` já como fração de ano. A
  conversão data→fração é responsabilidade do `DayCountConvention` +
  `TradingCalendar` (Sprint 2), que carregam a convenção junto do valor
  (`TimeToExpiry` guarda a convenção que o produziu — auditável).
- **Armadilha documentada:** vol anualizada e `tau` devem estar na MESMA
  base. Vol em base 252 com `tau` em base 365 produz preço errado sem
  nenhum erro de runtime. O VO `Volatility` (Sprint 2) carrega a base.
- Calendário de feriados: **arquivo estático versionado** no repositório
  (decisão nº 7); fonte e atualização documentadas quando o adapter entrar
  (Sprint 3).
- Os golden-masters do Hull usam frações de ano diretamente — são neutros
  quanto à convenção e permanecem válidos.

## 3. Taxas — CDI vs contínua

Black-Scholes assume capitalização contínua; o CDI é cotado como taxa
efetiva anual em base 252 dias úteis. A conversão `r_cont = ln(1 + cdi)` é
método explícito e testável do VO `RiskFreeRate.as_continuous()` (Sprint 2)
— nunca uma linha enterrada em adapter. **Taxa como `float` nu é proibida em
qualquer port**: sempre acompanhada da convenção de capitalização.

## 4. Direção e quantidade de posições

- `quantity > 0` **sempre**; a direção vive no enum `Side` (BUY/SELL).
  Quantidade negativa (`SELL/-10`) é ambiguidade que inverte P&L
  silenciosamente — o tipo a torna irrepresentável (Sprint 2).
- Exposição assinada de uma leg = `side_sign · quantity` com
  `side_sign ∈ {+1, -1}` derivado do enum, em UM único lugar do código.
- Propriedade de segurança: `short(estrutura) == -long(estrutura)` ponto a
  ponto, verificada por Hypothesis.

## 5. Payoff vs P&L — semânticas distintas, nomes distintos

- `payoff_at_expiry` — valor **bruto** da estrutura no vencimento (não
  considera prêmio pago/recebido).
- `pnl` — resultado **líquido** do prêmio. Prêmio é **opcional e informado
  pelo chamador** (decisão nº 4); sem prêmio, o sistema entrega apenas o
  payoff bruto e os breakevens não são calculáveis.
- Curva de P&L a mercado (mark-to-model, reprecificação com `tau`
  remanescente) é uma terceira coisa — `pnl_curve` (Sprint 2).

## 6. Política numérica

- **float64 IEEE-754 em todo o core; `Decimal` é proibido** (ADR prevista):
  padrão da indústria para analytics; o erro dominante é de modelo, não de
  representação. `Decimal` pertence a contabilidade/liquidação.
- `==` entre floats é proibido em testes, exceto ramos de forma fechada com
  caminho aritmético idêntico (política formal em `tests/_tolerances.py` e
  docs/VV-PLAN.md §1 — toda tolerância é constante nomeada, nunca inline).
- Agregações (soma de legs/cenários) em ordem determinística, com
  `math.fsum` — iterar sobre `set` muda o último bit e quebra testes de
  1e-12.

## 7. Determinismo

- `datetime.now()`/`date.today()` e `random` global são **proibidos** no
  core: `Clock` e `RandomSource` são ports injetados (Sprint 3), com seed
  obrigatória no mock. Mesma seed ⇒ resultado bit a bit idêntico.
- Perfis Hypothesis: `dev` (100 exemplos), `ci` (500, `derandomize=True` —
  PR nunca flaka por sorteio), `nightly` (10.000; falha vira `@example`
  permanente no teste).

## 8. Golden-masters

`tests/data/golden/*.json` é **imutável por convenção**: corrigir um valor
exige nova verificação independente, novo `verified_on` e justificativa no
commit. Proveniência é parte do teste (fonte, arredondamento, método).

## 9. Léxico canônico

| Termo | Significado | Não usar |
|---|---|---|
| `kernel` | functional core matemático (funções puras sobre floats) | "core", "engine" para este pacote |
| `StrategyLeg` | perna de uma estrutura (VO) | `Leg` solto |
| `OptionTerms` | termos econômicos sem identidade (VO) | — |
| `OptionContract` | instrumento listado com ticker (Entity) | `EuropeanOption` |
| `Strategy` | estrutura multi-leg (Aggregate, Composite) | `StructuredPosition` |
| `tau` | tempo até o vencimento em anos | `T`, `t`, `dias` |

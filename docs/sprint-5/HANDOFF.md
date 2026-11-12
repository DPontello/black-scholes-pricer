# Sprint 5 — estado do trabalho e como continuar (2026-10-27)

Documento de passagem entre máquinas. Some com a branch
`docs/sprint-5-handoff` quando a Sprint 5 fechar; o que for permanente já
está (ou vai para) as ADRs, o ROADMAP e o código.

## 1. Onde está cada coisa

Atualizado em 2026-10-27, na segunda máquina. Todas as branches partem de
`development` (0f00a9f) e estão publicadas no GitHub. Merges feitos na
`development` (`--no-ff`, sem apagar branches), nesta ordem:

| Branch | O que tem | Estado |
|---|---|---|
| `fix/ruff-format-markdown` | Gate de formatação do ruff ignora `.md` (o ruff 0.17 passou a formatar os blocos de código das docs e derrubou o CI desde 2026-10-26) | Mergeada |
| `docs/adr-pendencias-renda` | ADRs 0002–0006 com o resultado do spike e **todas** as decisões da mesa; ROADMAP da Sprint 5 atualizado | Mergeada |
| `fix/kernel-preco-nao-negativo` | Kernel nunca devolve preço negativo (subnormal por cancelamento) | Mergeada; achados da §3 pendentes |
| `feat/american-call-approx` | ADR-0002: CALL+AMERICAN precificada como europeia com `PricingResult.approximation`; PUT+AMERICAN rejeitada | Mergeada; achados da §3 pendentes |
| `feat/implied-vol` | `implied_vol` no kernel + oráculo scipy de ida e volta | Mergeada; revisão da §3 pendente |
| `feat/option-chain` | `OptionQuote`, `OptionChain`, `PriceQuality`, `LegPremium`, `executable_premium`, `OptionChainPort` + suíte de contrato | Mergeada; achados da §3 pendentes |
| `docs/sprint-5-handoff` | Este documento e o plano da fase 2 | Mergeada |
| `feat/income-metrics` | `domain/income/` (custos de montagem e exercício, IR, anualização, métricas e extremos líquidos das 3 estruturas) + `vertical_spread` | Mergeada depois da §2 |
| `fix/revisao-kernel` | Correções da §3 no kernel e na IV + cota física no oráculo da IV | Mergeada |
| `fix/revisao-call-americana` | Call americana com r < 0 rejeitada, testes de rejeição no motor, ADR-0002 | Mergeada |
| `docs/revisao-sprint-5` | ARCH e VV-PLAN atualizados (call americana, IV, fronteiras, tolerâncias de renda) | Mergeada |

Gates depois de cada merge (pytest + cobertura, mypy strict, ruff
check/format, lint-imports): todos verdes; 3233 testes, cobertura 99%. O
oráculo scipy (`tests/oracle/scipy_oracle.py`) passou na `development` depois
das branches de kernel (`feat/income-metrics` não toca o kernel).

Os PRs #1 (`docs/sprint-5-handoff`) e #2 (`feat/implied-vol`) foram
mergeados direto na `master` pelo GitHub, fora da convenção (feature entra na
`development`; a `master` só recebe a `development` no fechamento de versão),
e com o CI vermelho pelo motivo acima. O histórico não foi reescrito: a
`master` foi mergeada de volta na `development` sem mudança de conteúdo, então
continua ancestral dela e o merge da v0.4.0 sai limpo. A `master` fica com o
CI vermelho até esse merge. PRs novos apontam para a `development`.

## 2. Ajuste de `feat/income-metrics` — feito em 2026-10-27

Itens 3–5 da ADR-0005 aplicados em commits pequenos e mergeados na
`development`:

- `CostSchedule` com `option_exchange_fee_rate` (renomeada),
  `spot_exchange_fee_rate`, `brokerage_per_order`,
  `exercise_brokerage_per_order` e `income_tax_rate`.
- `estimate_setup_costs`, `estimate_exercise_costs` e `estimate_income_tax`
  (funções puras); `OrderCosts` (emolumentos + corretagem) e
  `OperationCosts` (montagem + IR do cenário de rendimento, com a tabela).
- Venda coberta paga a compra das ações na montagem.
- `IncomeMetrics.net_breakeven` (`None` quando o líquido nunca zera),
  `net_max_gain_per_position` e `net_max_loss_per_position`.
- Golden cases à mão com a tabela de referência e com a ilustrativa;
  oráculo numérico independente do P&L líquido (extremos por cenário e
  grade, breakeven por bisseção) em casos fixos e aleatórios; propriedades
  pedidas. Mutantes nas fórmulas líquidas são mortos.

Decisões de implementação que a mesa deve conhecer estão na nota de estado
da ADR-0005 (base do IR limitada ao prêmio; ganho máximo da venda coberta no
cenário exercido, com S = K valendo até o custo de exercício a mais).
As tolerâncias de renda entraram na tabela do VV-PLAN com a revisão da §3.

## 3. Achados de revisão — verificados em 2026-10-27

Cada achado foi reproduzido antes de qualquer correção; os corrigidos têm
teste que falha no código anterior. Um fuzz de magnitudes extremas (200 mil
casos) achou mais um furo na IV e confirmou os do kernel; depois das
correções, zero exceções cruas. Oráculo scipy verde depois das mudanças.

| Achado | Veredito | Onde ficou |
|---|---|---|
| Kernel: `max(price, 0.0)` vira `-inf` em 0.0 | **Confirmado** (put com S=K=1,78e308 saía 0.0; o valor real é ~1e307) e corrigido: piso só para ruído finito; o não finito chega aos VOs, que o rejeitam | `fix/revisao-kernel` |
| Kernel: docstring "preço >= 0 sempre" com NaN | **Confirmado** e corrigido: "sempre que finito", com o caso de overflow documentado | `fix/revisao-kernel` |
| Kernel: `log(s / k)` com underflow vaza `ValueError` | **Confirmado** e corrigido: `log(s/k)` no caminho normal, `log(s) - log(k)` fora da faixa | `fix/revisao-kernel` |
| Kernel: `s * sig_sqrt_tau` com underflow vaza `ZeroDivisionError` no gamma | **Confirmado** e corrigido: gamma por divisões sucessivas | `fix/revisao-kernel` |
| IV: chute inicial divide por `min(S̃, K̃)·sqrt(tau)` (achado novo do fuzz) | **Confirmado** (~9% dos casos extremos) e corrigido do mesmo jeito | `fix/revisao-kernel` |
| IV: piso do oráculo frouxo com K ≫ S | **Confirmado** por medição (piso até 4,4× o preço) e corrigido: cota física pela escala de cancelamento (margem 28×, cota <= 1,1e-6 do preço) | `fix/revisao-kernel` |
| Call americana com r < 0 abaixo do intrínseco | **Confirmado** (S=100, K=50, r=-2%, T=5: 44,74 contra 50) e corrigido: `price_many` rejeita; propriedade `C >= S - K` com r >= 0 | `fix/revisao-call-americana` |
| Motor rejeita a call americana, contra a ADR-0002 e o ROADMAP | **Confirmado** como inconsistência de docs. Decisão: o motor segue europeu-only (os resultados não carregam a marca); ADR-0002 (nota 2) e ROADMAP registram | `fix/revisao-call-americana` |
| Faltam testes de rejeição em `pnl_curve`, `stress_grid`, `portfolio_greeks` e da PUT no motor; docstring "opção europeia" | **Confirmado** e corrigido: 14 testes (7 entradas × CALL/PUT); docstring do `PriceOptionUseCase` | `fix/revisao-call-americana` |
| Docs de ARCH/VV-PLAN desatualizadas (americana e IV) | **Confirmado** e corrigido | `docs/revisao-sprint-5` |
| Option chain: `trades` NaN/float/bool passa | **Reproduzível só com tipo errado** (o mypy strict barra NaN e float; `True` vale 1 negócio, como o `int` 1). O domínio não checa tipo em runtime em lugar nenhum. **Não corrigido**; ver fase 2 abaixo | — |
| Option chain: `quotes` gerador não vira tuple | **Reproduzível só com tipo errado** (gerador esvazia a checagem e a cadeia). Mesma convenção; a suíte de contrato exige tuple. **Não corrigido** | — |
| `worst_quality(None)` vaza `ValueError` | **Reproduzível só com tipo errado** (`None` numa lista de `PriceQuality`). **Não corrigido** | — |
| IV: preço no intrínseco descontado vira `CONVERGED` com sigma = 0.0 | Comportamento do contrato (regra 5), não defeito. **Decidido na fase 2**: pontos com sigma = 0 ficam fora do smile (não carregam informação sobre a vol); docstring de `domain/pricing/smile.py` | `feat/rank-income` |

**Pontos em aberto gerais**
- Vol realizada zero ou histórico insuficiente: a suíte de contrato exige
  vol > 0; o plano da fase 2 tira o ativo do painel com motivo.
- Campo `OptionQuote.volume` é volume financeiro, mas o nome não carrega a
  unidade (CONVENTIONS pede); renomear exige emendar a ADR-0003.
- `OptnStyle` (valores) e o vínculo série → ativo-objeto precisam ser
  conferidos no primeiro arquivo real do cadastro/COTAHIST.
- `valid_from` da tabela de custos: a B3 não publica vigência; o plano usa
  2025-08-01 (OC 025/2025-VPC), com a origem anotada.
- Adapters de cadeia: converter `trades` com `int()` estrito na fronteira.
  O COTAHIST já o faz (campo numérico de largura fixa); um adapter futuro
  sobre JSON (brapi) recebe `Any`, que escapa do mypy (achado de option
  chain da §3).

## 4. Fase 2 — implementada em 2026-10-27

Especificação em [`plano-fase-2.md`](plano-fase-2.md). Mergeadas na
`development`, nesta ordem, com gates verdes depois de cada merge (3485
testes, cobertura 99%, kernel em 100%):

| Branch | O que tem |
|---|---|
| `feat/chain-exclusions` | `UnderlyingUnavailableError`, `RejectedSeries`, `OptionChain.rejected_series` e `underlying_book_available`; port e suíte de contrato |
| `feat/cotahist-adapter` | parser, cadastro de instrumentos, cache sqlite por pregão, `CotahistOptionChainAdapter`, fixture sintética com gerador determinístico; o adapter plugado na suíte de contrato |
| `feat/rank-income` | tabela de custos versionada + `schedule_on`, smile e preço TEÓRICO, VOs do ranking e `RankIncomeOpportunitiesService` |
| `feat/painel-html` | `html_report.py`, `build_income_panel` e `python -m options_engine painel` |
| `docs/fase-2` | ARCH §4.1/§4.2/§6/§7, CONVENTIONS §9 (rendimento e vol), README, ROADMAP e versão 0.4.0 |
| `feat/grafico-payoff` | Gráfico de payoff por linha do ranking (item acrescentado ao plano pelo autor em 2026-10-27): `domain/income/profile.py` (bruto e líquido por preço, conferido contra o oráculo de `test_net_profile.py`) e `adapters/inbound/payoff_svg.py` |

**Falta para fechar a Sprint 5:**

1. ~~Merge da `development` na `master` e tag `v0.4.0`~~ — feito em
   2026-10-27: PR #3 com CI verde (gates em Python 3.12 e 3.13 e oráculo
   scipy), merge `ba1003c` na `master` e tag anotada `v0.4.0`.
2. Conferir no primeiro arquivo REAL da B3 as premissas registradas nas
   docstrings do adapter: TOTREG do trailer conta header e trailer; domínio
   do `OptnStyle`; conteúdo do ESPECI das opções (desempate PETR3/PETR4);
   strike já ajustado no `PREEXE` (ROADMAP, spike).
3. Intraday via Tryd: spike aberto em 2026-10-27. Roteiro em
   `docs/spikes/tryd-intraday.md`, prova de conceito em
   `tools/tryd_spike/tryd_poc.py` (só Windows, pywin32 em venv separado) e
   [ADR-0008](../adr/0008-intraday-tryd-rtd.md) **proposta**. Falta rodar o
   roteiro numa máquina com o Tryd e preencher os resultados antes de a
   mesa aceitar ou descartar a ADR.

Observação para a mesa: com o critério default (anualizado líquido), as
travas de crédito tendem a liderar o ranking, porque o retorno sobre risco
anualizado de forma composta em poucos du fica muito alto (ex.: 26% em 18
du vira ~2.600% a.a.). É consequência direta das decisões 6 e 8 da ADR-0005;
o critério é configurável (`--ordenar`).

## 5. Ambiente

- Gates: `python -m pytest -q -p no:cacheprovider --cov`, `python -m mypy`,
  `python -m ruff check .`, `python -m ruff format --check .` e
  `lint-imports --no-cache` com `PYTHONPATH=src`.
- O oráculo (`tests/oracle/scipy_oracle.py`) precisa de scipy num venv
  separado (`pip install -r tests/oracle/requirements.txt` + pytest) e roda
  por caminho explícito com `PYTHONPATH=src` e a raiz do repo.
- Commits sem linha de coautoria de IA (preferência do autor).
- Publicação: a ideia original era dar datas futuras espaçadas de 5 a 24 h
  aos commits da Sprint 5 e publicar por tarefa agendada; para continuar em
  outra máquina, estas branches foram publicadas com as datas reais.

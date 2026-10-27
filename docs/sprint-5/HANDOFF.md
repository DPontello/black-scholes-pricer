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
Pendente de documentação: tolerâncias de renda (`REL/ABS_INCOME`,
`*_INCOME_ORACLE`) ainda fora da tabela do VV-PLAN.

**Próxima tarefa:** verificar os achados da §3.

## 3. Achados de revisão ainda NÃO verificados

Os verificadores caíram no limite de uso. Cada item abaixo precisa ser
confirmado (reproduzir) antes de corrigir; não são defeitos comprovados.

**feat/american-call-approx**
- (médio) Com taxa negativa, a call americana sai com preço europeu abaixo do
  intrínseco: a premissa da ADR-0002 (sem exercício antecipado) exige r >= 0.
  Sugestão: rejeitar CALL+AMERICAN com r contínua < 0 em `_price_single` e
  registrar a condição na ADR-0002; o teste de propriedade `_pares_de_calls`
  fixa hoje a igualdade com r em [-0.02, 0.30].
- (médio) O motor de simulação continua rejeitando a CALL americana, mas a
  ADR-0002 diz que os testes de rejeição passam a cobrir só PUT e o ROADMAP
  quer travas com call no `stress_grid`. Decidir: levar a marca aos
  resultados do motor ou registrar a restrição na ADR.
- (médio/baixo) Faltam testes de rejeição em `pnl_curve`, `stress_grid` e
  `portfolio_greeks`; PUT americana sem teste no motor; docstring de
  `PriceOptionUseCase` ainda diz "opção europeia".
- Docs ainda desatualizadas: ARCH §2.1/§3/§6 e VV-PLAN §6 (linha "Exercício
  AMERICAN"), catálogo de VOs sem `PricingApproximation`.

**fix/kernel-preco-nao-negativo**
- (baixo) `max(price, 0.0)` transforma -inf (overflow) em 0.0 válido; piso só
  para ruído finito (`if isfinite(price) and price < 0.0`).
- (baixo) Docstring promete "preço >= 0.0 sempre", falso se sair NaN de inf*0.
- (baixo, pré-existente) `log(s / k)` com underflow vaza `ValueError` cru; usar
  `log(s) - log(k)`. `s * sig_sqrt_tau` com underflow vaza `ZeroDivisionError`
  no gamma.

**feat/option-chain**
- (médio) `trades` validado com `self.trades < 0` (não negado, sem checar
  tipo): NaN/float/bool passam. Um revisor anterior refutou com o argumento
  de que o mypy barra floats e o resto do código valida ints assim.
- (baixo) `OptionChain.__post_init__` não normaliza `quotes` para tuple
  (gerador esgota antes da checagem de duplicatas). Refutado antes pelo
  mesmo argumento (mypy + suíte de contrato exige tuple).
- (baixo) `worst_quality` vaza `ValueError` cru se receber `None`.

**feat/implied-vol**: nenhuma revisão rodou. Pontos do próprio engenheiro:
preço exatamente no intrínseco descontado vira `CONVERGED` com sigma = 0.0
(decidir se o smile/painel aceita IV 0); piso do oráculo com K >> S fica
frouxo; ARCH §5–§7 e VV-PLAN §3/§7 não citam `implied_vol`.

**Pontos em aberto gerais**
- Vol realizada zero ou histórico insuficiente: a suíte de contrato exige
  vol > 0; o plano da fase 2 tira o ativo do painel com motivo.
- Campo `OptionQuote.volume` é volume financeiro, mas o nome não carrega a
  unidade (CONVENTIONS pede); renomear exige emendar a ADR-0003.
- `OptnStyle` (valores) e o vínculo série → ativo-objeto precisam ser
  conferidos no primeiro arquivo real do cadastro/COTAHIST.
- `valid_from` da tabela de custos: a B3 não publica vigência; o plano usa
  2025-08-01 (OC 025/2025-VPC), com a origem anotada.

## 4. Depois disso: fase 2

Especificação completa em [`plano-fase-2.md`](plano-fase-2.md): extensões de
domínio (`UnderlyingUnavailableError`, `RejectedSeries`,
`underlying_book_available`), adapter COTAHIST + cadastro + cache sqlite +
fixtures sintéticas, smile e preço TEÓRICO, tabela de custos versionada,
`RankIncomeOpportunitiesService`, relatório HTML e subcomando
`python -m options_engine painel`. Depois: documentação (ARCH §4.1,
CONVENTIONS, README), versão 0.4.0, merge na `master` e tag `v0.4.0`.

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

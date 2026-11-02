# Ledger — semana 2 (Montador e Carteira)

Plano: [`plans/2026-10-31-app-semana-2-montador-carteira.md`](plans/2026-10-31-app-semana-2-montador-carteira.md).
Branch `feat/app-semana-2`, a partir da `development` (`4bafb73`).

## 2026-11-01: Task 1 — lote do Cadastro na cadeia

- `InstrumentInfo.lot` vem do `AllcnRndLot`; vazio, ilegível ou não positivo vira `None`. `LoadedLibrary.lot(symbol)`, `SeriesRow.lot` e `SerieOut.lote` (no frontend, `Serie.lote`).
- Ruling: o app passa a ter **um** `LibraryLoader` só, compartilhado pelo `TrydMarketFeed`, pelo `EndOfDayMarket` e pelo lote (parâmetro `loader`). Antes, cada um lia a biblioteca à parte, e o Cadastro real tem 20 MB. Se errado: nada muda no resultado, porque o loader é thread-safe e relê quando a biblioteca muda.
- Cadastro real de 28/10: das 77.968 opções, 61.231 têm lote 100, 14.878 têm lote 1 (BOVA11 e outras) e 1.859 têm lote 10.
- Note (para a Task 6): no Cadastro, o `AllcnRndLot` do **à vista** é 1 (PETR4 = 1), não o lote padrão de 100. O aviso de lote da perna de ação não pode usar esse campo como está; decidir na Task 6 (lote 100 do mercado padrão, ou só avisar nas opções).
- Gates: 4647 testes (cobertura 97,4%), mypy, ruff, import-linter; frontend com `tsc`, 34 testes e build.

## 2026-11-01: Task 2 — perna de ação no `Strategy` e payoff no vencimento

- `StockLeg(symbol, side, quantity, price=None)`, com a mesma disciplina do `StrategyLeg`: quantidade >= 1, direção só no `Side` e preço finito e > 0 quando informado. `Strategy.stock_legs` aceita no máximo uma (`InvalidStrategyError`), do mesmo ativo-objeto das opções (`MixedUnderlyingError`). Estrutura só com ação tem `underlying`; o `expiry` dela levanta `InvalidStrategyError`.
- Kernel: `payoff`, `breakevens` e `payoff_extrema` ganham `stock` (quantidade assinada de ações, termo linear `stock · S`). A inclinação da cauda direita inclui as ações, então a venda coberta tem ganho máximo finito e a ação vendida tem perda ilimitada (`None`). O preço das ações vai no `offset`, como o prêmio.
- Ruling: as funções a mercado que já existiam (`mark_to_model_value`, `pnl_curve`, `stress_grid`, `portfolio_greeks`) passam a **incluir** a ação (valor = quantidade assinada × spot; delta += quantidade) em vez de recusá-la. Se ficassem como estavam, ignorariam a ação e o número sairia errado em silêncio. Se errado: nada, porque a ação a mercado é exatamente o spot.
- Conferido à mão: venda coberta (ação a 30, call 32 vendida a 1,00, 100 ações) com caixa de -2.900, breakeven 29, ganho máximo 300 e perda máxima -2.900; collar 28/33 com ganho de 310 e perda de -190; put protetora com perda de -250 e ganho ilimitado. A propriedade short == -long também vale com ação (hypothesis).
- Gates: 4674 testes (cobertura 97,4%), mypy, ruff e import-linter. Frontend sem mudança.

## 2026-11-01: Task 3 — fábricas e catálogo de modelos

- Fábricas novas, no mesmo padrão das antigas (`InvalidStrategyError` para a forma errada): `long_call`, `long_put`, `cash_secured_put` (uma perna), `covered_call` e `protective_put` (uma perna mais a ação comprada na mesma quantidade) e `collar` (put comprada abaixo da call vendida, mais a ação). As travas de débito e de crédito continuam no `vertical_spread`.
- `domain/model/templates.py`: `Family`, `TemplateLeg(option_type, side, ratio, offset)`, `Template` e `TEMPLATES` com os 18 modelos da spec §2.1, mais `template(key)` e `suggest_strikes(modelo, strikes, spot)`.
- Ruling (strikes sugeridos): o passo 0 é o strike mais perto do spot; em empate, o menor. Venda coberta e put coberta saem um strike fora do dinheiro; as travas de renda, um e dois strikes fora; as de direção, no dinheiro e um fora; strangle e collar, um de cada lado; iron condor, um e dois de cada lado. É só sugestão: o usuário troca o strike na cadeia. Se errado, muda a tabela `TEMPLATES`, sem mexer em código.
- Ruling: `Template.build(legs, stock)` confere se as pernas têm a forma do modelo (tipo e lado por strike, proporção e ação) antes de chamar a fábrica. Sem isso, uma trava com os lados trocados passaria pela fábrica genérica com o nome errado na tela.
- Gates: 4719 testes (cobertura 97,5%; `factories` e `templates` em 100%), mypy, ruff e import-linter.

## 2026-11-01: Task 4 — avaliação "hoje" com vol por perna, gregas e grade

- `domain/simulation/valuation.py`:
  - `today_value` (valor bruto) e `today_curve` (P&L com o caixa da montagem);
  - `structure_greeks`;
  - `scenario_matrix`, com os choques padrão de spot (-20% a +20%) e de vol (-10 a +10 pontos);
  - `american_call_approximated`.

  Os tipos da convenção (`TimeToExpiry`, `RiskFreeRate` e uma `Volatility` por perna) são conferidos na mesma base, como no motor.
- Ruling: módulo à parte, sem mexer no `engine`. O `engine` segue europeu-only e de vol única, porque a CLI e o painel usam. Aqui a call americana entra como europeia, e quem mostrar o número tem de mostrar `american_call_approximated` junto (ADR-0002). Put americana levanta `UnsupportedExerciseStyleError`; a tela mostra o vencimento sem a curva de hoje.
- Ruling: na grade, a célula em que o choque leva a vol de alguma perna a <= 0 sai `None` (a tela mostra "—"), em vez de um número com vol inventada. A grade é só de hoje: no vencimento a vol não muda o resultado.
- Regressão (hypothesis): com a mesma vol em todas as pernas, opções europeias e ação, valor, curva e as cinco gregas batem com `mark_to_model_value`, `pnl_curve` e `portfolio_greeks`.
- Gates: 4728 testes (cobertura 97,5%; `valuation` em 100%), mypy, ruff e import-linter. Nesta rodada a suíte levou 7min53 em vez de ~2min30 por carga da máquina; os testes novos levam menos de 0,3 s cada.

## 2026-11-01: Task 5 — probabilidade de lucro e custos por perna

- `domain/simulation/probability.py`: `probability_of_profit(strategy, spot, *, time_to_expiry, rate, vol)`. O spot no vencimento é lognormal risco-neutro, e as faixas de lucro saem dos breakevens exatos do kernel, com a ação inclusive. Entre dois breakevens o sinal não muda, então basta testar um ponto de cada faixa. Com tau ou vol zero, a resposta é 0 ou 1 pelo spot a termo.
- Conferido de forma independente:
  - call comprada, put comprada e venda coberta contra `N(d2)` no breakeven, escrito de novo no teste;
  - put vendida e iron condor contra uma grade estratificada de 200.000 pontos em probabilidade (tolerância `ABS_PROBABILITY_GRID` = 2e-5, documentada em `tests/_tolerances.py`).
- `income/costs.py`: `estimate_order_costs` (prêmio ou preço e quantidade por perna; uma ordem por perna) e `estimate_exercise_costs_by_leg`. As funções antigas passam a chamar essas e dão o mesmo número, bit a bit: os testes antigos seguem verdes, e um teste novo compara as duas.
- `income/net_result.py`: `net_result_at_expiry(strategy, spot, schedule, *, stock_already_held=False)` = bruto - montagem - exercício no cenário - IR estimado, com o IR limitado ao resultado do prêmio (ADR-0005). Bate com `covered_call_metrics` nos extremos e com `income/profile.result_at_expiry` numa trava. Ação vinda da carteira não paga a ordem de compra.
- Gates: 4752 testes (cobertura 97,5%; `costs`, `net_result` e `probability` em 100%), mypy, ruff e import-linter.

## 2026-11-01: Task 6 — serviço do montador

- `StrategyBuilderService.analyze(BuilderRequest) -> BuilderAnalysis` e `templates()`. O contrato (`BuilderLegInput`, `BuilderStockInput`, `BuilderRequest`, `BuilderAnalysis`, `ExpiryPoint`, `ExpiryResult`, `TodayResult` e `LegPriceOrigin`) fica nos ports de entrada. `StockOrigin` (`compra`/`carteira`) entra nos enums do domínio, para a carteira da Task 9 reaproveitar.
- Preço da perna, nesta ordem: o digitado (`DIGITADO`); o lado executável do book (`EXECUTAVEL`); o último com negócio (`INDICATIVO`); o teórico pelo smile (`TEORICO`). O teórico só existe com o strike dentro do smile. Sem nenhum deles, a perna fica sem preço, com aviso, e o resultado sai parcial: só o payoff bruto, sem vencimento líquido e sem hoje.
- Ação comprada junto entra pelo ask, ou pelo bid se for vendida. Sem book do ativo, entra pelo fechamento, rotulada `INDICATIVO`. Ação da carteira exige o preço médio digitado até a Task 12, e não paga a ordem de compra.
- Bug evitado (Task 5), FIXED aqui: o motor recusa opção americana até no vencimento, e as calls de ações da B3 são quase todas americanas. Então o resultado líquido e a probabilidade não funcionariam numa venda coberta real.
  - Ruling: `valuation.expiry_payoff`, `expiry_pnl` e `expiry_summary` aceitam qualquer estilo, supondo que a opção vai até o vencimento. O montador avisa ("o resultado no vencimento supõe que não há exercício antecipado").
  - `net_result_breakdown`, `net_result_at_expiry` e `probability_of_profit` passam a usar essas funções. O `engine` continua europeu-only.
- Ruling (lote): só as opções são conferidas contra o lote do Cadastro. O `AllcnRndLot` da ação é 1 (Task 1), e a fábrica já exige a mesma quantidade de ações e de opções na venda coberta, na put protetora e no collar.
- Ruling: ganho e perda líquidos máximos = máximo e mínimo do líquido nos pontos do eixo (0,5 a 1,5 × spot, mais strikes e breakevens), e ilimitados quando o bruto é ilimitado.
  - Na venda coberta, o máximo cai em S = K, sem exercício, e passa o das métricas de renda (cenário exercido) pelo custo de exercício.
  - Se errado: muda a escolha do ponto, não o modelo.
- Ruling: o serviço não recebe o CDI do perfil, porque a taxa vem do snapshot da cadeia, que o mercado já monta com o CDI. A probabilidade usa a vol do smile no spot; sem ela, a vol de referência da cadeia.
- `application/use_cases/_freshness.least_fresh` passa a ser compartilhado pelo serviço de mercado e pelo montador. O `tests/application/_mercado_falso.py` é o mercado falso novo; o teste do serviço de mercado segue com o dele.
- Gates: 4772 testes (cobertura 97,6%; `strategy_builder` em 100%), mypy, ruff e import-linter.

## 2026-11-01: Task 7 — API do montador, simulações e pasta do perfil

- API:
  - `GET /api/montador/modelos`;
  - `POST /api/montador/analise` (corpo: `ativo`, `pernas` com `ticker`/`lado`/`quantidade`/`preco?`, no máximo 8, `acao?` com `lado`/`quantidade`/`origem`/`preco?`, e `modelo?`);
  - `GET /api/simulacoes`, `POST /api/simulacoes` (201), `GET /api/simulacoes/{id}` e `DELETE /api/simulacoes/{id}` (204).

  Lado em português (`compra`/`venda`). Gregas: `theta_dia_util` (theta / 252, porque o tau do montador é em dias úteis) e `vega_ponto` (vega / 100).
- Simulações: `application/ports/simulations.py` (`SavedSimulation`, `UnreadableFile`, `SimulationRepository`, `SimulationUseCase`), `SimulationService` e `JsonSimulationRepository`. A simulação guarda o pedido, não a análise: ao reabrir, a análise sai com os preços do momento.
  - Arquivo `simulacoes/<id>.json` na pasta do perfil, `"versao": 1`, escrita atômica. Ilegível é listado e preservado.
  - Pasta do perfil fora do ar: `ProfileFolderUnavailableError`, e nada é criado.
  - Erros novos no domínio: `UnknownRecordError` (404) e `UnreadableRecordError` (422).
- FIXED (achado de 31/10): `ProfileService.create` recusa pasta vazia ou relativa ("caminho completo, a partir do disco ou da raiz"). Antes, pasta `""` gravava o `perfil.json` na pasta de onde o app foi aberto. `ProfileUseCase.active_folder()` dá a pasta do perfil aberto.
- Bug achado no teste ponta a ponta com os arquivos reais, FIXED (Task 6): a perda máxima líquida da venda coberta saía -2.456 contra -5.080 de bruta. O líquido só era calculado no eixo do gráfico (0,5 a 1,5 × spot), e a perda máxima fica com o ativo a zero. Os extremos líquidos passam a ser procurados também no zero, em cada strike, logo acima de cada strike (onde entra o custo de exercício) e na cauda.
- Ponta a ponta (APPDATA e perfil temporários, arquivos de 28/10, sem ponte): venda coberta de PETR4 com a PETRK541 (52,91, americana) vendida a 1,72 e a ação comprada a 52,52 (ask):
  - caixa de -5.080, breakeven 50,80;
  - ganho máximo de 211 (líquido 183,43, com IR de 25,77);
  - perda máxima de -5.080 (líquida -5.081,81);
  - probabilidade de 68%; delta de 47,9;
  - os dois avisos de americana.

  A simulação foi gravada na pasta do perfil.
- Gates: 4804 testes (cobertura 97,7%; os módulos novos em 100%), mypy, ruff e import-linter.

## 2026-11-02: Task 8 — frontend do Montador (fecha a Parte A)

- Tela `/montador`, que abre também pelo "Montar com PETR4" do Mercado:
  - à esquerda, a cadeia do ativo com um "+" em cada lado de cada strike;
  - no topo, ativo, vencimento do modelo, modelo pronto (por família), "+ ação" e "Limpar";
  - à direita, a tabela de pernas (lado, quantidade, preço editável com o automático como dica, origem do preço, ação comprada junto ou da carteira) e o resultado: resumo em português, números, gregas, avisos, gráfico (ECharts 5.5.1: vencimento líquido e bruto, hoje tracejado, linha do spot) e a grade;
  - por fim, salvar, abrir e apagar simulações. "Registrar como executada" fica desabilitado até a Parte B.
- Ruling (desvio do plano): rota nova `GET /api/montador/sugestao?ativo&modelo&vencimento` e `StrategyBuilderService.suggest`. Sem ela, a tela teria de repetir em TypeScript a regra dos strikes sugeridos, que é do domínio (`suggest_strikes`). Quantidade padrão 100 × proporção.
  - Em modelo com call e put (straddle, strangle, collar, iron condor), só entram strikes que têm os tipos pedidos.
  - Se errado: muda a rota, não o domínio.
- Ruling: o vencimento do modelo começa no primeiro **mensal** entre os vencimentos escolhidos na cadeia, e pode ser trocado. No teste com os arquivos reais, o iron condor vendido na semanal de 30/10 (2 dias úteis, séries pouco líquidas) saía com **débito** de R$ 6 pelo bid e pelo ask. No mensal de 19/11 sai com crédito de R$ 13, perda máxima de R$ 37 e breakevens em 51,78 e 53,04.
- Bug achado na tela, FIXED: o resumo dizia "ganha no máximo R$ 6,00" quando o melhor caso era perder R$ 6 (valor absoluto). Agora diz "no melhor caso ainda perde R$ 6,00", ou "no melhor caso empata".
- Ruling: o gráfico abre em volta do spot, dos strikes e dos breakevens, com 10% de folga, e não no eixo inteiro de 0,5 a 1,5 × spot. No eixo inteiro, estrutura estreita virava um risco fino.
- Ruling: recálculo 300 ms depois da última mudança e a cada atualização da cadeia (no máximo uma por segundo, que é o ritmo do WebSocket). Apagar simulação pede confirmação.
- Note: o build avisa que o pacote passou de 500 kB por causa do ECharts. É app local e o carregamento é do disco; fica como está.
- Testes do frontend: 53 (resumo, pernas, grade, gráfico com o ECharts falso no `setup.ts`, a página do Montador ponta a ponta com a API falsa e o "+" da cadeia), mais `tsc` e build. Backend: 4808 testes (cobertura 97,7%), mypy, ruff e import-linter.

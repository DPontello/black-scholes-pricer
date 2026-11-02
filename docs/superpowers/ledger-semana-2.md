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

## 2026-11-02: Task 9 — domínio da carteira

- Step 0, IN RFB 1.585/2015 conferida no texto oficial (normasinternet2.receita.fazenda.gov.br, ato 67494, visão multivigente). Está **vigente**: alterada pelas IN RFB 1.637/2016, 1.720/2017 e 1.916/2019, sem revogação. O **art. 60** (mercados de opções) confirma os quatro casos da spec §3.2:
  - II, a e § 1º: titular de call exercida, custo da ação = strike + prêmio;
  - II, b: lançador de call, venda = strike + prêmio, contra o custo de aquisição do ativo;
  - II, c: titular de put, venda = strike - prêmio, contra o custo da compra à vista;
  - II, d e § 1º: lançador de put, custo da ação = strike - prêmio.

  Mais duas regras do mesmo artigo:
  - § 2º: os valores pagos ou recebidos entram pela **média ponderada**; é o preço médio por perna;
  - § 3º: sem encerramento nem exercício, no vencimento o prêmio é ganho do lançador e perda do titular; é o pó.
- `domain/portfolio`:
  - `model.py`: `Operation` com pernas (`OptionLegRef`, `StockLegRef` com origem) e eventos (`Open`, `Close`, `Exercise`, `Assignment`, `Expired`). A validação roda em `leg_states`, que recalcula tudo a partir dos eventos.
  - `positions.py`: `open_legs`, `is_closed`, `realized_result`, `consolidate` e `free_shares`.
  - `exercise.py`: `stock_from_option` e `apply_exercise`.
  - `expiry.py`: `expiry_outcome`.
- Ruling: exercício e atribuição fecham a perna da opção **sem resultado próprio**. O prêmio vai para o preço da ação pelo art. 60; contá-lo nas duas pernas daria o prêmio em dobro.
  - `apply_exercise` grava o evento da opção e o movimento da ação (custo 0, porque o custo do exercício fica no evento da opção).
  - A ação que sai vem da perna de ação da própria operação; senão, da ação "da carteira", pelo preço médio dela (`Close.cost_basis`); senão, a operação fica vendida em ações.
  - A ação que entra vira perna de ação comprada da operação.
  - Conferido: a venda coberta atribuída fecha com +300 = (32 - 30 + 1) × 100, o ganho máximo.
- Ruling: a ação "da carteira" não é comprada na operação (`Open` recusado) e só sai pelo custo médio informado. Quem baixa a posição de ações das outras operações é o serviço (Task 11), para o lucro da ação não contar duas vezes.
- Ruling: custos do resultado realizado:
  - o real informado no evento, senão a estimativa da ADR-0005 (ordem de opção, ordem de ação ou exercício) pela tabela vigente na data do evento;
  - o pó não tem custo.
- Ruling: ações livres = ações compradas nas operações sem ação "da carteira", menos as calls vendidas delas, menos as calls vendidas das operações "da carteira". A put protetora não prende ação.
- Gates: 4854 testes (cobertura 97,8%; `domain/portfolio` em 99-100%), mypy, ruff e import-linter.

## 2026-11-02: Task 10 — repositório das operações

- `JsonOperationRepository(folder)`: `list()`, `save(operation)` e `load(id)`.
  - Arquivo `operacoes/<AAAA-MM-DD>_<ATIVO>_<id8>.json` (data de criação), `"versao": 1`, escrita atômica, regravado a cada evento; continua um arquivo por operação.
  - JSON em português, legível à mão: pernas `opcao` (tipo, strike, vencimento, estilo `americana`/`europeia`) e `acao` (origem); eventos `abertura`, `encerramento` (com `custo_medio` só na ação da carteira), `exercicio`, `atribuicao` e `po`.
- Ruling: o arquivo é ilegível quando o JSON está quebrado, a versão é desconhecida, falta campo, o tipo de evento é desconhecido **ou o domínio recusa os eventos** (por exemplo, pó numa perna de ação). Nesse caso é listado com o motivo e **nunca sobrescrito**: `save` de uma operação cujo arquivo está ilegível levanta `UnreadableRecordError`.
- Ruling: o `load` procura pelo prefixo de 8 caracteres e confere o id inteiro dentro do arquivo, então dois ids com o mesmo começo não se confundem. Id fora de `[0-9A-Za-z_-]{8,64}` não vira nome de arquivo.
- `UnreadableFile` passou para `application/ports/outbound.py`, compartilhado com as simulações.
- Gates: 4869 testes (cobertura 97,8%; `storage/operations` em 99%), mypy, ruff e import-linter.

## 2026-11-02: Task 11 — serviço da carteira

- Contrato em `application/ports/portfolio.py` (como as simulações, fora do `inbound.py`): `PortfolioUseCase`, `RegisterOperation` (pernas com execuções `Fill`, ação opcional `RegisterStock`), `OperationView`, `PortfolioView` e `ExpiryNotice`. `OperationRepository` em `ports/outbound.py`.
- `PortfolioService(repository_for, clock, schedules, new_id, market_timezone)`: o repositório é pedido a cada chamada (perfil trocado, pasta trocada). Sem `calendar`: o vencimento já é dia de pregão, e "encerrado" é depois das 18h do dia no fuso da B3 ou qualquer dia seguinte.
- `register`: cada perna de opção precisa de execução. A ação `COMPRA` precisa de execução. A ação "da carteira" é comprada, sem execução, e exige ações livres para as calls vendidas da operação (`free_shares` das outras).
- `add_stock`: operação "ações à mão" de uma perna de ação, custo 0 (a compra é anterior ao app; o preço médio informado já é o custo).
- `exercise`/`assign` conferem o lado da perna; `open_operations` traz as abertas (mais recentes primeiro), os totais por ativo e os arquivos ilegíveis; `history` traz as encerradas com o resultado realizado.
- `process_expiries(closes)`: grava o pó das pernas fora do dinheiro estrito uma vez só (a perna zerada não volta) e devolve os avisos "registre o exercício" e "aguardando o fechamento". Os avisos não entram no `PortfolioView`; a API (Task 13) junta os dois.
- Ruling: evento novo `TransferOut` (JSON `transferencia`, com a operação de destino). Na atribuição de call com ação "da carteira", as ações saem das operações que as têm livres, sem resultado ali, porque quem vende é a operação de destino. Sem isso o lucro da ação contaria duas vezes ou as ações ficariam no perfil depois de entregues.
- Ruling **para o autor conferir**: o custo da venda "da carteira" é o **preço médio de todas as ações do ativo no perfil** (spec §3.2, "pelo preço médio dela"). As ações saem **na proporção das livres de cada operação** (maiores restos; no empate, a mais antiga), para o médio de cada operação e o do perfil não mudarem com a venda, como na regra do preço médio. O arredondamento por ação inteira pode mexer centavos: 100 ações de lotes de 100 a 28, 30 e 32 saem 34/33/33, e o médio das que ficam vai de 30,00 a 30,01. A alternativa seria tirar por ordem de compra (FIFO), que muda o médio de quem fica.
- Ruling: a operação de destino é gravada antes das fontes. Se a gravação parar no meio (nuvem fora do ar), repetir a atribuição é recusado (a perna já foi atribuída) em vez de tirar as ações duas vezes.
- `domain/portfolio/exercise.py`: `takes_portfolio_shares(operation, leg, quantity)`, a mesma regra que o `apply_exercise` usa para saber se a ação sai "da carteira".
- Gates: 4898 testes (cobertura 97,8%; `use_cases/portfolio` em 100%), mypy, ruff e import-linter.

## 2026-11-02: Task 12 — cotação das pernas e assinatura da carteira

- Port novo `OptionQuotePort.get_option_quotes(symbols) -> Mapping[str, OptionQuote | str]`, dentro do `MarketPort`. Toda série pedida volta com a cotação ou o motivo: "sem cotação ao vivo", "aguardando dados", "série desconhecida no cadastro", "sem estilo de exercício no cadastro", o vínculo ambíguo e, no fim de dia, "sem negócio no pregão de AAAA-MM-DD".
- `watch(..., portfolio_series=())`: a ordem do limite de tópicos é ativos, carteira e cadeia, então a cadeia é cortada antes da carteira. A série que está na carteira e na cadeia é assinada uma vez só, com a prioridade da carteira.
- `TrydMarketFeed.get_option_quotes`: os termos vêm do cadastro (o ativo-objeto declarado, senão o dono único da raiz). O feed guarda os tickers da última assinatura: a série fora dela (cortada pelo limite) ou com a ponte caída sai "sem cotação ao vivo", nunca com o preço que sobrou no quadro.
- `EndOfDayMarket.get_option_quotes`: pelo `CotahistOptionChainAdapter.get_option_quotes`, com o mesmo vínculo e as mesmas rejeições da cadeia. O `FallbackMarket` escolhe a fonte como na cadeia, sem misturar fontes por série.
- `MarketViewService.follow(..., portfolio_underlyings=(), portfolio_series=())`: os ativos da carteira entram depois da lista do perfil. Quem chama com a carteira é o WebSocket (Task 13).
- `PortfolioService(..., market=, calendar=)`. `open_operations` marca cada perna aberta e cada total por ativo (`LegMark`):
  - preço de zerar: bid para a comprada e ask para a vendida, na opção e na ação; P&L não realizado bruto, sem o custo de zerar;
  - sem esse lado, `price` e `unrealized` ficam vazios, `reason` diz por quê e `theoretical` traz o prêmio teórico: BS com a vol do smile do vencimento no strike, senão a vol de referência do ativo. A cadeia só é pedida para a série sem preço de zerar;
  - o não realizado da operação é `None` quando alguma perna aberta não tem preço de zerar;
  - `source`: a saúde menos fresca da consulta, como na cadeia e no montador.
- Ruling: só o lado de zerar vale como preço. O último negócio (o "indicativo" do montador) não marca a carteira, porque a spec manda mostrar o teórico quando falta o lado.
- Ruling: put americana fica sem teórico (sem fórmula fechada, ADR-0002), em vez de mostrar o valor da europeia. Ação sem lado de zerar também fica sem teórico.
- `PortfolioService.symbols()` (os ativos e as séries abertas, para a assinatura) e `average_price(symbol)` (o médio das ações compradas no perfil).
- Montador: `StrategyBuilderService(..., portfolio_average=)`. A ação "da carteira" sem preço digitado usa o preço médio do perfil, com a origem nova `preco_medio` ("preço médio da carteira" na tela). Sem ações no perfil, o erro pede o preço médio. A ligação com a carteira na composição fica para a Task 13.

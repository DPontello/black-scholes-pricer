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

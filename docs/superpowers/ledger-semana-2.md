# Ledger — semana 2 (Montador e Carteira)

Plano: [`plans/2026-10-31-app-semana-2-montador-carteira.md`](plans/2026-10-31-app-semana-2-montador-carteira.md).
Branch `feat/app-semana-2`, a partir da `development` (`4bafb73`).

## 2026-11-01: Task 1 — lote do Cadastro na cadeia

- `InstrumentInfo.lot` vem do `AllcnRndLot`; vazio, ilegível ou não positivo vira `None`. `LoadedLibrary.lot(symbol)`, `SeriesRow.lot` e `SerieOut.lote` (no frontend, `Serie.lote`).
- Ruling: o app passa a ter **um** `LibraryLoader` só, compartilhado pelo `TrydMarketFeed`, pelo `EndOfDayMarket` e pelo lote (parâmetro `loader`). Antes, cada um lia a biblioteca à parte, e o Cadastro real tem 20 MB. Se errado: nada muda no resultado, porque o loader é thread-safe e relê quando a biblioteca muda.
- Cadastro real de 28/10: das 77.968 opções, 61.231 têm lote 100, 14.878 têm lote 1 (BOVA11 e outras) e 1.859 têm lote 10.
- Note (para a Task 6): no Cadastro, o `AllcnRndLot` do **à vista** é 1 (PETR4 = 1), não o lote padrão de 100. O aviso de lote da perna de ação não pode usar esse campo como está; decidir na Task 6 (lote 100 do mercado padrão, ou só avisar nas opções).
- Gates: 4647 testes (cobertura 97,4%), mypy, ruff, import-linter; frontend com `tsc`, 34 testes e build.

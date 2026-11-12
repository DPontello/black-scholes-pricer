# Architecture Decision Records

Formato MADR curto: **Status / Contexto / Decisão / Consequências**. Uma
decisão por arquivo, numeração sequencial por ordem de registro — o número
não implica prioridade nem sprint.

Uma ADR aceita não é editada para mudar de ideia: a decisão nova vira outra
ADR que a **substitui** (`Status: Substituída por ADR-NNNN`), preservando a
trilha de auditoria.

As ADRs planejadas pela Sprint 4 (float64 vs Decimal, stdlib-only, contrato
batch-first, hexagonal sem DI framework, BUSINESS_252, async/CPU-bound,
pydantic só na borda) continuam a numeração a partir da última existente.

| ADR | Título | Status | Data |
|---|---|---|---|
| [0001](0001-renda-antes-da-api.md) | Painel de renda antecipado para antes da API REST | Aceita | 2026-10-26 |
| [0002](0002-calls-americanas-como-europeias.md) | Calls americanas de ação precificadas como europeias (emenda à decisão nº 2) | Aceita | 2026-10-26 |
| [0003](0003-option-chain-port.md) | `OptionChainPort` e lado de book ausente como `None` | Aceita | 2026-10-26 |
| [0004](0004-preco-executavel-e-livro-vazio.md) | Preço executável por lado e regra de livro vazio | Aceita | 2026-10-26 |
| [0005](0005-metricas-de-rendimento.md) | Métricas de rendimento, anualização e custos | Aceita | 2026-10-26 |
| [0006](0006-fontes-de-dados-de-opcoes.md) | COTAHIST como fonte da fase 1; intraday via Necton depois | Aceita | 2026-10-26 |
| [0007](0007-painel-html-estatico.md) | Painel como relatório HTML estático | Aceita | 2026-10-26 |
| [0008](0008-intraday-tryd-rtd.md) | Intraday via RTD do Tryd (emenda à decisão 3 da ADR-0006) | Aceita, com correções do spike | 2026-10-28 |

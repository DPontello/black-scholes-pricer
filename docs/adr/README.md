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

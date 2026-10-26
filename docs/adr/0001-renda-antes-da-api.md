# ADR-0001 — Painel de renda antecipado para antes da API REST

- **Status:** Aceita
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

O roadmap original previa Sprint 4 (API REST, `v1.0.0`) e, só depois, a
Fase 5 com volatilidade implícita e dividendos. O caso de uso que gera valor
agora é um **painel de renda com opções** (venda coberta, put coberta e
travas de crédito) comparando vários ativos com dados reais da B3. Ele exige
volatilidade implícita, cadeia de opções real e métricas de rendimento —
nada disso depende da API.

## Decisão

A **Sprint 5 — Painel de Renda** passa à frente da Sprint 4. Ordem de
execução: S3 → **S5** → S4. A S5 absorve a volatilidade implícita da antiga
Fase 5 (dividendos discretos e hardening de V&V permanecem fora). A tag da
S5 é `v0.4.0`; a S4 mantém `v1.0.0` e passa a depender da S5.

## Consequências

- A regra de corte do roadmap continua valendo: a S5 só começa com a tag
  `v0.3.0` criada e o CI verde.
- O painel nasce com seu próprio adapter de apresentação (ADR-0007); a API
  da S4, quando vier, reutiliza o mesmo use case — sem retrabalho de domínio.
- As ADRs planejadas pela S4 continuam na numeração após esta série.

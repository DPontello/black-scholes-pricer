# ADR-0007 — Painel como relatório HTML estático

- **Status:** Aceita
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

O painel precisa ser visual (tabela comparativa por ativo, estrutura e
vencimento, com filtros e rótulos de qualidade), mas a API REST foi
adiada (ADR-0001) e o projeto mantém o core sem dependências.

## Decisão

Fase 1: **relatório HTML estático** gerado por um adapter de apresentação,
acionado pela CLI existente (`python -m options_engine`), só com a stdlib.

- O adapter consome o resultado do use case `RankIncomeOpportunitiesService`;
  nenhuma regra de negócio no adapter.
- Conversões de exibição (Θ por dia útil, vega por ponto, percentuais) vivem
  só no adapter (decisão ratificada nº 8).
- Todo texto vindo de dados externos é escapado (`html.escape`).
- CSS inline; sem JavaScript de terceiros.

## Consequências

- Zero dependências novas; o relatório abre em qualquer navegador e pode ser
  arquivado por data (rastreabilidade).
- A API da S4 reutiliza o mesmo use case; o HTML pode virar uma página
  servida pela API depois, sem tocar o domínio.
- Sem interatividade rica na fase 1 (ordenar/filtrar no navegador fica para
  depois, se necessário).

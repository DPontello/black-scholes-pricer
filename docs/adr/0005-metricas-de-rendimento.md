# ADR-0005 — Métricas de rendimento, anualização e custos

- **Status:** Aceita (itens marcados como **pendentes** aguardam a mesa)
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

O painel compara estruturas de renda entre ativos e vencimentos diferentes.
Sem uma base de capital, uma regra de anualização e um tratamento de custos
definidos, os números não são comparáveis entre si nem com a renda fixa.

## Decisão

1. **Put coberta** (venda de put com caixa reservado): rendimento no
   período = `prêmio / strike`. Capital reservado = strike; é a base mais
   conservadora.
2. **Anualização composta em dias úteis:**
   `(1 + r_período) ^ (252 / du) − 1`, com `du` contado pelo
   `TradingCalendar` (calendário B3, intervalo meio-aberto já ratificado).
3. **Comparação com o CDI:** o painel exibe o rendimento anualizado e o
   **excesso sobre o CDI** do mesmo período, a partir do `RiskFreeRate`
   (CDI efetivo anual, base 252 — CONVENTIONS §3).
4. **Custos na fase 1**, todos parametrizáveis e nunca hardcoded:
   - emolumentos da B3 sobre o prêmio;
   - corretagem da Necton por ordem;
   - IR de 15% sobre o ganho (estimativa de swing trade).

   O painel mostra rendimento **bruto** e **líquido**.

### Pendentes (propostos, aguardando a mesa)

5. **Venda coberta:** rendimento = `prêmio / spot`. Proposto por coerência
   com o item 1 (capital bruto empatado).
6. **Trava de crédito:** retorno sobre risco =
   `crédito / (largura − crédito)`, com a largura entre strikes como proxy
   do risco máximo. A margem real da B3 não é modelada na fase 1.
7. **Tamanho de referência da posição:** corretagem fixa por ordem não
   escala com o prêmio; o rendimento líquido exige um tamanho de posição
   (ex.: lote padrão). Valor padrão a definir.
8. **Critério de ordenação padrão do ranking:** proposto = rendimento
   anualizado líquido; configurável.

## Premissas a verificar (gate do spike da Sprint 5)

- Tabela de emolumentos vigente da B3 para opções sobre ações.
- Tabela de corretagem vigente da Necton para opções.
- Tratamento de IR: alíquota de swing trade, apuração mensal e compensação
  de prejuízos. Na fase 1 o painel faz uma **estimativa por operação**,
  rotulada como tal — não é cálculo fiscal.

## Consequências

- Métricas em módulo puro novo (`domain/income/`), em forma fechada.
- Unidades de rendimento (decimal, período vs anual) entram no
  CONVENTIONS na implementação, com unidade no nome do campo
  (ex.: `yield_period`, `yield_annual_252`).
- Tabelas de custo vivem em configuração versionada, com data de vigência,
  para manter a rastreabilidade de qual tabela gerou cada número.

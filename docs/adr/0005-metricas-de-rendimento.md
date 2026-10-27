# ADR-0005 — Métricas de rendimento, anualização e custos

- **Status:** Aceita (itens 5–8 fechados pela mesa em 2026-10-26; premissas
  verificadas no spike da mesma data; modelo de custos fechado pela mesa no
  mesmo dia)
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

### Itens fechados pela mesa em 2026-10-26

5. **Venda coberta:** rendimento = `prêmio / spot` (capital bruto empatado,
   coerente com o item 1).
6. **Trava de crédito:** retorno sobre risco =
   `crédito / (largura − crédito)`, com a largura entre strikes como proxy
   do risco máximo. A margem real da B3 não é modelada na fase 1.
7. **Tamanho de referência da posição:** **100 ações por estrutura**
   (parâmetro do comando). Necessário porque a corretagem fixa por ordem
   não escala com o prêmio.
8. **Critério de ordenação padrão do ranking:** **rendimento anualizado
   líquido**; configurável no comando.

## Premissas a verificar (gate do spike da Sprint 5)

- Tabela de emolumentos vigente da B3 para opções sobre ações.
- Tabela de corretagem vigente da Necton para opções.
- Tratamento de IR: alíquota de swing trade, apuração mensal e compensação
  de prejuízos. Na fase 1 o painel faz uma **estimativa por operação**,
  rotulada como tal — não é cálculo fiscal.

## Valores da tabela de custos (spike 2026-10-26)

- **Emolumentos da B3 — opções sobre ações, pessoa física, operação
  normal:** **0,1340% do prêmio, por lado** (comprador e vendedor) =
  0,0370% de negociação + 0,0275% de liquidação + 0,0695% de registro. Sem
  faixa de volume; já inclui PIS/COFINS e ISS da própria B3. A página **não
  traz data de vigência**; consultada em 26/10/2026:
  <https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/opcoes-de-acoes/>
  O OC 025/2025-VPC (nova tarifação desde 01/08/2025) declara que não
  mudou a tarifação de derivativos. As tabelas de day trade (regressiva,
  de 0,0450% a 0,0260%) e de fundos e clubes (0,0950%) não se aplicam ao
  painel.
- **Exercício:** cobrado pela tabela do **mercado à vista**, sobre o volume
  financeiro ao strike: **0,0300%** para ADTV <= R$ 3 mi (0,00500% de
  negociação + 0,02240% de CCP + 0,0026% de TTA) e 0,0225% acima disso.
  Página consultada em 26/10/2026:
  <https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/tarifas-de-acoes-e-fundos-de-investimento/a-vista/>
- **Corretagem da Necton: R$ 0,00 por ordem**, informada pela mesa em
  26/10/2026 a partir da própria conta. Não há tabela oficial pública (o
  site da Necton não respondeu durante o spike), e o valor citado por
  terceiros (R$ 4,90 por ordem) não é usado. O parâmetro continua
  existindo: se a conta mudar, muda a tabela versionada, não o código.
- **IR: 15%** sobre o ganho em operações comuns (Lei 11.033/2004, art. 2º,
  II), consultada em 26/10/2026:
  <https://www.planalto.gov.br/ccivil_03/_ato2004-2006/2004/lei/l11033.htm>
  A MP 1.303/2025, que unificaria a alíquota em 17,5%, perdeu a vigência;
  os 15% seguem valendo em 2026. O painel faz **estimativa por operação**,
  rotulada como tal:
  - o IRRF de 0,005% sobre o saldo positivo dos prêmios do dia (art. 2º,
    §1º, II) e a compensação de prejuízos (Lei 8.981/1995, art. 72, §4º)
    **não são modelados**;
  - a isenção de R$ 20 mil por mês vale só para alienação de ações no
    mercado à vista (art. 3º, I) e **não se aplica a opções**.

## Modelo de custos e decisões de cálculo

Regras do cálculo, por estrutura e no tamanho de referência do item 7:

- **Emolumento por perna:** cada perna paga a taxa sobre o próprio prêmio
  (`taxa × prêmio × ações`), vendida ou comprada, e o custo da estrutura é
  a soma das pernas.
- **Uma ordem por perna:** corretagem = valor por ordem × número de pernas
  de opção (put coberta: 1; trava de crédito: 2).
- **IR depois dos custos e só sobre ganho positivo:**
  `IR = alíquota × max(ganho bruto − emolumentos − corretagem, 0)`.

Escolhas de cálculo **aprovadas pela mesa em 2026-10-26**:

1. **Rendimento líquido na base do bruto:** o líquido usa a mesma base de
   capital do bruto — strike (put coberta), spot (venda coberta) e
   largura − crédito (trava de crédito) —, e não a perda máxima líquida.
2. **IR só sobre o prêmio:** na venda coberta, a valorização da ação até o
   strike fica fora da estimativa de IR.

Duas propostas da implementação foram **recusadas pela mesa** em
2026-10-26 e substituídas pelas decisões abaixo, tomadas no mesmo dia:

3. **Venda coberta paga a compra da ação e o exercício.** Os custos de
   montagem incluem a ordem da opção (emolumento sobre o prêmio +
   corretagem) **e a compra das ações** (emolumento do à vista sobre
   `spot × ações` + corretagem de uma ordem). No cenário em que a call é
   exercida (ganho máximo), entram também os custos do **exercício**
   (emolumento do à vista sobre `strike × ações` + corretagem de
   exercício). Proposta recusada: contar só a ordem da opção.
4. **Breakeven, ganho máximo e perda máxima brutos e líquidos.** O painel
   mostra os dois, como já faz com o rendimento. O líquido desconta os
   custos incorridos naquele cenário (montagem + exercício das pernas
   exercidas) e, no ganho máximo, o IR estimado conforme o item 2; perda
   não paga IR. Proposta recusada: só os brutos.
5. **Corretagem de exercício da Necton: R$ 0,00**, informada pela mesa em
   2026-10-26 (o valor de terceiros, R$ 25,21 + 0,5%, não é usado).
   Parâmetro próprio na tabela versionada.

Pelo mesmo princípio dos itens 3 e 4, o exercício entra nos cenários em que
acontece também na **put coberta** (put exercida: compra das ações ao
strike, nos cenários de breakeven e perda máxima) e na **trava de crédito**
(pernas que terminam dentro do dinheiro). A regra exata de cada cenário fica
documentada nas docstrings de `domain/income/`.

> **Estado da implementação (2026-10-27):** itens 3–5 implementados na
> branch `feat/income-metrics`. Notas de implementação (regra completa nas
> docstrings de `domain/income/`):
>
> - **IR de cada cenário** = alíquota × max(min(resultado, resultado do
>   prêmio), 0), com resultado do prêmio = prêmio − ordens de opção. Tira a
>   valorização da ação da base (escolha 2) sem deixar de abater uma perda
>   da ação; perda não paga IR (item 4).
> - **Exercício** só com o strike estritamente ultrapassado (no dinheiro não
>   há exercício), cobrado por perna, ao próprio strike.
> - **Venda coberta:** o ganho máximo líquido é o do cenário exercido (item
>   3). Com S = K a call não é exercida e a ação fica marcada a K sem custo
>   de venda: esse ponto vale mais que o ganho máximo, no máximo pelo custo
>   de exercício (≈ 0,03% do strike × ações na tabela de referência).
> - **Breakeven líquido:** `None` quando o resultado líquido nunca chega a
>   zero (prêmio menos montagem negativo; na venda coberta, zero acima do
>   strike); igual ao strike vendido quando a troca de sinal acontece no
>   salto do custo de exercício.

## Consequências

- Métricas em módulo puro novo (`domain/income/`), em forma fechada.
- Unidades de rendimento (decimal, período vs anual) entram no
  CONVENTIONS na implementação, com unidade no nome do campo
  (ex.: `yield_period`, `yield_annual_252`).
- Tabelas de custo vivem em configuração versionada, com data de vigência,
  para manter a rastreabilidade de qual tabela gerou cada número.

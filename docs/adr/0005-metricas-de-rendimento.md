# ADR-0005 — Métricas de rendimento, anualização e custos

- **Status:** Aceita (itens 5–8 fechados pela mesa em 2026-10-26; premissas
  verificadas no spike da mesma data; dois itens do modelo de custos
  **em decisão pela mesa**)
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

**Em decisão pela mesa (26/10/2026)** — propostas da implementação, ainda
sem aprovação:

3. **Custos da venda coberta só da ordem da opção:** a compra da ação e o
   exercício ficariam fora dos custos.
4. **Extremos e breakeven brutos:** breakeven, ganho máximo e perda máxima
   sairiam sem custos.

## Consequências

- Métricas em módulo puro novo (`domain/income/`), em forma fechada.
- Unidades de rendimento (decimal, período vs anual) entram no
  CONVENTIONS na implementação, com unidade no nome do campo
  (ex.: `yield_period`, `yield_annual_252`).
- Tabelas de custo vivem em configuração versionada, com data de vigência,
  para manter a rastreabilidade de qual tabela gerou cada número.

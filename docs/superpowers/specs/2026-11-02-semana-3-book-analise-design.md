# App de opções — semana 3: Book de recomendações e Análise de mercado — desenho (2026-11-02)

> Detalha a semana 3 do desenho geral
> ([`2026-10-28-app-opcoes-design.md`](2026-10-28-app-opcoes-design.md), §2 itens 1 e 3, §6.6, §7
> itens 3 e 6, e §8). As regras marcadas **(autor, 02/11)** foram respondidas pelo autor em
> enquete; o resto é decisão de quem escreveu, revisável.

## 1. Escopo

Entrega da semana, em três partes usáveis:

1. **Histórico de IV:** a IV no dinheiro de 30 dias úteis de cada pregão, a HV de 21 dias, o IV
   rank e o percentil, calculados dos COTAHIST da biblioteca.
2. **Book de recomendações:** as melhores operações de cada família entre os ativos da lista do
   perfil, por regras transparentes, cada item com o porquê em números e "abrir no montador".
3. **Análise de mercado:** uma aba por ativo no Mercado com o preço, a IV contra a realizada no
   ano, o IV rank e o percentil, o smile por vencimento e a estrutura a termo.

O histórico de IV vem antes do book porque os critérios de Volatilidade e das Direcionais sem
visão usam o IV rank.

Fora da semana 3 (como no desenho geral): alertas, vencimentos, proventos e ajustes, IR mensal e
instalador (semana 4); teste com a mãe do autor e acabamento (semana 5).

### Decisões do autor (02/11)

- A semana tem o **book e a análise**, o book primeiro.
- O book varre pelo **fim de dia** (o último COTAHIST importado), rotulado com o pregão. Ao abrir
  um item no montador, os preços são refeitos pela cadeia do momento (ao vivo, se houver). O
  limite de 600 tópicos da ponte não comporta várias cadeias ao vivo.
- O book varre **a lista de ativos do perfil**.
- **Direcionais nos dois modos:** com visão (o usuário diz a direção, o alvo e o vencimento) e sem
  visão ("opções baratas" pela vol, rotuladas como não direcionais).
- Os **presets ficam salvos no perfil**, com os valores editados, e um botão volta ao padrão.
- Abordagem: **varredura própria por família** (módulos puros no domínio sobre a cadeia de fim
  de dia) e **histórico de IV pelos COTAHIST** da biblioteca, em cache.

### Correção do desenho geral

O §6.6 do desenho geral diz que vol alta sugere "borboleta vendida". Pelo payoff, a borboleta que
ganha com o ativo parado e a vol caindo é a **comprada** (compra as asas e vende o miolo), que é
como o modelo já está no montador (`borboleta_comprada`). Esta spec usa a comprada para vol alta
**(autor, 02/11)**.

## 2. Histórico de IV

### 2.1 Regras

- **IV de 30 dias úteis por pregão:** para cada vencimento com pelo menos 5 dias úteis, a vol no
  dinheiro é a do smile do pregão no spot (fechamento do ativo). O smile usa o meio da melhor
  oferta de compra e de venda no fechamento, só nas séries com os dois lados e `bid <= ask`.
  Com a variância total `w = σ² x τ` (τ = dias úteis / 252), a IV de 30 dias úteis é
  `sqrt(w30 / τ30)`, com `w30` interpolado linearmente em τ entre o vencimento logo antes e o
  logo depois de 30 dias úteis.
- Só um lado disponível (todos antes ou todos depois de 30 dias úteis): vale a vol do vencimento
  mais perto, **marcada como extrapolada**. Pregão sem smile no spot (menos de duas séries com
  book em volta do spot): sem IV nesse pregão. Buraco não é interpolado.
- **HV de 21 dias:** a vol realizada que já existe (log-retornos dos fechamentos, `sqrt(252)`).
- **IV rank** = `(IV hoje - mínima) / (máxima - mínima)` e **percentil** = fração dos pregões com IV
  abaixo da de hoje, na janela dos últimos **252 pregões** com IV. Com menos de **60 pregões**, o
  rank e o percentil saem vazios, com o motivo.
- **Taxa:** o CDI do perfil, constante em todo o histórico. É uma aproximação, rotulada na tela.
- **Regime de vol** de cada ativo: **alta** com IV rank >= 50% e IV 30 >= HV 21; **baixa** com IV rank
  <= 30% e IV 30 <= HV 21; senão **neutra**. Sem rank (histórico curto), o regime sai da IV contra
  a HV, com margem de 10% (alta acima de 1,1 x HV, baixa abaixo de 0,9 x HV), rotulado.

### 2.2 Leitura e cache

- Uma passada em fluxo por cada COTAHIST da biblioteca, pregão a pregão, guardando só o à vista e
  as opções. O vínculo da série com o ativo-objeto é o mesmo do adapter COTAHIST (cadastro, raiz
  única, classe do ESPECI). As séries rejeitadas lá (strike corrigido, book cruzado, divergentes)
  também ficam fora aqui.
- Cache sqlite na raiz da biblioteca, por pregão e ativo: só os pregões ainda não calculados são
  lidos. Importar um diário calcula um pregão.
- **Premissa a conferir no arquivo real:** o COTAHIST anual vem ordenado por pregão. Se não vier,
  a leitura agrupa em memória só as raízes dos ativos pedidos.

## 3. Book de recomendações

### 3.1 Item do book

Cada item tem: família, estrutura (a chave do modelo do montador), ativo, vencimento e dias
úteis, as pernas (ticker, tipo, strike, lado, quantidade, prêmio e a qualidade do preço), o
**critério** (nome, valor e unidade), os **números de apoio** (rótulo, valor e unidade), **o
porquê** em uma frase e o **pedido do montador** pronto (o mesmo `BuilderRequest` das
simulações).

- Só entra no book o item com todas as pernas a preço **EXECUTAVEL**. Com alguma perna
  INDICATIVO ou TEORICO, o item vai para as **referências**, à parte e rotuladas, como no painel
  de renda.
- Filtros de liquidez do preset (negócios no pregão e spread) em **todas** as pernas.
- O que não entra por dado ruim (sem preço, sem strike para a outra perna, série rejeitada) vira
  **exclusão com motivo**. Fora da faixa de delta é filtro, não exclusão.
- Resultado líquido de custos e IR pela ADR-0005, como no montador.
- Por estrutura, os 5 melhores itens pelo critério.

### 3.2 Presets

| | Conservador | Moderado | Arrojado |
|---|---|---|---|
| Delta (módulo) da perna principal | 0,10 a 0,25 | 0,15 a 0,35 | 0,25 a 0,45 |
| Negócios mínimos no pregão, por perna | 20 | 10 | 3 |
| Spread máximo, (ask - bid) / meio | 10% | 20% | 35% |
| Risco máximo por estrutura sem ação | R$ 1.000 | R$ 3.000 | R$ 10.000 |
| Vencimentos varridos | 2 | 2 | 3 |
| Piso da proteção (% do spot) | 95% | 90% | 85% |
| Perda ilimitada (strangle vendido) | fora | fora | dentro, rotulada |

O padrão é o Moderado. O perfil guarda o preset escolhido e os valores editados **(autor,
02/11)**; o arquivo do perfil continua lendo os perfis sem o campo novo.

O risco máximo não se aplica às estruturas com ação (venda coberta, put protetora, collar): o
risco delas é a própria posição de ações.

### 3.3 Famílias e critérios

| Família | Quando e o quê | Critério | Números de apoio |
|---|---|---|---|
| Renda | o ranking da Sprint 5 (`RankIncomeOpportunitiesService`) com o preset: venda coberta, put coberta, trava de alta com put, trava de baixa com call | coberta e put coberta: anualizado líquido; travas: retorno sobre risco | probabilidade, prêmio, delta, dias úteis |
| Volatilidade, venda de vol | regime alta (e neutra, rotulada "sem sinal claro"): iron condor vendido, strangle vendido (só no Arrojado), borboleta comprada | ganho máximo líquido / perda máxima líquida | breakevens em desvios-padrão, probabilidade de lucro, IV rank, IV x HV |
| Volatilidade, compra de vol | regime baixa (e neutra, rotulada): straddle comprado, strangle comprado | movimento necessário até o breakeven mais perto, em desvios-padrão (menor é melhor) | custo em % do ativo, probabilidade de lucro, IV rank, IV x HV |
| Direcionais sem visão | calls e puts com delta (módulo) de 0,30 a 0,60, IV da série abaixo da HV 21 e IV rank <= 30% | desconto da vol: `(HV 21 - IV da série) / HV 21` | IV da série, HV, IV rank, prêmio, delta |
| Direcionais com visão | o usuário informa ativo, alta ou baixa, preço-alvo e vencimento: compra de call ou put e travas de débito (comprada entre o spot e o alvo, vendida no alvo ou depois, de 1 a 3 strikes de largura) | resultado líquido no alvo / risco líquido (débito + custos) | probabilidade de chegar ao alvo (lognormal pela IV), breakeven, débito |
| Proteção | para cada ativo da lista: as ações da carteira (as compradas) ou 100 hipotéticas, rotuladas; put protetora e collar com piso >= o piso do preset | custo mensal equivalente: `custo líquido / valor da posição x 21 / dias úteis` | piso e teto em R$ e em % do spot, custo em % da posição |

- O porquê de cada item cita o critério e os números, por exemplo (números ilustrativos): "IV rank 72% e IV 31% acima da
  HV 24%: o iron condor recebe R$ 13 para arriscar R$ 37 (ganho/risco 0,35), com 62% de
  probabilidade de lucro".
- **Breakeven em desvios-padrão:** `ln(BE / spot) / (σ x sqrt(τ))`, com σ a IV 30 do ativo e τ
  os dias úteis até o vencimento / 252.
- Put americana: sem avaliação de hoje (ADR-0002); no book só usa o resultado no vencimento,
  que vale para qualquer estilo.

### 3.4 Fluxo

- `GET /api/book`: o book do perfil aberto, com o preset dele, o pregão e a fonte "fim de dia
  (B3)", o contexto de vol de cada ativo (IV 30, HV 21, rank, percentil, regime), as famílias, as
  referências e as exclusões.
- `POST /api/book/direcional`: os itens das Direcionais com visão.
- `PUT /api/perfil/book`: salva o preset e os valores editados.
- "Abrir no montador" leva o pedido do item ao montador, que o analisa com a cadeia do momento.
- A cadeia é sempre a do fim de dia (`EndOfDayMarket`), mesmo com o Tryd aberto. Sem COTAHIST, o
  book diz por quê e não mostra nada.

## 4. Análise de mercado

- Aba **Análise** no Mercado, para o ativo escolhido:
  - gráfico do fechamento no ano;
  - IV 30 contra HV 21 no ano, com os pregões extrapolados marcados;
  - cartões de IV 30 de hoje, HV 21, IV rank, percentil e regime;
  - **smile** por vencimento (IV de cada série contra o strike) e **estrutura a termo** (IV no
    dinheiro de cada vencimento contra os dias úteis), pela cadeia do momento, com a fonte.
- `GET /api/mercado/analise/{ativo}`.
- A IV 30 de hoje sai da cadeia do momento (ao vivo, se houver); o rank e o percentil a comparam
  com o histórico, que é só de fim de dia.

## 5. Riscos (anti-objetivos desta semana)

- **Ranking que premia iliquidez:** só EXECUTAVEL no book, filtros de liquidez em todas as pernas.
- **Dado parado como ao vivo:** o book diz o pregão; o montador reprecifica ao abrir.
- **Unidade trocada na vol:** variância total em τ de dias úteis / 252; taxa do CDI convertida para
  contínua pelo VO, nunca à mão.
- **IV rank com histórico curto ou esburacado:** abaixo de 60 pregões não há rank; pregão sem smile
  fica vazio, sem interpolar.
- **Perda ilimitada escondida:** o strangle vendido só entra no Arrojado, com o rótulo.
- **Perfil antigo quebrado:** o campo novo é opcional na leitura.

## 6. Critérios de pronto da semana 3

1. Histórico de IV de PETR4 e VALE3 com os arquivos reais (anual de 2026 e diário de 28/10):
   IV 30, HV 21, rank e percentil conferidos contra um cálculo à mão de pelo menos três pregões.
2. Book com as quatro famílias para a lista do perfil, cada item com o porquê e "abrir no
   montador"; os presets mudam o book e ficam salvos no perfil.
3. Direcionais com visão para um alvo informado.
4. Aba Análise com os gráficos e os números do dia.
5. Gates verdes (pytest com cobertura, mypy strict, ruff, import-linter, `tsc` e Vitest) e o teste
   ponta a ponta com os arquivos reais da B3.

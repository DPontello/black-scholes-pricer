# ADR-0006 — COTAHIST como fonte da fase 1; intraday via Necton depois

- **Status:** Aceita — premissas verificadas no spike de 2026-10-26 (strike
  ajustado no `PREEXE` e MT5 na Necton seguem em aberto); obtenção manual
  dos arquivos e estilo obrigatório decididos pela mesa na mesma data.
  **Decisão 3 emendada pela [ADR-0008](0008-intraday-tryd-rtd.md)** (intraday
  via RTD do Tryd, aceita em 2026-10-28)
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

Fontes avaliadas para a cadeia de opções:

| Fonte | Cobertura | Custo | Observações |
|---|---|---|---|
| COTAHIST (B3) | Todas as opções, fim de dia | Gratuito | Testado e funcionando; bid/ask frequentemente zerados |
| brapi | Opções só no plano Pro; sem token, só PETR4 | Pago | bid/ask frequentemente zerados |
| Necton (corretora do usuário) | Intraday | — | Sem API pública; caminhos possíveis: RTD do Profit, ProfitDLL (Nelogica) ou MetaTrader 5 |

## Decisão

1. **Fase 1 (Sprint 5): `CotahistOptionChainAdapter`**, só com a stdlib:
   - parser do layout de largura fixa: mercado (call/put), strike, data de
     vencimento, melhor oferta de compra e de venda, último preço, número
     de negócios, volume e fator de cotação;
   - preços divididos pelo fator de cotação;
   - zero de "sem oferta" traduzido para `None` (ADR-0003);
   - cache local por pregão com `sqlite3` da stdlib (permitido na camada de
     adapters);
   - vol realizada do subjacente calculada do histórico do próprio arquivo.
2. **brapi:** descartada para opções.
3. **Intraday via Necton:** fora da Sprint 5. Ordem de avaliação:
   **MT5** (biblioteca Python oficial, Windows) → **ProfitDLL** (exige
   licença da Nelogica) → **RTD** (depende de Excel e Profit abertos; mais
   frágil). Qualquer uma implementa o mesmo `OptionChainPort` e passa pela
   mesma suíte de contrato.

## Premissas a verificar (gate do spike da Sprint 5)

- Layout vigente do COTAHIST (posições e semântica dos campos usados).
- **Fonte do estilo de exercício** por série: o COTAHIST não parece trazê-lo
  de forma confiável; candidata: cadastro de instrumentos da B3.
- Se o strike publicado no pregão já reflete ajustes por proventos.
- Para a fase intraday: se a Necton oferece MT5 com cotação de opções.

## Verificação (spike 2026-10-26) e decisões da mesa

### Obtenção dos arquivos (decidido pela mesa em 2026-10-26)

- A página oficial do COTAHIST destina os dados só à consulta informativa e
  **veda expressamente a coleta automatizada**, inclusive por ferramentas de
  inteligência artificial; o formulário de download exige **CAPTCHA**. A
  mesma vedação aparece na página "Pesquisa por pregão", de onde vem o
  cadastro de instrumentos. Página Cotações Históricas da B3, consultada em
  26/10/2026:
  <https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/>
- **Decisão: download manual.** O usuário baixa no site da B3 o ZIP do
  pregão e o CSV do cadastro de instrumentos; o adapter **só lê arquivos
  locais**. Nenhum download automático e nenhum contorno de CAPTCHA.
  Como a vol realizada do subjacente precisa de vários pregões, o usuário
  baixa também o arquivo **anual ou mensal** (ou os diários da janela) do
  COTAHIST; com histórico insuficiente, o subjacente fica fora do painel
  do dia com motivo explícito, nunca com vol inventada.

### Estilo de exercício (decidido pela mesa em 2026-10-26)

- O COTAHIST **não tem campo de estilo** (layout abaixo). A fonte oficial é
  o Cadastro de Instrumentos (Listados) da B3 — `InstrumentsConsolidatedFile`,
  em CSV —, coluna 37 `OptnStyle`. Glossário de 02/02/2024, consultado em
  26/10/2026:
  <https://b3.com.br/data/files/52/74/1E/14/4BA6D8103152D4C8AC094EA8/Glossario%20InstrumentsConsolidatedFile%202024.pdf>
  O glossário não lista os valores possíveis de `OptnStyle` (provavelmente
  americano/europeu em forma abreviada): conferir no primeiro arquivo real.
- O ticker **não codifica estilo** (estrutura do código de negociação no
  OC 025/2017-DO, vigência 04/12/2017). O "E" no fim do código identifica o
  instrumento de **exercício**, não "europeia".
- **Decisão: estilo obrigatório.** O adapter lê o COTAHIST **e** o CSV do
  cadastro; série sem estilo no cadastro fica **fora do painel com motivo
  explícito**. O estilo nunca é suposto pelo tipo da opção nem pelo ticker.

### Layout do COTAHIST — fatos que o parser usa

Fonte: "Layout do Arquivo — Cotações Históricas — COTAHIST.AAAA.TXT",
revisão 02 de 05/10/2020 (a capa ainda diz "13/04/2017, Revisão 01"; vale o
histórico interno do documento), consultado em 26/10/2026:
<https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf>

- Registros de **245 bytes**: **header `00`**, registros de cotação `01` e
  **trailer `99`**. O trailer traz o total de registros (incluindo header e
  trailer) nas posições 32–42. O layout descreve só o arquivo anual; o nome
  gravado no header do arquivo diário não está documentado e não deve ser
  validado de forma rígida.
- **Encoding cp1252** ("Windows (ANSI)", segundo a página Cotações
  Históricas).
- Campos principais do registro `01` (posições 1-based, inclusivas):

  | Campo | Posições | Tipo | Conteúdo |
  |---|---|---|---|
  | `TIPREG` | 1–2 | N(02) | fixo `01` |
  | `DATPRE` | 3–10 | N(08) | data do pregão, AAAAMMDD |
  | `CODNEG` | 13–24 | X(12) | código de negociação (ticker) |
  | `TPMERC` | 25–27 | N(03) | **010** à vista, **070** opção de compra, **080** opção de venda |
  | `PREULT` | 109–121 | (11)V99 | último negócio |
  | `PREOFC` | 122–134 | (11)V99 | melhor oferta de compra |
  | `PREOFV` | 135–147 | (11)V99 | melhor oferta de venda |
  | `TOTNEG` | 148–152 | N(05) | número de negócios |
  | `VOLTOT` | 171–188 | (16)V99 | volume financeiro |
  | `PREEXE` | 189–201 | (11)V99 | strike |
  | `INDOPC` | 202 | N(01) | correção monetária do strike (1 US$, 2 TJLP, 8 IGP-M, 9 URV) — **sem relação com proventos** |
  | `DATVEN` | 203–210 | N(08) | vencimento, AAAAMMDD |
  | `FATCOT` | 211–217 | N(07) | fator de cotação (1 = unitária, 1000 = lote de mil) |
  | `CODISI` | 231–242 | X(12) | código ISIN |

- `(11)V99` são 13 dígitos com **2 decimais implícitas**; `VOLTOT`,
  `(16)V99`, também tem 2 decimais implícitas.
- Os preços vêm **por unidade de `FATCOT`**, na moeda da época e sem ajuste
  retroativo por inflação ou proventos; daí a divisão pelo fator da
  decisão 1.
- **`PREOFC`/`PREOFV` = 0 não está documentado** no layout. Tratar o zero
  como "sem oferta" (`None`) é **interpretação** adotada pela ADR-0003, não
  regra publicada pela B3.
- **Strike já ajustado por proventos no `PREEXE`: provável, não
  confirmado.** O strike muda na data ex sem trocar o ticker (ADR-0002),
  mas nenhum documento diz que o `PREEXE` do COTAHIST já sai ajustado.
  Teste proposto: comparar o `PREEXE` de um mesmo `CODNEG` antes e depois
  de uma data ex conhecida.

### Fase intraday e lote padrão

- **MT5 na Necton: não encontrado.** Nenhuma fonte (Necton, BTG ou
  MetaQuotes) confirma que a Necton oferece MT5 — **pendente com o
  usuário**. A biblioteca Python oficial existe (versão 5.0.6231, de
  27/09/2026, só Windows x64) e exige o terminal MT5 instalado e logado na
  conta da corretora: <https://pypi.org/project/MetaTrader5/> (consultado
  em 26/10/2026). A ordem de avaliação da decisão 3 não muda.
- **Lote padrão:**
  - opções sobre ações: **100** — provável (negociação em múltiplos de 100
    e `FATCOT = 1`), sem documento oficial vigente localizado;
  - opções sobre ETF: **1** desde 28/09/2020 — confirmado; afeta BOVA11.
    Notícia da B3 de 17/09/2020:
    <https://www.b3.com.br/pt_br/noticias/alteracao-no-lote-padrao-de-bdrs-e-etfs.htm>
  - a fonte por série é o campo `AllcnRndLot` do cadastro de instrumentos.

## Consequências

- Dados de fim de dia: bid/ask do COTAHIST refletem o fechamento; o último
  negócio de uma série pode ser bem anterior ao fechamento da ação, o que
  distorce a volatilidade implícita — por isso a ADR-0004 rotula `last` como
  `INDICATIVO`.
- Uso pessoal dos dados; nenhuma redistribuição.

# ADR-0004 — Preço executável por lado e regra de livro vazio

- **Status:** Aceita
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

Estratégias de renda **vendem** opções. O prêmio que de fato se recebe é o
melhor bid; numa trava de crédito, a perna de proteção é **comprada** e
paga o melhor ask. Usar o mid ou o último negócio superestima o rendimento,
e o ranking tende a premiar justamente as séries menos líquidas — onde o
spread é maior e o último negócio é mais velho.

Com frequência um ou os dois lados do book vêm vazios (ADR-0003).

## Decisão

Preço da perna por lado e qualidade do preço:

| Situação da série | Perna vendida | Perna comprada | Qualidade | Entra no ranking padrão? |
|---|---|---|---|---|
| bid e ask presentes | bid | ask | `EXECUTAVEL` | Sim |
| só bid | bid | sem preço | `EXECUTAVEL` só para venda | Só se a perna for vendida |
| só ask | sem preço | ask | `EXECUTAVEL` só para compra | Só se a perna for comprada |
| nenhum lado, com negócio no pregão (`trades > 0`) e `last` presente | `last` | `last` | `INDICATIVO` | Não |
| nenhum lado **e** nenhum negócio no pregão (`trades == 0`) | teórico (BS com volatilidade implícita interpolada do smile da mesma série de vencimento) | idem | `TEORICO` | Nunca |

Regras complementares:

- **Book de um lado só nunca cai para o `last`:** a perna do lado ausente
  fica sem preço, mesmo com negócio no pregão. `INDICATIVO` só existe com
  o book vazio.
- **`TEORICO` exige as duas condições:** book vazio **e** nenhum negócio no
  pregão (`trades == 0`). Book vazio com `trades > 0` e sem `last` é dado
  incoerente e fica sem preço (ADR-0003, notas de implementação).
- A qualidade de uma estrutura é a **pior** qualidade entre suas pernas.
- O **mid** serve só para exibir o smile, nunca para calcular rendimento.
- Filtros de liquidez — número mínimo de negócios e spread percentual
  máximo — são **parâmetros** do comando, não constantes.
- Candidatos `INDICATIVO` podem ser exibidos fora do ranking, sempre
  rotulados; `TEORICO` só aparece como referência.
- **Ativo-objeto com livro vazio:** o adapter não inventa bid/ask; se não
  houver preço utilizável de fechamento, o subjacente fica fora do painel
  do dia com motivo explícito.
- **Ativo-objeto com fechamento mas sem ofertas** (decidido pela mesa em
  2026-10-26): o spot é o preço de fechamento e o ativo **continua no
  painel**, com a marca "sem ofertas". O snapshot carrega o fechamento como
  referência, a cadeia sinaliza que o book do ativo-objeto não foi
  observado, e nenhuma métrica de renda usa bid/ask do ativo-objeto.

Esclarecido em 2026-10-26 (Sprint 5), sem mudar a decisão: as condições
das linhas `INDICATIVO` e `TEORICO` da tabela e as duas primeiras regras
complementares.

## Filtros de liquidez (fechado pela mesa em 2026-10-26)

- **Sem filtro padrão.** O ranking exige apenas preço `EXECUTAVEL`; mínimo
  de negócios e spread percentual máximo são filtros **opcionais** do
  comando, desligados quando não informados.

## Consequências

- Regra pura no domínio (`executable_premium(quote, side)` + enum de
  qualidade), testável sem adapter.
- O painel mostra a qualidade em cada linha; nenhum número sai sem rótulo.

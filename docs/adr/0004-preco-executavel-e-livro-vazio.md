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
| nenhum lado, com negócio no pregão | `last` | `last` | `INDICATIVO` | Não |
| nenhum lado, sem negócio | teórico (BS com volatilidade implícita interpolada do smile da mesma série de vencimento) | idem | `TEORICO` | Nunca |

Regras complementares:

- A qualidade de uma estrutura é a **pior** qualidade entre suas pernas.
- O **mid** serve só para exibir o smile, nunca para calcular rendimento.
- Filtros de liquidez — número mínimo de negócios e spread percentual
  máximo — são **parâmetros** do comando, não constantes.
- Candidatos `INDICATIVO` podem ser exibidos fora do ranking, sempre
  rotulados; `TEORICO` só aparece como referência.
- **Ativo-objeto com livro vazio:** o adapter não inventa bid/ask; se não
  houver preço utilizável de fechamento, o subjacente fica fora do painel
  do dia com motivo explícito.

## Pendência

- Valores padrão dos filtros de liquidez (mínimo de negócios, spread
  percentual máximo): a mesa define antes do fim da Sprint 5.

## Consequências

- Regra pura no domínio (`executable_premium(quote, side)` + enum de
  qualidade), testável sem adapter.
- O painel mostra a qualidade em cada linha; nenhum número sai sem rótulo.

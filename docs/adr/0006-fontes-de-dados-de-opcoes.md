# ADR-0006 — COTAHIST como fonte da fase 1; intraday via Necton depois

- **Status:** Aceita
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

## Consequências

- Dados de fim de dia: bid/ask do COTAHIST refletem o fechamento; o último
  negócio de uma série pode ser bem anterior ao fechamento da ação, o que
  distorce a volatilidade implícita — por isso a ADR-0004 rotula `last` como
  `INDICATIVO`.
- Uso pessoal dos dados; nenhuma redistribuição.

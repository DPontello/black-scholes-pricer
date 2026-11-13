# Plano de melhorias do Painel de Opções (black-scholes-pricer)

Você vai implementar melhorias no app, uma sprint por vez, na ordem abaixo.
Leia antes: `docs/superpowers/HANDOFF-2026-11-02.md`, `docs/CONVENTIONS.md`,
`docs/adr/0004` e `0005`, e o ledger da semana 4.

## Regras de trabalho (valem acima de tudo)
- Uma branch por tarefa a partir da `development`. Não commite nem dê push:
  ao fim de cada tarefa, mostre o diff e pergunte "commito e sigo?".
- Toda regra de negócio marcada como DECISÃO vira enquete (opção recomendada
  primeiro, com o custo de cada uma) e entra no ledger como `Ruling:`.
  Não assuma nenhuma.
- Teste primeiro: escreva o teste que falha, depois a correção.
- Por tarefa: ruff, mypy, lint-imports e as suítes tocadas. Gate completo
  (pytest inteiro, `npm --prefix frontend run verificar`, build) no fim da sprint.
- Não toque nos dados reais (`%APPDATA%\PainelOpcoes`, `~/.config/painel-opcoes`),
  no registro, no Tryd nem na rede.
- Nada de número novo na tela sem rótulo de origem (executável, indicativo,
  teórico, estimado).

## Sprint 0 — Auditoria do que não foi conferido (só leitura, 1 dia)
Objetivo: fechar os pontos cegos antes de mexer. Entregue um relatório com
"confirmado" (entrada → saída) e "suspeita", sem alterar código.
1. Parsing do COTAHIST e do XML BVBG.028: strike, fator de cotação, estilo,
   vencimento, lote, série ajustada por provento.
2. Valores do Tryd em `adapters/outbound/tryd/translation.py`: "12,34",
   "1.234", "1.234,56", zero, vazio, "-", negativo.
3. `data/b3_holidays.csv` termina em 2027-12-31: o que acontece com um
   vencimento de 2028 (erro, aviso ou "dia útil" em silêncio)?
4. Tela: como "probabilidade de lucro" e "probabilidade de exercício" são
   rotuladas. No cálculo são neutras a risco, com vol única
   (`domain/simulation/probability.py`). Se a tela não disser isso, vira
   tarefa da Sprint 2.
5. Candidatos a remoção — confirme se ainda são usados pelo app web antes de
   propor: `adapters/inbound/html_report.py`, `payoff_svg.py`,
   `outbound/mock_orderbook.py`, `seeded_random.py` (painel estático e mock
   da Sprint 5) e as branches locais `worktree-agent-*`.
6. Rode o gate do frontend e registre o resultado.

## Sprint 1 — Alertas que não calam (prioridade máxima)
Objetivo: nenhum alerta de perda fica em silêncio.

1.1 Stop com perna sem oferta para zerar.
- Hoje: `_marks.py:56-65` devolve preço `None`; `portfolio.py:281` zera o
  total; `rules.py:152` marca "indeterminado" e nada aparece. Provado: stop
  de R$ 500 com total indeterminado → nenhum alerta.
- O comportamento atual é decisão do ledger da semana 4 e tem teste
  (`tests/alerts/test_rules.py:134`, `tests/application/test_alerts.py:127`).
- DECISÃO: (A, recomendada) com cotação mas sem o lado, estimar pelo
  `LegMark.theoretical` e disparar stop rotulado "estimado"; sem teórico,
  alerta "stop sem preço para avaliar". (B) comprada sem bid vale zero.
  (C) só o aviso. Sem cotação nenhuma continua indeterminado nas três.
- Só o stop usa o estimado; o alvo não.
- Testes: `test_stop_estimado_dispara_com_comprada_sem_bid`,
  `test_sem_cotacao_stop_segue_indeterminado`, `test_sem_teorico_vira_aviso`,
  `test_alvo_nao_usa_total_estimado`,
  `test_dispensado_nao_volta_quando_o_bid_some`.

1.2 Risco de exercício fora da janela.
- Hoje: `rules.py:117` sai cedo se faltam mais dias que `expiry_days` (5).
  Provado: put vendida strike 30, ativo a 26, 10 dias úteis → nenhum alerta.
- DECISÃO: vendida dentro do dinheiro avisa em qualquer prazo (recomendada)
  ou só acima de uma distância configurável.
- Teste: `test_vendida_dentro_do_dinheiro_avisa_fora_da_janela`.

1.3 Alertas indeterminados visíveis.
- A aba Alertas mostra "N alertas não puderam ser avaliados" com o motivo
  (sem spot, sem preço, fora do calendário), em vez de sumir.

1.4 Suíte verde no Windows.
- 6 testes falham por barra de caminho: `tests/ponte/test_tryd7.py` (4) e
  `tests/web/test_folder_picker.py` (2). Corrija os testes, não o produto,
  salvo se a Sprint 0 mostrar o contrário.

Aceite da sprint: os 4 itens com teste; pytest sem falha no Windows e no Linux.

## Sprint 2 — Book que não confunde rendimento com risco
Objetivo: o topo do Book deixa de ser "a operação mais arriscada da faixa".

2.1 Critério único e comparável entre prazos.
- Hoje: venda coberta e put coberta ordenam pelo anualizado composto bruto
  (`domain/book/renda.py:86`, `income/metrics.py:141`); a trava ordena pelo
  retorno do período sem anualizar (`renda.py:89`). Provado: R$ 0,20 em 3
  dias úteis vira 74,7% a.a.; R$ 0,80 em 23 dias vira 33,4% a.a.
- DECISÃO: (A, recomendada) agrupar o Book por vencimento e ordenar dentro
  de cada um, sem comparar prazos; (B) rendimento líquido por dia útil;
  (C) anualização simples. Em qualquer uma, usar o líquido de custos.

2.2 Risco ao lado do rendimento, sempre.
- Provado: o retorno sobre o risco da trava sobe de 6,9% (delta 0,08) para
  62,3% (delta 0,43) com valor esperado perto de zero em todas.
- Cada item mostra, na mesma linha: perda máxima em R$, probabilidade de
  exercício e distância do strike em desvios-padrão (`scan.std_devs_to` já
  existe).
- Remover da frase do "porquê" qualquer texto que apresente o maior
  rendimento como vantagem sem citar o risco.

2.3 Sinal de prêmio caro ou barato.
- O contexto de vol já existe (`domain/analytics/volatility.py`: IV 30,
  HV 21, rank, regime). Mostrar no item a razão IV da série ÷ HV 21 e
  marcar "sem sinal claro" quando o regime for neutro.
- Não usar esse sinal como critério de ordenação antes da Sprint 5.

2.4 Rótulo das probabilidades (se a Sprint 0 confirmar a falta).
- Texto fixo: "estimativa pela vol implícita, neutra a risco; não é a
  chance real".

Aceite: nenhum item do Book aparece sem perda máxima; prazos diferentes não
são ordenados juntos sem aviso; testes cobrem a ordem com dois vencimentos.

## Sprint 3 — Números mais fiéis
3.1 Tempo fracionado no intradiário.
- Hoje: `_time.py:50` conta dias úteis inteiros. Provado: com 1,9 pregão
  restante a vol de 30% aparece como 42,4%; com 5,9, como 33,0%.
- DECISÃO: somar a fração restante do pregão de hoje (10h–17h) só na fonte
  ao vivo; fim de dia continua inteiro, para o histórico de IV não mudar.
- Teste: `test_iv_ao_vivo_na_vespera_nao_infla`, com tolerância de 1 ponto
  de vol contra a vol usada para gerar o preço.

3.2 IRRF no IR mensal.
- Hoje não existe (`domain/portfolio/income_tax.py`). Acrescentar o retido
  (0,005% nas operações comuns, 1% do ganho em day trade) como dedução do
  "a pagar", com campo para informar o valor real da nota.
- DECISÃO: estimar, ou só aceitar o valor digitado.
- A tela diz o que fica fora: ações, exercício e prejuízo de ações.

3.3 CDI do perfil.
- É campo manual com padrão 0,15. Mostrar a data da última alteração e
  avisar depois de 60 dias sem revisão.

## Sprint 4 — Diário e tamanho de posição
4.1 Estatísticas por estratégia, a partir do histórico da Carteira
   (`PortfolioService.history`): número de operações, taxa de acerto, ganho
   médio, perda média, expectativa por operação e maior perda. Agrupar por
   `modelo` da operação. Abaixo de 20 operações, mostrar "amostra pequena".
4.2 Perda máxima por operação: campo no perfil (R$ ou % do capital
   informado). Ao registrar ou montar, avisar quando a perda máxima da
   estrutura passar do limite; perda ilimitada sempre avisa.
4.3 Estresse da carteira inteira: somar o `scenario_matrix` das operações
   abertas por ativo (queda de 10% e 20%, vol +10 pontos) numa tabela.

## Sprint 5 — Validar antes de confiar
5.1 Backtest das operações de renda com o COTAHIST anual: entrar pelo bid
   do fechamento, levar ao vencimento, com os custos da tabela e os filtros
   de liquidez do preset.
5.2 Medir por faixa de delta, prazo e razão IV÷HV: taxa de acerto,
   resultado médio, pior resultado. Só então decidir se IV÷HV vira critério
   do Book.
5.3 Armadilhas a tratar e documentar: um ano de dados é pouco; séries sem
   negócio somem da amostra; bid de fechamento não é preço garantido; nada
   de escolher parâmetro olhando o resultado do mesmo período.

## Fora do escopo
Put americana exata, calendar spreads, envio de ordens e qualquer
recomendação automática de operação.

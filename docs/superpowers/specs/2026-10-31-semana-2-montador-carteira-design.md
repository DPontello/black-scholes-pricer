# App de opções — semana 2: Montador e Carteira — desenho (2026-10-31)

> Detalha a semana 2 do desenho geral
> ([`2026-10-28-app-opcoes-design.md`](2026-10-28-app-opcoes-design.md), §2 itens 2 e 4, §6.5 e §8).
> As regras marcadas **(autor, 31/10)** foram respondidas pelo autor em enquete; o resto é
> decisão de quem escreveu, revisável.

## 1. Escopo

Entrega da semana (04/11 a 10/11), em duas metades usáveis:

1. **Montador:** montar qualquer estrutura das quatro famílias, por modelo pronto ou perna a
   perna a partir da cadeia, ver o resultado completo e daí salvar como simulação ou registrar
   como executada.
2. **Carteira:** registrar operações, acompanhar o P&L ao vivo pelo preço de zerar, encerrar,
   exercer e ser exercido, e lançar posições de ações à mão.

Fora da semana 2 (vêm depois, como no desenho geral): IR mensal com compensação (semana 4),
proventos e ajuste de strike (semana 4), alertas (semana 4), book de recomendações (semana 3).

### Decisões do autor (31/10)

- A carteira da semana 2 tem: registrar operação, encerrar posição, exercício e atribuição, e
  ações à mão.
- Na venda coberta, na put protetora e no collar, a ação **vem da carteira ou é comprada
  junto**, à escolha na hora.
- Quantidade **como na Necton**: em número de opções ou de ações, conferida contra o lote do
  Cadastro.
- No vencimento, a perna **fora do dinheiro vira pó sozinha**; no dinheiro ou dentro, o app pede
  para registrar o exercício ou a atribuição.
- A carteira mostra **uma linha por operação, com o total por ativo** embaixo.
- Abordagem A: estender o domínio que já existe (perna de ação no `Strategy`, motor de
  simulação generalizado, carteira como módulo puro novo).

## 2. Montador

### 2.1 Domínio

- **Perna de ação** (`StockLeg`: ticker, lado, quantidade, preço por ação opcional) no agregado
  `Strategy`, que passa a ter `legs` (opções) e `stock_legs` (no máximo uma). Invariantes: o
  ticker da ação é o ativo-objeto das opções; a estrutura tem ao menos uma perna de qualquer
  tipo; as opções seguem com o mesmo vencimento (decisão nº 6). Direção só no `Side`, como nas
  opções.
- **Payoff no vencimento** com termo linear da ação: `ações x (S - preço)` com o sinal do lado.
  Breakevens e extremos continuam exatos (curva linear por partes), e ganho ou perda
  **ilimitados** saem como tal, nunca como o valor da ponta do eixo.
- **Modelos prontos** (catálogo puro, por família): forma das pernas (tipo, lado, proporção) e
  uma sugestão de strikes a partir do spot (no dinheiro e os próximos strikes da cadeia). O
  usuário troca qualquer strike clicando na cadeia.

  | Família | Modelos |
  |---|---|
  | Renda | venda coberta, put coberta, trava de alta com put, trava de baixa com call |
  | Direcionais | compra de call, compra de put, trava de alta com call, trava de baixa com put |
  | Volatilidade | straddle, strangle, iron condor, borboleta (comprados e vendidos) |
  | Proteção | put protetora, collar |

- **Avaliação "hoje"** (motor de simulação generalizado): vol **por perna**, a IV da própria
  série pelo meio do book ou, sem ela, a do smile no strike (o que `series_risk` já faz). Call
  americana entra como europeia, **rotulada** (ADR-0002). Put americana não tem avaliação hoje:
  a curva de hoje sai indisponível com o motivo, e o vencimento continua.
- **Gregas** agregadas por soma ponderada; a ação tem delta = quantidade assinada e as demais
  zero. Unidades canônicas (CONVENTIONS §1); por dia e por ponto de vol só na tela.
- **Grade de cenários** spot × vol: spot de -20% a +20% e choque de vol somado à vol de cada
  perna (-10 a +10 pontos), no vencimento escolhido e hoje.
- **Probabilidade risco-neutra de lucro no vencimento:** lognormal com a vol do smile no dinheiro
  do vencimento, sobre as faixas de spot em que o resultado bruto é positivo. Rotulada como
  risco-neutra.
- **Custos e IR** pelo modelo da ADR-0005, generalizado para quantidades por perna (a borboleta
  tem 1-2-1): emolumentos sobre o financeiro de cada perna, uma ordem por perna, exercício pela
  tabela do à vista sobre `strike x quantidade` e IR estimado por operação, limitado ao
  resultado do prêmio. Ação vinda da carteira não paga a compra.

### 2.2 Regras de preço e quantidade

- Preço de cada perna pelo lado executável (ADR-0004): vende no bid e compra no ask, com a
  qualidade (EXECUTAVEL, INDICATIVO ou TEORICO) visível. O usuário pode editar o preço; o
  editado vira "digitado" e sai do rótulo de qualidade.
- Quantidade em número de opções ou de ações. Fora do lote do Cadastro (`AllcnRndLot`: 100 na
  maioria; 1 nas de BOVA11) o app **avisa e não bloqueia**: registrar o que foi executado na
  Necton nunca pode ser impedido.
- Perna de ação "da carteira": usa o preço médio da posição de ações do perfil. Numa estrutura
  com call vendida (venda coberta, collar), exige ações **livres**: a posição menos as que já
  cobrem outra call vendida aberta. "Comprada junto": o preço vem do ask do ativo e é editável.

### 2.3 Fluxo e tela

- Tela **Montador**: cadeia do ativo à esquerda (a mesma do Mercado, com clique para pôr perna);
  à direita, os modelos por família, a tabela de pernas (lado, quantidade, preço editável) e o
  resultado.
- O resultado tem um **resumo em português** ("você recebe R$ X agora; no pior caso perde R$ Y;
  ganha no máximo R$ Z; empata se PETR4 ficar entre A e B no vencimento"), os números, o gráfico
  de payoff (vencimento e hoje, ECharts), as gregas e a grade.
- Recalcula quando as pernas mudam e a cada atualização da cadeia, no máximo uma vez por
  segundo.
- A cadeia do Mercado ganha "Montar com este ativo".
- **Salvar simulação** grava na pasta do perfil (`simulacoes/`) e reabre depois. **Registrar como
  executada** abre o formulário da carteira (§3.3) já preenchido com as pernas e os preços do
  montador, para trocar pelos preços reais.

## 3. Carteira

### 3.1 Modelo

- **Operação:** id, ativo, nome da estrutura e família, data de criação, pernas e uma lista de
  **eventos** em ordem. As posições, os preços médios e os resultados são **recalculados a partir
  dos eventos**; nada é guardado já somado.
- **Perna:** opção (ticker e termos: tipo, strike, vencimento e estilo) ou ação (ticker e
  origem: `compra` ou `carteira`).
- **Eventos:**
  - **execução de abertura:** perna, data, quantidade, preço e custos reais opcionais. Várias
    por perna dão o preço médio;
  - **execução de encerramento:** perna, data, quantidade e preço; parcial ou total;
  - **exercício** (perna comprada) e **atribuição** (perna vendida): perna, data e quantidade;
    geram o movimento da ação;
  - **pó:** perna e data; zera a perna sem fluxo de caixa.
- **Ações à mão:** uma operação de uma perna de ação com uma execução de abertura (quantidade e
  preço médio informados).

### 3.2 Regras

- **P&L não realizado** pelo preço de zerar: perna comprada sai no bid, vendida recompra no ask
  (ação idem), com a fonte (`ao_vivo`, `atrasado`, `fim_de_dia`) e a qualidade do preço. Sem
  lado de zeragem, o valor teórico aparece ao lado, rotulado, e não entra no total executável.
- **P&L realizado** por perna: (preço de saída - preço médio de entrada) x quantidade, com o
  sinal do lado, menos os custos (os reais quando informados, senão a estimativa da ADR-0005).
- **Exercício e atribuição** seguem a regra da Receita para o prêmio, a conferir no texto da
  IN RFB 1.585/2015 antes de implementar:
  - titular de call exercida: a ação entra com custo = strike + prêmio pago;
  - lançador de call atribuída: a ação sai com venda = strike + prêmio recebido;
  - titular de put exercida: a ação sai com venda = strike - prêmio pago;
  - lançador de put atribuída: a ação entra com custo = strike - prêmio recebido.

  A ação que entra vira perna de ação da mesma operação. A ação que sai é baixada da perna de
  ação da operação ou, se ela veio "da carteira", da posição de ações do perfil, pelo preço
  médio dela.
- **Vencimento (autor, 31/10):** depois do pregão do vencimento, cada perna de opção ainda aberta
  é comparada com o **fechamento do ativo nesse pregão** (COTAHIST daquele dia ou o último `ULT`
  do Tryd depois do fechamento):
  - fora do dinheiro (call com fechamento < strike, put com fechamento > strike): vira **pó**
    sozinha, com evento gravado;
  - no dinheiro ou dentro: fica "vencida, registre o exercício ou a atribuição";
  - sem o fechamento do dia: fica "vencida, aguardando o fechamento".
- **Consolidado por ativo:** por ticker, a quantidade líquida, o preço médio ponderado e o P&L,
  somando as operações abertas. A posição de ações do perfil é a soma das pernas de ação
  abertas.
- **Encerrada:** operação sem nenhuma perna aberta. Vai para o histórico com o resultado
  realizado total.

### 3.3 Persistência

- Pasta do perfil: `operacoes/<data>_<ativo>_<id8>.json`, um arquivo por operação, com
  `"versao": 1`, escrita atômica (temporário + renomear) e regravada a cada evento.
  Simulações em `simulacoes/`.
- Arquivo ilegível ou de versão desconhecida é listado com o caminho e o motivo, nunca apagado
  nem sobrescrito.
- Nada de carteira dentro do repositório (que é público); testes com pastas temporárias.

### 3.4 Ao vivo

- As pernas de opção das operações abertas entram na assinatura do Tryd, com os ativos delas.
  Prioridade no limite de tópicos: a lista de ativos, a carteira e só então a cadeia aberta.
- Port novo de cotação de séries por ticker (`get_option_quotes`), no ao vivo e no fim de dia,
  com o mesmo recuo do `FallbackMarket`.
- O WebSocket `/api/ao-vivo` ganha a mensagem `carteira` (só quando muda, como as outras).

### 3.5 Tela

- **Carteira:** as operações abertas, uma linha por operação, que se abre nas pernas, e o total
  por ativo embaixo. Ações por operação: encerrar (parcial ou total), registrar exercício ou
  atribuição, ver eventos.
- "Adicionar ações" (à mão) e "Registrar operação" (formulário da §3.1, também aberto pelo
  montador).
- Aba **Histórico** com as operações encerradas e o resultado realizado.
- Avisos das pernas vencidas aguardando ação.

## 4. Riscos (anti-objetivos desta semana)

- **Sinal da perna de ação invertido** ou prêmio somado ao custo com o sinal errado no
  exercício: testes de propriedade (short == -long com ação) e um teste por caso da Receita.
- **Ação contada duas vezes:** a perna "da carteira" não cria ação nova, só compromete a que
  existe.
- **Pó indevido:** sem o fechamento do dia, nada vira pó.
- **Carteira corrompida pela nuvem:** um arquivo por operação, escrita atômica, e nunca
  sobrescrever arquivo ilegível.
- **Limite de tópicos:** a carteira tem prioridade sobre a cadeia. O que ficar fora da
  assinatura aparece "sem cotação ao vivo", nunca com o preço velho.

## 5. Critérios de pronto da semana 2

1. Montar no app as quatro famílias por modelo pronto e perna a perna, com payoff, gregas,
   breakevens, máximos, custos, IR, grade e probabilidade conferidos contra testes do domínio.
2. Salvar e reabrir uma simulação.
3. Registrar uma venda coberta com ação comprada junto e outra com ação da carteira; ver o P&L ao
   vivo pelo preço de zerar, encerrar parte e registrar uma atribuição.
4. Uma perna fora do dinheiro vira pó sozinha depois do vencimento, com o fechamento importado.
5. As carteiras do autor e da mãe ficam em pastas diferentes e não se misturam.
6. Gates verdes (pytest com cobertura, mypy strict, ruff, import-linter, `tsc` e Vitest) e o
   teste ponta a ponta com os arquivos reais da B3.

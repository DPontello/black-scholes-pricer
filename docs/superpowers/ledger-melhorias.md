# Ledger — plano de melhorias

Plano: [`plans/2026-11-13-plano-de-melhorias.md`](plans/2026-11-13-plano-de-melhorias.md), colado
pelo autor em 13/11. Uma branch por tarefa, a partir da `development`; o autor commita. Toda
regra marcada como DECISÃO no plano é respondida pelo autor numa enquete e entra aqui como
`Ruling:` com "(autor)"; as outras linhas `Ruling:` são decisões minhas, para o autor conferir.

## 2026-11-13: Sprint 0 — auditoria (só leitura)

Feita sem alterar código, a partir da `development` em `c5ca7ff`. As sondas usaram registros e
XML sintéticos montados pelos helpers dos testes (`tests/adapters/cotahist/_layout.py` e
`_bvbg.py`), fora do repositório.

### 1. COTAHIST e cadastro BVBG.028

Confirmado (entrada → saída):

- Fator de cotação: o strike e os preços são divididos pelo FATCOT. Registro com FATCOT 1000 e
  strike gravado 30000,00 → strike 30,0 e último 0,85.
- Strike corrigido por índice: INDOPC=1 → série rejeitada com "strike corrigido por índice
  (INDOPC=1)".
- Vencimento: vem do DATVEN (2026-12-18); o à vista fica com 9999-12-31.
- Estilo: só vem do cadastro. `AMER` → americana, `EURO` → europeia; vazio → série fora, com
  "sem estilo de exercício no cadastro" (nunca europeia por omissão).
- Lote: vem do `AllcnRndLot` do XML (100 nas opções); o Montador recusa quantidade fora do lote
  (`strategy_builder.py:161`).
- Strike da cadeia: vem do PREEXE do próprio pregão (`cotahist/adapter.py:251`), não do cadastro.
- Série ajustada por provento: strike 29,47 com ESPECI `"PN EJ N2"` passa como qualquer outra.
  Não existe detecção de ajuste.

Confirmado, problema novo (N1): a Carteira grava o strike do dia do registro
(`storage/operations.py:112`) e o usa no vencimento (`portfolio.py:235-238`). Call registrada com
K=30,00, strike ajustado pela B3 para 29,47 e fechamento de 29,80 no vencimento → `PO` (a operação
é encerrada como pó); com o strike ajustado → `REGISTRAR_EXERCICIO`. O mesmo strike guardado
alimenta o risco de exercício dos alertas e o teórico.

Suspeita: o COTAHIST não ajusta os fechamentos por provento (já documentado). Uma data-com dentro
dos 21 pregões distorce a HV 21 e, por ela, o sinal IV÷HV da tarefa 2.3.

### 2. Valores do Tryd (`adapters/outbound/tryd/translation.py`)

Confirmado:

| Valor | Resultado |
|---|---|
| `"12,34"`, `"12.34"` | 12,34 |
| `" 7,5 "` | 7,5 |
| `"1.234,56"` | 1234,56 |
| `"0"`, `0`, `0.0` | preço ausente |
| `""` | ausente |
| `"1.234"` | 1,234 (ponto lido como decimal) |
| `"-"`, `"-1,5"`, `-2.0`, `"1,234.56"` | a série inteira é rejeitada ("valor ilegível") |

- `NEG "1.234"`: a série some, com "valor ilegível no campo NEG".
- `VOL "1.234"`: vira 1,234 em vez de 1234, mil vezes menor e sem aviso.
- `OCP "-"` (sem oferta): a série some, em vez de ficar sem compra.

Suspeita (N2): se o Tryd 7 mandar `"-"` para book vazio, ou `NEG` com ponto de milhar, séries
somem da cadeia no PC da mãe. O `espiar` do HANDOFF §14 tira a dúvida.

### 3. Calendário depois de 2027

Confirmado: os dias úteis até 21/01/2028 levantam "fora da cobertura do calendário"; nenhum
vencimento de 2028 vira dia útil em silêncio. Mas ele some sem aviso (N3):

- Cadeia (`market_view.py:136-140`), Book (`book.py:172-175`), análise e histórico de IV: o
  vencimento é pulado.
- Alertas (`alerts.py:104-107`): indeterminados (tarefa 1.3).
- Teórico da Carteira (`_marks.py:97-102`): `None`.

Suspeita:

- Montador (`strategy_builder.py:142`): não trata o erro. A tela não chega lá, mas uma rolagem
  para 2028 cairia nele.
- Tryd ao vivo (`feed.py:406`, `_atm_implied_vol`): também não trata. Só roda quando falta
  histórico para a vol realizada; aí uma série de 2028 com compra e venda derrubaria a cadeia.

### 4. Rótulo das probabilidades

Confirmado: a tela não diz que a probabilidade é neutra a risco → tarefa 2.4 da Sprint 2.

- Montador: "Chance de lucro"; "Probabilidade risco-neutra no vencimento, pela vol do smile no
  dinheiro" só passando o mouse (`ResumoEstrutura.tsx:72`).
- Book: "chance de lucro" com um "?" para o glossário, sem texto na tela
  (`CartaoDestaque.tsx:94`, `TabelaFamilia.tsx:45`).
- Glossário: "estimativa do modelo, não uma previsão"; não diz neutra a risco nem "não é a chance
  real".
- Probabilidade de exercício: só no glossário; nenhuma tela mostra o número.
- Cálculo: vol única, a do smile no dinheiro (`strategy_builder.py:400`).

### 5. Candidatos a remoção

Confirmado: o app web não importa nenhum dos quatro. Mesmo assim a remoção é uma DECISÃO:

- O executável do Windows entra por `packaging/windows/painel.py` → `options_engine.__main__`, que
  importa no topo `composition` (que traz `mock_orderbook` e `seeded_random`) e `html_report` (que
  traz `payoff_svg`).
- Eles servem ao comando `painel` (o painel HTML estático da ADR-0007) e ao smoke de
  `python -m options_engine` sem argumento.
- Remover os quatro é remover esses dois comandos e os testes deles, inclusive
  `tests/contract/test_mock_orderbook.py`.

Branches `worktree-agent-*`: não existem neste PC (nem locais nem remotas).

### 6. Gate do frontend

`npm --prefix frontend run verificar`: 1ª rodada 313/314 (falhou `Aprender.test.tsx`, "/aprender
abre em Comece aqui"); 2ª rodada 314/314; o teste sozinho, 5 de 5 verdes. É a falha intermitente
conhecida, que só aparece com a suíte inteira.

### Problemas novos, fora do plano

- N1 (grave): strike guardado na Carteira sem o ajuste por provento.
- N2: `"-"` e `NEG "1.234"` do Tryd derrubando a série; `VOL "1.234"` mil vezes menor.
- N3: vencimento de 2028 sumindo sem aviso; falta estender o `b3_holidays.csv` quando a B3
  publicar 2028.

### Segunda auditoria (16/11, Windows)

Refeita no PC Windows, sobre a `development` antiga dele (`fa4a8c7`) e conferida na atual
(`3664f5d`), com entradas sintéticas fora do repositório. Os itens 1 a 5 chegam às mesmas
conclusões de 13/11. O que acrescenta:

- Tarefa 1.4: no Windows falham exatamente os 6 testes do plano (5735 passando, 23 pulados), e o
  produto está certo nos dois casos (detalhe na entrada da tarefa).
- N1, strike de duas fontes: a cadeia de fim de dia usa o PREEXE do COTAHIST
  (`cotahist/adapter.py:251`); a ao vivo, o `ExrcPric` do Cadastro (`tryd/feed.py:176`). Com um
  ajuste por provento entre os dois pregões, o mesmo ticker aparece com strikes diferentes conforme
  a fonte, sem aviso. O `conferir-b3` já detecta o deslocamento (`conferencia.py:342`); o app não.
  Para a enquete da tarefa 1.5.
- N3: a partir de 03/01/2028 toda consulta passa da cobertura do calendário, então não é só o
  vencimento de 2028 que some: some qualquer vencimento.
- Lote com decimais vira `None` (`AllcnRndLot` `100.0`, `1,00`, `100.000000`); o arquivo real de
  03/11 veio inteiro. Strike com milhar no Cadastro CSV (`1.030,00`) também vira `None`, e a série
  some da cadeia ao vivo. Os dois são raros.
- Documentação divergente: `cotahist/parser.py:14` diz que o PREEXE é dividido pelo FATCOT;
  `b3files/conferencia.py:320` diz que na opção de índice (FATCOT 100) ele vem em pontos, sem o
  fator. Sem efeito hoje: opção de índice não entra no app.
- Conflito para a tarefa 2.1: a ADR-0005 (item 8) ordena pelo anualizado líquido; o `dfd6d4f`
  (09/11) passou o Book para bruto sem atualizar a ADR nem registrar `Ruling:`; o plano pede o
  líquido de custos. Pede decisão do autor antes da 2.1.

## Sprint 1 — alertas que não calam

### Tarefa 1.5 — decisões de 16/11 e desenho (strike ajustado na Carteira, N1)

Branch `fix/strike-ajustado-carteira`, a partir da `development` (`3664f5d`). Esta seção vem antes
das outras tarefas para não dar conflito com as entradas da 1.2 (no fim do arquivo) e da 1.4
(antes das "Decisões de 13/11").

- Ruling (autor, 16/11, fonte): o strike ajustado vem do Cadastro da B3 mais recente, pelo
  ticker, o mesmo que o registro (`LoadedLibrary.option_terms`) e o ao vivo já usam. Custo se
  errado: o ajuste só aparece depois de importado um Cadastro posterior a ele (com a rotina
  semanal, até uma semana de atraso).
- Ruling (autor, 16/11, aplicação): queda de até 15% sobre o strike em vigor (faixa de provento em
  dinheiro) é aplicada sozinha e gravada como evento na operação, com o strike anterior, o novo, a
  data e a fonte, sem apagar o original; a Carteira mostra a linha. Qualquer outra mudança (alta,
  ou queda maior que 15%) não é aplicada e vira alerta "confira" (desdobramento, grupamento ou
  bonificação mudam também a quantidade, e o app não tem dados de proventos). Custo se errado:
  uma bonificação de 10% passa como provento e a quantidade fica errada.
- Ruling (autor, 16/11): a divergência de strike entre a cadeia de fim de dia (COTAHIST) e a ao
  vivo (Cadastro) fica para a Sprint 3, com o N2 e o N3. Custo se errado: até lá, as duas cadeias
  podem mostrar strikes diferentes para a mesma série depois de um ajuste.

Análise de impacto (onde o strike gravado entra hoje):

| Onde | Uso | Lê de |
|---|---|---|
| `portfolio.py:233-245` (`_vencer`) | pó ou exercício no vencimento | `leg_states` |
| `domain/portfolio/exercise.py:62-73` | preço da ação no exercício (IR) | `operation.legs` |
| `domain/portfolio/positions.py:66-70` | emolumento do exercício sobre o strike | a perna do evento |
| `domain/alerts/rules.py:139` | risco de exercício | `leg_states` (pelo `OperationSnapshot`) |
| `application/use_cases/_marks.py:75` | teórico da perna | a perna da marcação |
| `adapters/inbound/web/portfolio.py` e a Carteira | o strike na tela | a perna |

Desenho proposto (rulings minhas, para o autor conferir):

- Ruling: evento novo `StrikeAdjusted(leg, on, previous, strike, source)`, gravado no
  `operacoes/*.json` como `{"tipo": "ajuste_strike", "perna", "data", "strike_anterior",
  "strike", "fonte"}`. A `versao` do arquivo segue 1 (o campo é um tipo novo de evento). Custo se
  errado: uma versão antiga do app não lê a operação ajustada; a atualização pelo app (§13 do
  HANDOFF) reduz a janela.
- Ruling: os termos em vigor de cada perna saem de `leg_states` (o `LegState.ref` passa a trazer o
  strike ajustado), e o exercício e o emolumento passam a ler dali, em vez de `operation.legs`. As
  pernas gravadas não mudam.
- Ruling: a conferência roda em `ler_carteira`, **antes** do vencimento, no mesmo padrão do
  `process_expiries` (que já grava o pó numa leitura). Assim o vencimento já decide com o strike
  ajustado.
- Ruling: só o Cadastro mais recente é consultado. Se a série já tiver saído dele (vencida) antes de
  o app ler a Carteira com um Cadastro posterior ao ajuste, o ajuste não é visto. Custo se errado:
  o caso N1 continua possível para quem passa semanas sem abrir o app.
- Ruling: o alerta "confira" tem chave por perna (`strike_mudou:<operação>:<perna>`) e pode ser
  dispensado; segue a regra de sempre dos dispensados: volta quando deixa de valer (o Cadastro
  volta a bater) e vale de novo. Mudou do desenho: lá dizia "volta quando o strike do Cadastro muda
  de novo", o que pediria o valor na chave. Custo se errado: um segundo salto de strike numa perna
  já dispensada não reaparece. O app não oferece correção manual de strike e quantidade.

Implementação (o autor aprovou o desenho em 16/11):

- Domínio (`domain/portfolio/`):
  - `model.py`: o evento `StrikeAdjusted`; `leg_states` aplica o ajuste e confere a perna (só
    opção, só aberta, strike finito e > 0, fonte preenchida, anterior igual ao strike em vigor);
    `event_refs` dá a perna em vigor em cada evento.
  - `adjustment.py`: `strike_change(em vigor, do Cadastro)` → igual, aplicar ou conferir.
  - `exercise.py` (preço da ação no IR) e `positions.py` (emolumento do exercício) passam a usar o
    strike em vigor.
- Ruling: borda inclusiva, como nos alertas: queda de exatamente 15% aplica. Diferença abaixo de
  meio centavo é igual (strikes da B3 têm duas casas); queda de um centavo já aplica.
- Ruling: a data do evento é o dia em que o app aplicou o ajuste, e a data do Cadastro vai na
  fonte (`"Cadastro da B3 de 13/11/2026"`, do nome do arquivo importado; sem data no nome, só
  "Cadastro da B3"). Custo se errado: a data de corte do ajuste na B3 não fica gravada.
- Aplicação: `PortfolioService.process_strike_adjustments(listed)` grava os ajustes e devolve os
  `StrikeNotice`; `ListedStrike` e `StrikeNotice` na porta da Carteira. O `AlertService.evaluate`
  ganhou `strike_notices`.
- Alertas: tipo `strike_mudou`, logo depois do stop sem preço e antes do risco de exercício (um
  strike em dúvida põe em dúvida o risco que vem depois). O `Alert` ganhou `strike` e
  `listed_strike`.
- Ruling: o alerta de strike convive com o risco de exercício e o vencimento da mesma perna (o
  risco segue pelo strike em vigor). Custo se errado: dois alertas para a mesma perna.
- Web e composição: `LoadedLibrary.listed_strike` lê o strike e a data do Cadastro;
  `ler_carteira(portfolio, closes, listed)` confere antes do vencimento, para as rotas da Carteira
  e dos Alertas e para o WebSocket do Mercado. A API manda o evento `ajuste_strike` (com
  `strike_anterior`, `strike` e `fonte`) e o alerta com `strike` e `strike_cadastro`.
- Tela: a linha "16/11/2026 · strike ajustado pela B3 · PETRK300 · 30,00 → 29,47 (Cadastro da B3
  de 13/11/2026)" nos eventos da operação; o alerta "PETRK300: o strike mudou no Cadastro da B3 de
  30,00 para 15,00 e não foi ajustado. Desdobramento, grupamento ou bonificação mudam também a
  quantidade: confira na corretora"; o termo "Ajuste de strike" no glossário, com o "?" do alerta.
  O README ganhou a frase da conferência.
- Testes novos: 8 no domínio, com 23 casos (`tests/portfolio/test_ajuste_strike.py`), o caso N1 e a mudança
  grande no serviço (`tests/application/test_portfolio.py`), o JSON (`test_operations.py`), as
  regras e o serviço dos alertas, o `listed_strike` (`test_loaded.py`), as duas APIs e dois da tela.
  Os testes que conferem um evento ou um alerta inteiro da API ganharam os campos novos (nulos); o
  dublê `_AlertasComVencimento` ganhou o `strike_notices`; o teste do glossário que fixava
  "Americana e europeia" como primeiro termo agora começa em "Ajuste de strike".
- Checagens: ruff, ruff format, mypy, import-linter; pytest em `tests/web`, `tests/adapters`,
  `tests/application`, `tests/alerts`, `tests/portfolio` e `tests/config` (1602 passando; as 2
  falhas do seletor de pasta são as da tarefa 1.4, corrigidas na `fix/testes-windows`); `tsc
  --noEmit` e os testes de Alertas, Carteira e Aprender (69 passando).
- Não conferido no app real: abrir a Carteira com um Cadastro que traga um strike ajustado. Fica
  para o autor, com um Cadastro de depois de uma data-com.

### Tarefa 1.1 — stop com perna sem oferta para zerar

Branch `fix/alerta-stop-sem-oferta`, a partir da `development` (`c5ca7ff`).

- Ruling (autor, 13/11, opção A): perna com cotação mas sem o lado de zerar (comprada sem bid,
  vendida sem ask) entra no stop pelo `LegMark.theoretical`, e o stop dispara rotulado
  "estimado". Sem teórico, o alerta é "stop sem preço para avaliar". Sem cotação nenhuma, segue
  indeterminado. Só o stop usa o estimado; o alvo não. Custo se errado: num book ralo o teórico
  erra e o stop dispara (ou não) à toa.
- Marcação (`_marks.py`): o `LegMark` ganhou `quoted` (`False` quando a série ou a ação está sem
  cotação nenhuma) e `estimated_unrealized`, o não realizado pelo teórico, só na perna cotada sem
  o lado de zerar. O total da Carteira não muda: o estimado serve só ao stop.
- Alertas: o `OperationSnapshot` ganhou `estimated_total` e `unpriced`; o `Alert`, `estimated`; a
  `Evaluation`, `estimated` (as chaves do stop avaliado pelo estimado). Tipo novo
  `stop_sem_preco`, logo depois do stop na ordem de gravidade. A API manda `estimado` em cada
  alerta.
- Tela: "Stop: resultado estimado R$ -60,00, pelo teórico da perna sem oferta para zerar (limite
  R$ -50,00)" e "Stop sem preço para avaliar: uma perna está sem oferta para zerar e sem teórico
  (limite R$ -50,00)", na cor do stop. O termo "Stop e alvo" do glossário explica os dois.
- Ruling: o stop estimado usa a mesma chave do stop executável (`stop:<operação>:-`). Dispensar
  um esconde o outro, e uma avaliação pelo estimado, dispare ou não, não limpa o dispensado, como
  o Tryd piscando (ruling da semana 4). Custo se errado: um stop dispensado não reaparece quando
  só a estimativa melhora e piora de novo.
- Ruling: "stop sem preço para avaliar" é um alerta à parte, com chave própria
  (`stop_sem_preco:<operação>:-`), e o stop fica indeterminado. Dispensar o aviso não esconde o
  stop de verdade quando o preço voltar. Custo se errado: um tipo a mais na tela.
- Ruling: uma perna sem cotação nenhuma deixa o stop inteiro indeterminado, mesmo que as outras
  pernas tenham teórico; a ação cotada sem o lado (sem teórico) dá o aviso de stop sem preço.
  Custo se errado: o stop cala enquanto uma perna está sem cotação (a tarefa 1.3 mostra o motivo).
- Testes novos: os cinco do plano em `tests/application/test_alerts.py`
  (`test_stop_estimado_dispara_com_comprada_sem_bid`, `test_sem_cotacao_stop_segue_indeterminado`,
  `test_sem_teorico_vira_aviso`, `test_alvo_nao_usa_total_estimado`,
  `test_dispensado_nao_volta_quando_o_bid_some`); seis nas regras (`tests/alerts/test_rules.py`);
  três na marcação (`tests/application/test_portfolio.py`); um na API; um na tela. O helper
  `_visao(aberto=None)` passou a ser "sem cotação", que é o caso do Tryd piscando de
  `test_sem_preco_de_zerar_nao_limpa_o_dispensado`.
- Checagens: ruff, ruff format, mypy, import-linter; pytest em `tests/alerts`,
  `tests/application`, `tests/web` e `tests/portfolio` (603 passando); `tsc --noEmit` e os testes
  de Alertas, Termos e DialogoLimites (23 passando).

### Tarefa 1.4 — suíte verde no Windows

Branch `fix/testes-windows`, a partir da `development` (`3664f5d`). Só testes; o produto não muda.

- `tests/ponte/test_tryd7.py` (4): `identidade_do_assembly` recebia `Path("C:/Tryd/StRtd.dll")`.
  No Windows o `Path` vira `C:\Tryd\StRtd.dll` e o comando do PowerShell sai com barra invertida,
  que é o certo ali (a aspa continua dobrada: `O''Brien`); o teste esperava a barra do Linux. Os
  testes passam a usar o caminho como no Windows (`Path(r"C:\Tryd\StRtd.dll")`), que dá o mesmo
  texto nos dois sistemas.
- `tests/web/test_folder_picker.py` (2): `HOME = Path("/home/maria")` vira `\home\maria` no
  Windows, e o ramo "Linux" do produto só roda no Linux. O esperado do kdialog e do zenity passa a
  ser `str(HOME)`, igual ao de antes no Linux.
- Ruling: corrigir o teste e não o produto, como o plano pede; a segunda auditoria confirmou que o
  produto monta o caminho certo no Windows. Custo se errado: nenhum no app; só os testes.
- Posição desta entrada: antes das "Decisões de 13/11", e não no fim do arquivo, para não dar
  conflito com a entrada da tarefa 1.2 (`fix/risco-exercicio-fora-da-janela`), que vai no fim.
- Checagens: ruff, ruff format, mypy, import-linter; no Windows, pytest em `tests/ponte` e
  `tests/web/test_folder_picker.py` (458 passando, 1 pulado; antes, 6 falhas). O Linux não foi
  rodado (sem PC Linux nesta sessão): simulei com `PurePosixPath` e os mesmos esperados batem.

## Decisões de 13/11 para as próximas tarefas

- Ruling (autor, 13/11, tarefa 1.2): opção vendida dentro do dinheiro avisa em qualquer prazo; o
  "perto do strike" continua só na janela de `expiry_days`. Custo se errado: uma vendida pouco
  dentro do dinheiro a 40 dias avisa todo dia até ser dispensada.
- Ruling (autor, 13/11): N1 vira a tarefa 1.5 da Sprint 1, com a própria enquete de como achar o
  strike ajustado; N2 e N3 entram na Sprint 3. Custo se errado: a Sprint 1 cresce cerca de meio
  dia, e até a Sprint 3 uma série com "-" no Tryd some da cadeia.

### Tarefa 1.2 — risco de exercício fora da janela

Branch `fix/risco-exercicio-fora-da-janela`, a partir da `development` (`3664f5d`). Decisão do
autor acima ("Decisões de 13/11").

- `rules.py`: a perna vendida dentro do dinheiro dá o risco de exercício em qualquer prazo, com os
  dias úteis, o vencimento e o "Rolar" de sempre; o "perto do strike" e o vencimento próximo
  continuam só na janela de `expiry_days`.
- Ruling: fora da janela, a perna vendida sem spot do ativo deixa a chave do risco indeterminada,
  como dentro dela. Assim o Tryd piscando não limpa um risco dispensado a 40 dias. Custo se
  errado: mais chaves indeterminadas na tarefa 1.3 (uma por vendida sem spot).
- O teste antigo `test_risco_fora_da_janela_de_dias_nao_dispara` exigia silêncio para uma call
  vendida dentro do dinheiro (spot 35, strike 30) a 6 du, o que a decisão muda. Virou
  `test_perto_do_strike_fora_da_janela_nao_dispara` (spot 29,50). Novos:
  `test_vendida_dentro_do_dinheiro_avisa_fora_da_janela` (o caso provado do plano: put strike 30,
  ativo a 26, 10 du), `test_fora_da_janela_sem_spot_risco_indeterminado` e
  `test_comprada_dentro_do_dinheiro_fora_da_janela_nao_avisa`.
- Textos: o termo "Risco de exercício" do glossário e o parágrafo dos Alertas no README. O README
  ganhou também a frase do stop estimado, que faltou na tarefa 1.1.
- Checagens: ruff, ruff format, mypy, import-linter; pytest em `tests/alerts`,
  `tests/application`, `tests/web` e `tests/portfolio` (606 passando); `tsc --noEmit` e os testes
  de Termos e Alertas (20 passando).

### Tarefa 1.3 — alertas que não puderam ser avaliados, visíveis

Branch `fix/alertas-nao-avaliados`, a partir da `development` (`3795cc2`, já com a 1.2, a 1.4 e a
1.5).

- Domínio (`domain/alerts/`): `UndeterminedReason` (`sem_spot`, `sem_preco`,
  `fora_do_calendario`) e `Undetermined` (o alerta e o motivo). A `Evaluation` ganhou
  `not_evaluated`, na ordem de gravidade; o `undetermined` (as chaves) segue igual e continua
  guardando os dispensados.
- Onde nasce cada motivo: vencimento fora do calendário → o vencimento próximo e, na vendida, o
  risco de exercício; vendida sem spot (dentro ou fora da janela) → o risco; stop ou alvo sem total
  pelo preço de zerar → `sem_preco`. Nos não avaliados das pernas vai o ticker.
- Ruling: o stop que já saiu como "stop sem preço para avaliar" fica fora dos não avaliados (a
  chave segue indeterminada, para o dispensado ficar). Custo se errado: o mesmo problema contado
  duas vezes na tela.
- Ruling: os não avaliados aparecem mesmo quando o alerta está dispensado, e o aviso não se
  dispensa: ele diz que a avaliação parou, não que o alerta disparou, e some sozinho quando ela
  volta. Custo se errado: com o Tryd piscando, a lista aparece e some.
- Ruling: o "Alertas (N)" do menu continua contando só os alertas visíveis; os não avaliados não
  entram. Custo se errado: o menu não chama a atenção para uma avaliação parada.
- Ruling: o motivo `sem_preco` cobre também a perna sem cotação nenhuma ("sem preço para zerar
  alguma perna"); o plano pedia três motivos, e separar o "sem cotação" mudaria pouco para quem lê.
- Serviço e API: `AlertsView.not_evaluated`; `AlertasOut.nao_avaliados` com `chave`, `tipo`,
  `operacao`, `nome`, `ativo`, `perna`, `ticker` e `motivo`, também no WebSocket.
- Tela: a caixa "N alertas não puderam ser avaliados" (no singular, "1 alerta não pôde ser
  avaliado") depois dos alertas, uma linha por item, por exemplo "put coberta · risco de exercício
  de PETRW280: sem a cotação do ativo". Borda tracejada e sem a cor de perda: é informação, não
  alerta. O "Nenhum alerta agora." só aparece quando também não há não avaliados. O README ganhou a
  frase.
- Testes novos: quatro nas regras, um no serviço, um na API e dois na tela. O
  `test_alertas_vao_no_ao_vivo_junto_da_carteira_e_so_quando_mudam` esperava os dados dos alertas
  sem nada, que era justamente o silêncio que esta tarefa tira: agora confere o stop entre os não
  avaliados. A fixture do `aoVivo.test` ganhou o campo novo.
- Checagens (gate completo, fim da Sprint 1, no Windows): pytest inteiro com cobertura (5785
  passando, 23 pulados, cobertura de 98,51%), mypy, ruff, ruff format, import-linter;
  `npm --prefix frontend run verificar` (319 testes) e `run build` (verde; o aviso de tamanho do
  pacote é o de antes).

## 2026-11-17: fechamento da Sprint 1

- Feitas: 1.1 (PR #20), 1.2 (PR #21), 1.4 (PR #22), 1.5 (PR #23) e 1.3 (esta branch). Aceite do
  plano: os itens com teste; pytest sem falha no Windows (gate acima) e no Linux (CI dos PRs).
- Fica para o autor conferir no app: o stop estimado e o "stop sem preço" (1.1), o risco fora da
  janela (1.2), o ajuste de strike com um Cadastro de depois de uma data-com (1.5) e a lista de não
  avaliados com o Tryd fechado (1.3).
- Próximo: a Sprint 2. Antes da 2.1, a decisão do conflito bruto × líquido (ADR-0005, item 8, e o
  `dfd6d4f`), registrada na segunda auditoria.

# Ledger — semana 3 (Book e Análise)

Plano: [`plans/2026-11-02-app-semana-3-book-analise.md`](plans/2026-11-02-app-semana-3-book-analise.md).
Branch `feat/app-semana-3`, a partir da `development` (`088f67e`).

## 2026-11-02: Task 1 — IV de 30 dias, rank, percentil e regime de vol

- `domain/analytics/volatility.py`: `ExpiryVol(business_days, vol)`, `HorizonVol(vol, extrapolated)`, `iv_at_horizon` (variância total `σ² x τ` interpolada linearmente em τ = du / 252), `iv_rank`, `iv_percentile`, `VolRegime` e `vol_regime`. Constantes da spec com nome: prazo de 30 du, vencimento mínimo de 5 du, janela de 252 pregões, mínimo de 60, rank alto 50%, baixo 30% e margem de 10%.
- Conferido à mão: 20 du a 30% e 40 du a 34% dão IV 30 de 0,327210 (a média das vols daria 0,32); 25 du a 32% e 45 du a 28% dão 0,305614. Propriedades (hypothesis): vol plana nos vencimentos dá a mesma vol no prazo, e a IV no prazo nunca sai do intervalo das vizinhas (a variância no prazo é média ponderada das duas, com pesos >= 0).
- Ruling: o rank usa a mínima e a máxima da janela **com a IV de hoje incluída**, então fica sempre entre 0 e 1. A IV de hoje da aba Análise vem da cadeia do momento (Task 11) e pode sair do intervalo do histórico de fim de dia; sem isso o rank passaria de 100%. Se errado: uma linha em `iv_rank`.
- Ruling: com a janela inteira na mesma IV (máxima = mínima), o rank sai `None` em vez de um número arbitrário; o percentil sai 0 (nenhum pregão abaixo). Na prática não acontece com 60 pregões reais. Se errado: nada no resultado do book, porque o regime cai na regra sem rank.
- Ruling: o percentil conta os pregões **estritamente** abaixo da IV de hoje ("abaixo", como na spec).
- Ruling: dois pontos com o mesmo número de dias úteis são recusados (`InvalidDomainValueError`): vencimentos distintos caem sempre em dias úteis distintos, então é erro de quem chama. Se errado: o histórico (Task 2) tem de escolher um dos dois antes.
- A janela são os **últimos 252 valores** do histórico recebido: quem chama passa só os pregões com IV, em ordem cronológica (Task 2).
- Gates: 4961 testes (cobertura 98,10%; `domain/analytics` em 100%), mypy, ruff e import-linter. Frontend sem mudança.

## 2026-11-02: Task 2 — histórico de IV pelos COTAHIST da biblioteca

- `adapters/outbound/cotahist/vol_history.py`: `CotahistVolHistory(loader, calendar, cdi_annual)` implementa o `VolHistoryPort` (novo, em `application/ports/outbound.py`) e devolve `DailyVol(session, close, iv30, extrapolated, hv21)` (novo, em `domain/analytics/volatility.py`) por pregão, do mais antigo ao mais recente, ou o motivo: sem COTAHIST, sem cadastro (motivo da biblioteca), ativo sem fechamento, arquivo ilegível.
- A IV de cada vencimento é a do **mesmo** `build_smile` da cadeia de fim de dia, no spot; a de 30 du vem do `iv_at_horizon` da Task 1. Conferido: na fixture, a IV 30 de PETR4 em 23/10 é igual (1e-12) à calculada pela cadeia do `CotahistOptionChainAdapter` daquele pregão. A HV 21 é a `realized_volatility` que já existia, pregão a pregão.
- Refactor: o vínculo série–ativo e as rejeições que só dependem do registro (strike corrigido, vencida, book cruzado, strike zero) saíram do adapter para `cotahist/series_rules.py` (`link_underlying`, `record_rejection`, `series_root`, `specification_class`), usadas pelo adapter e pelo histórico. Comportamento do adapter igual (os testes antigos seguem verdes).
- **Step 0 não feito:** os arquivos reais da B3 não estão neste PC. A leitura não depende da ordem do anual: agrupa por pregão em memória só os registros da raiz do ativo pedido. Falta medir, com o anual real, o tempo e a memória da primeira leitura (o parser lê o anual em 12 a 18 s no outro PC; aqui soma o smile de até dois vencimentos por pregão).
- Ruling: o cache `vol_history.sqlite` (raiz da biblioteca) guarda os pregões **por arquivo** (caminho, tamanho e mtime), ativo e CDI, em vez de por (pregão, ativo). Dá o que a spec pede: a segunda consulta não relê nada, um diário importado é o único arquivo lido, e trocar o CDI recalcula. Se errado: baixar de novo o anual faz relê-lo inteiro uma vez.
- Ruling: o histórico **não exige o estilo de exercício**. As séries vencidas não estão no cadastro do dia, e o estilo não muda a IV: o smile usa a fórmula europeia em todas as séries, como na cadeia. O vínculo usa o cadastro quando a série está nele, senão a raiz única ou a classe do ESPECI, como no adapter. Se errado: séries do passado de raiz dividida (PETR3/PETR4) dependem do ESPECI das opções, premissa ainda a conferir no arquivo real (HANDOFF de 28/10).
- Ruling: de cada lado do prazo, só o vencimento mais perto com vol no spot entra; se ele não tem book em volta do spot, vale o seguinte daquele lado. Dá o mesmo resultado de calcular todos e chamar `iv_at_horizon`, sem montar smiles que não seriam usados.
- Ruling: vencimento fora da cobertura do calendário (2028) fica fora do pregão, sem derrubá-lo; ativo com registros divergentes no pregão fica sem esse pregão (o adapter o dá como indisponível); com arquivos sobrepostos, vale o primeiro na ordem da biblioteca (o mais antigo), como nos fechamentos do `session.py`.
- Nota: a fixture sintética tem opções só no pregão de referência (o plano fala em "17 pregões", que não existem nela). Os testes de vários pregões usam COTAHIST sintéticos montados no `tmp_path`, com book em três pregões.
- Gates: 4979 testes (cobertura 98,15%; `vol_history`, `series_rules`, `adapter` e `domain/analytics` em 100%), mypy, ruff e import-linter. Frontend sem mudança.

## 2026-11-02: Task 3 — presets do book no domínio e no perfil

- `domain/book/presets.py`: `BookPreset` (Conservador, Moderado, Arrojado) e `BookSettings` com os valores da spec §3.2 em `BookSettings.default(preset)`; faixas validadas (delta de 0 a 1 com mínimo <= máximo, negócios >= 0, vencimentos >= 1, spread e risco > 0, piso em (0, 1]).
- `Profile.book: BookSettings | None = None` e `Profile.book_settings`, que devolve o Moderado quando o perfil não tem o campo. O `perfil.json` só ganha a chave `book` depois que o usuário escolhe um preset; perfil antigo é lido sem erro.
- `ProfileService.set_book_settings` e `PUT /api/perfil/book`; `GET /api/perfil` e as outras rotas de perfil devolvem o `book` já resolvido.
- Ruling: o corpo do `PUT` é `{preset, valores?}`. Sem `valores`, valem os padrões do preset: é assim que a tela troca de preset e "volta ao padrão" sem copiar a tabela da spec no frontend. Com `valores`, eles são gravados como vieram, no preset escolhido.
- Gates: 5007 testes (cobertura 98,17%), mypy, ruff e import-linter. Frontend sem mudança (o tipo `Perfil` ganha o `book` na Task 10).

## 2026-11-02: Task 4 — item do book, contexto de vol e a família Renda

- `domain/book/model.py`: `Metric(key, label, value, unit)` com `MetricUnit`, `BookLeg`, `BookStock`, `BookItem` (família, chave do modelo, ativo, vencimento, du, pernas, ação, critério, números, porquê e rótulos), `BookLabel`, `BookExclusion`, `FamilyResult` (itens só EXECUTAVEL, referências, exclusões), `best_per_structure` (os 5 melhores por estrutura, desempate por ativo, vencimento e strikes) e `passes_liquidity`.
- `VolContext`, `vol_context` e `end_of_day_context` ficaram em `domain/analytics/volatility.py`, e não em `domain/book`: a aba Análise (Task 11) usa o mesmo contexto. O do fim de dia é o último pregão do histórico contra as IVs dos anteriores.
- `domain/book/renda.py`: `renda_items(ranking, settings, contexts)` converte o ranking da Sprint 5. Critério: anualizado líquido na venda coberta e na put coberta, retorno sobre o risco líquido nas travas; números de apoio: prêmio, probabilidade de exercício, delta da vendida, dias úteis e o IV rank quando há contexto.
- Ruling: a família do item é o `Family` dos modelos do montador (mesmos quatro valores), em vez de um `BookFamily` repetido.
- Ruling: o porquê é um molde com `{chave}` das métricas do item, e quem mostra formata os números (decisão 8 da Sprint 3: conversão de exibição só no adapter). O item recusa um porquê que cite métrica que ele não tem.
- Ruling: os filtros de liquidez do preset valem só para o que entra no book (todas as pernas, como na spec); as referências não passam por eles, porque sem book completo não há spread a medir e elas seriam sempre descartadas. Por isso o `BookService` pede o ranking sem `min_trades` e sem `max_spread_pct`. Reprovar na liquidez é filtro, não exclusão (como a faixa de delta).
- Ruling: vencimento no próprio pregão (0 du) fica fora do book em todas as famílias.
- Gates: 5025 testes (cobertura 98,22%; `domain/book` em 100%), mypy, ruff e import-linter. Frontend sem mudança.

## 2026-11-02: Task 5 — família Volatilidade

- `domain/book/scan.py`: a varredura comum às famílias sobre a cadeia — os N próximos vencimentos com pelo menos 1 du (os dias úteis vêm de quem chama, pelo calendário), o smile de cada um, o delta pelo `series_risk` (o mesmo do painel de renda), o prêmio pelo lado (EXECUTAVEL, INDICATIVO ou TEORICO), a liquidez das pernas e o resultado no vencimento pelo cálculo do montador (`expiry_summary`, `net_result_breakdown` nos pontos de extremo, `probability_of_profit` com a vol do smile no spot).
- Refactor: os pontos de extremo do líquido saíram do `StrategyBuilderService` para `domain/income/net_result.extreme_spots`, usados pelo montador e pelo book (o book soma os breakevens, onde o IR muda de inclinação). O montador continua igual (testes verdes).
- `domain/book/volatilidade.py`: `volatility_items(chain, context, settings, schedule, business_days)`. Vol alta: iron condor vendido (vendidas na faixa de delta, compradas 1 strike mais fora), borboleta comprada (miolo no dinheiro, asas a 1 e a 2 strikes) e, com `allow_unlimited_loss`, strangle vendido. Vol baixa: straddle comprado no dinheiro e strangle comprado na faixa de delta. Neutra: as duas, rotuladas "sem sinal claro". Rótulos também para regime pela HV e IV 30 extrapolada.
- Conferido à mão, sem custos: o iron condor W260/W280/K320/K340 da cadeia falsa tem crédito, risco `(2 - c) x 100`, ganho/risco `c / (2 - c)` e breakevens `28 - c` e `32 + c` em desvios (`|ln(BE/30)| / (IV x sqrt(du/252))`).
- Ruling: o strangle vendido, que tem perda ilimitada, usa como critério a distância até o breakeven mais perto em desvios-padrão (maior é melhor), espelho da compra de vol; ganho/risco não existe sem perda máxima. O risco máximo do preset não se aplica a ele: quem o libera é o `allow_unlimited_loss`.
- Ruling: estrutura com ganho máximo líquido <= 0 (custos maiores que o crédito) fica fora, como filtro.
- Ruling: a put americana fica fora da varredura com o motivo, como no painel de renda: o delta dela, que escolhe a faixa, não tem a aproximação europeia (ADR-0002).
- Exclusões repetidas (a mesma perna sem preço em várias combinações) aparecem uma vez só.
- Checagens (combinado com o autor em 02/11: o gate completo fica para o fim da semana): ruff, mypy, import-linter e as suítes do book, da renda e do montador. A última suíte inteira (fim da Task 5, antes do combinado) deu 5042 testes, 98,27%.

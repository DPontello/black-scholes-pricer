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

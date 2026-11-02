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

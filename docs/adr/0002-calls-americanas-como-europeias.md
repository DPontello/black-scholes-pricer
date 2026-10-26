# ADR-0002 — Calls americanas de ação precificadas como europeias

- **Status:** Aceita — **emenda a decisão ratificada nº 2** (ROADMAP, 2026-07-02)
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

A decisão nº 2 restringe o MVP a opções europeias; `BlackScholesPricingModel.supports()`
rejeita `ExerciseStyle.AMERICAN`. Na B3, as calls sobre ações são em sua
maioria americanas — e a venda coberta, estrutura principal do painel de
renda, usa exatamente essas calls. Sem emenda, o painel não precifica nem
calcula volatilidade implícita da sua estrutura principal até a Fase 6
(binomial).

Para uma call sem dividendos até o vencimento, o exercício antecipado nunca
é ótimo e o preço americano coincide com o europeu. Com dividendos, ele pode
ser ótimo às vésperas da data ex. A premissa desta ADR é que a B3 **ajusta o
strike das opções sobre ações pelos proventos em dinheiro**, o que remove a
maior parte do incentivo ao exercício antecipado da call.

Para puts, o exercício antecipado pode ser ótimo mesmo sem dividendos —
especialmente com juros altos — e a aproximação europeia não é defensável.

## Decisão

1. `supports()` passa a aceitar **CALL + AMERICAN** sobre ações, precificada
   por Black-Scholes europeu com `q = 0`.
2. O resultado carrega uma **marca explícita de aproximação** (forma exata
   definida na implementação, sem quebrar o contrato `PricingModel`); o
   painel exibe essa marca.
3. **PUT + AMERICAN continua rejeitada** com `UnsupportedExerciseStyleError`.
4. Precificação americana exata segue na Fase 6, pelo mesmo seam
   (`ExerciseStyle` + `supports()`).

## Premissa a verificar (gate do spike da Sprint 5)

- Regra vigente de ajuste de strike por proventos em dinheiro (dividendos e
  JCP) no manual de procedimentos operacionais da B3. **Se a regra não se
  confirmar**, esta ADR é reaberta antes de qualquer código de
  precificação americana-como-europeia.

## Consequências

- A venda coberta entra no painel na Sprint 5.
- Volatilidade implícita de call americana fica levemente viesada perto de
  datas ex; o painel sinaliza séries com vencimento após uma data ex
  conhecida quando essa informação estiver disponível.
- Os testes da decisão nº 2 (rejeição de AMERICAN) passam a cobrir só PUT;
  um teste novo fixa a aceitação de CALL com a marca de aproximação.

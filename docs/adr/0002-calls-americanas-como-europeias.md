# ADR-0002 — Calls americanas de ação precificadas como europeias

- **Status:** Aceita — **emenda a decisão ratificada nº 2** (ROADMAP, 2026-07-02);
  premissa verificada no spike de 2026-10-26
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

## Verificação (spike 2026-10-26)

**Status: premissa verificada.** A ADR segue aceita, sem reabertura.

Fonte principal: Manual de Procedimentos Operacionais (MPO) da Câmara B3,
item 7.9.1 (tratamento de eventos corporativos para opções sobre ativos do
mercado à vista), subitem 1 (eventos em recursos financeiros), versão de
24/02/2025, consultado em 26/10/2026:
<https://www.b3.com.br/data/files/CC/F6/D6/2E/8083591029BEEC39AC094EA8/MPO%20da%20Camara%20B3.pdf>

- **Fórmula:** `PE_aj = PE − EV`, com o strike ajustado arredondado na
  segunda casa decimal; a quantidade da posição não muda. O ajuste roda no
  processamento noturno da última data "com": as séries já abrem ajustadas
  no pregão ex. Por ser aditivo, preserva o valor intrínseco.
- **Valor do evento (`EV`):**
  - dividendo: **100%** do valor;
  - JCP: **0,825 × JCP desde 01/01/2026**. O texto do MPO ainda traz 0,85;
    o fator novo vem do OC 026/2025-VPE, de 30/12/2025, que acompanha a
    alta do IRRF do JCP para 17,5% e prevalece sobre o MPO:
    <https://www.b3.com.br/data/files/0F/23/BA/E4/1117B9105B12E5A9AC094EA8/OC%20026-2025-VPE%20ATUALIZACAO%20NA%20TRIBUTACAO%20DE%20JCP%20DE%20CONTRATOS%20FUTUROS%20E%20OPCOES%20A%20PARTIR%20DE%202026_PT.pdf>
- **Alcance:** todas as opções sobre ativos do mercado à vista — **calls e
  puts, de qualquer estilo**.
- **Sem percentual mínimo:** o texto vigente ajusta qualquer provento em
  dinheiro.
- **Exceção — provento >= strike:** em vez da subtração, strike e
  quantidade são ajustados pelo fator `F = Pex / Pcom` (strike × F,
  quantidade ÷ F). A regra nasceu em ofícios caso a caso, como o
  OC 141/2023-PRE (Petrobras, 10/08/2023), e hoje está no MPO:
  <https://www.b3.com.br/data/files/44/41/F8/1E/E90E98101D7C7D98DC0D8AA8/OC%20141-2023%20PRE%20Tratamento%20para%20Dividendos%20Superiores%20ao%20Strike_Petrobras%20(PT).pdf>

Nuances, que não reabrem a ADR:

1. **Proteção parcial do JCP.** Como só 82,5% do JCP sai do strike, sobra
   um incentivo residual ao exercício antecipado da call perto de datas ex
   de JCP. É o viés já previsto em Consequências, e a marca de aproximação
   o sinaliza.
2. **Estilo por série.** Muitas calls são **europeias** e as puts são
   praticamente todas europeias. Contagem de terceiros (opcoes.net.br,
   <https://opcoes.net.br>, vencimento de 19/11/2026, cotações do pregão de
   23/10/2026, consultado em 26/10/2026):

   | Ativo | Calls americanas | Calls europeias | Puts americanas | Puts europeias |
   |---|---|---|---|---|
   | PETR4 | 111 | 98 | 0 | 209 |
   | VALE3 | 75 | 97 | 0 | 172 |
   | ITUB4 | 62 | 64 | 0 | 126 |
   | BOVA11 | 108 | 72 | 0 | 180 |

   Entre 40% e 56% das calls de cada ativo são europeias. Por isso o estilo
   vem **por série, do cadastro de instrumentos da B3** (ADR-0006), e nunca
   é inferido do tipo da opção: a série europeia é precificada sem a marca
   de aproximação, e a rejeição de PUT + AMERICAN quase não atinge série
   real.

## Consequências

- A venda coberta entra no painel na Sprint 5.
- Volatilidade implícita de call americana fica levemente viesada perto de
  datas ex; o painel sinaliza séries com vencimento após uma data ex
  conhecida quando essa informação estiver disponível.
- Os testes da decisão nº 2 (rejeição de AMERICAN) passam a cobrir só PUT;
  um teste novo fixa a aceitação de CALL com a marca de aproximação.

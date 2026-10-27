# Sprint 5 — Fase 2: adapter COTAHIST, preço teórico, ranking e painel HTML

Especificação de trabalho para os engenheiros da fase 2. Fontes normativas, nesta
ordem: ADRs 0002–0007 em `docs/adr/` (já com as verificações do spike), seção
"Sprint 5" do `docs/ROADMAP.md` (escopo, critérios de aceite, casos de teste),
`docs/ARCHITECTURE.md`, `docs/CONVENTIONS.md` e `.claude/CLAUDE.md`. Este arquivo
fecha as escolhas técnicas que as ADRs deixaram para a implementação. Quando uma
escolha abaixo for técnica, registre-a em docstring; quando for de negócio, ela já
foi decidida pelo usuário (mesa) e está marcada como **[mesa]**.

## 0. Estado de partida (development após a integração da fase 1)

- `domain/model/chain.py`: `OptionQuote`, `OptionChain`, `PriceQuality`, `LegPremium`,
  `executable_premium`, `worst_quality`, `OptionQuote.is_theoretical_eligible`.
- `application/ports/outbound.py`: `OptionChainPort.get_chain(underlying_symbol)`;
  suíte herdável `tests/contract/option_chain_contract.py` (`known_symbols()`).
- `domain/kernel/implied_vol.py`: `implied_vol(...) -> ImpliedVolResult`.
- Kernel com preço nunca negativo.
- `BlackScholesPricingModel.supports()` aceita CALL+AMERICAN com
  `PricingResult.approximation` (marca); PUT+AMERICAN rejeitada.
- `domain/income/`: `CostSchedule` (com taxa do à vista/exercício e corretagem de
  exercício), custos de montagem e de exercício por cenário, `IncomeMetrics` com
  extremos brutos e líquidos, `cash_secured_put_metrics`, `covered_call_metrics`,
  `credit_spread_metrics`; factory `vertical_spread` + `vertical_spread_direction`.
- Leia o código real: os nomes exatos podem ter mudado na revisão.

## 1. Extensões de domínio (pré-requisito das trilhas; branch `feat/chain-exclusions`)

1. `UnderlyingUnavailableError(DomainError)` no catálogo `errors.py`: subjacente
   conhecido na fonte, mas sem preço utilizável no pregão (ADR-0004: "fica fora do
   painel do dia com motivo explícito"). Mensagem carrega o motivo.
2. `RejectedSeries(symbol: str, reason: str)` (VO frozen) e campo
   `OptionChain.rejected_series: tuple[RejectedSeries, ...] = ()`: séries que a fonte
   trouxe mas que o adapter não pode transformar em `OptionQuote` sem inventar dado
   (sem estilo no cadastro **[mesa]**, book cruzado na fonte, ticker duplicado,
   strike corrigido por índice etc.). Invariantes: símbolos únicos entre si e
   disjuntos dos `quotes`; motivo não vazio.
3. Campo `OptionChain.underlying_book_available: bool = True` **[mesa]**: quando o
   ativo-objeto tem fechamento mas não tem ofertas, o adapter monta o snapshot com
   `spot = bid = ask = mid = fechamento` e marca `False`; o painel mostra "sem
   ofertas" e nenhuma métrica de renda usa o book do ativo-objeto. Documente no
   docstring que, com `False`, bid/ask/mid do snapshot não são observados.
4. Docstring do `OptionChainPort`: símbolo desconhecido -> `UnknownSymbolError`;
   conhecido sem preço utilizável -> `UnderlyingUnavailableError`.
5. Suíte de contrato: `rejected_series` disjunta de `quotes`; e, se o adapter
   declarar um `unavailable_symbol()` opcional, ele levanta
   `UnderlyingUnavailableError`.

## 2. Trilha A — `CotahistOptionChainAdapter` (branch `feat/cotahist-adapter`)

Pacote `src/options_engine/adapters/outbound/cotahist/` (só stdlib: `zipfile`,
`sqlite3`, `csv`, `io`, `statistics`, `math`).

### 2.1 Parser do COTAHIST (`parser.py`)
- Lê `.TXT` ou `.ZIP` (um membro .TXT). Encoding **cp1252**. Registros de 245
  caracteres (aceitar `\r\n`/`\n`). Header `00`, registros `01`, trailer `99`
  (valide que o total de registros do trailer bate com o lido).
- Linha de tamanho errado, campo numérico inválido ou arquivo truncado (sem
  trailer) -> `CotahistFormatError` (exceção do adapter, filha de `ValueError`
  não; crie `class CotahistFormatError(Exception)` no pacote) com **caminho e número
  da linha**. Ela é levantada na carga (construtor/loader), nunca pelo port; a CLI a
  captura e reporta.
- Campos usados (posições 1-based inclusivas): DATPRE 3–10, CODBDI 11–12,
  CODNEG 13–24, TPMERC 25–27, NOMRES 28–39, ESPECI 40–49, PREULT 109–121,
  PREOFC 122–134, PREOFV 135–147, TOTNEG 148–152, QUATOT 153–170,
  VOLTOT 171–188, PREEXE 189–201, INDOPC 202, DATVEN 203–210, FATCOT 211–217.
- Preços (11)V99: 2 decimais implícitas; **todos os campos de preço, inclusive
  PREEXE, divididos por FATCOT** (o layout diz que preços vêm por unidade de
  FATCOT). VOLTOT (16)V99: 2 decimais, volume financeiro em reais (não dividir por
  FATCOT).
- Mercados: TPMERC 010 = à vista (ativo-objeto); 070 = call; 080 = put. Ignorar o
  resto.

### 2.2 Cadastro de instrumentos (`instruments.py`) **[mesa: obrigatório]**
- CSV (`InstrumentsConsolidatedFile_*.csv`), baixado manualmente. Detectar o
  delimitador (`;` ou `,`) e a linha de cabeçalho procurando as colunas
  `TckrSymb` e `OptnStyle` (pode haver linhas de preâmbulo). Encoding: tente
  `utf-8-sig`, depois `cp1252`.
- Mapear `OptnStyle` por prefixo, sem distinguir maiúsculas: `AMER*` -> AMERICAN,
  `EURO*` -> EUROPEAN. Vazio ou outro valor -> estilo desconhecido. O domínio exato
  do campo não está documentado no glossário da B3: registre isso como premissa a
  conferir com um arquivo real.
- Colunas opcionais úteis (não exigir): `Asst`, `UndrlygTckrSymb1`, `ExrcPric`,
  `XprtnDt`, `OptnTp`, `AllcnRndLot`.

### 2.3 Montagem da cadeia (`adapter.py`)
- Construtor (DI explícita, nada de ler ambiente): `session_date: date`,
  `cotahist_paths: Sequence[Path]` (diário, mensal ou anual; vários arquivos
  permitidos e mesclados por pregão), `instruments_path: Path`,
  `risk_free_rate: RiskFreeRate`, `realized_vol_window: int = 21` (retornos),
  `cache_path: Path | None = None`, `valuation_timezone = B3_UTC_OFFSET`.
- Timestamp das cotações e do snapshot: `datetime(session_date, 18:00,
  valuation_timezone)` (marcador de fim de pregão; só a data importa).
- Ativo-objeto: registro TPMERC 010 do `underlying_symbol` no pregão.
  - Símbolo ausente em todo o conjunto de arquivos -> `UnknownSymbolError`.
  - Presente, mas sem registro no pregão ou com PREULT = 0 ->
    `UnderlyingUnavailableError("sem fechamento no pregão")`.
  - Spot = PREULT. Se PREOFC e PREOFV > 0 e PREOFC <= PREOFV: bid/ask = ofertas e
    mid = média. Senão **[mesa]**: `bid = ask = mid = spot` e
    `underlying_book_available = False`.
  - Vol realizada: desvio-padrão amostral dos log-retornos fechamento a fechamento
    dos últimos `realized_vol_window` retornos até o pregão (inclusive), vezes
    sqrt(252), como `Volatility(value, BUSINESS_252)`. Histórico insuficiente ou vol
    zero -> `UnderlyingUnavailableError` com o motivo e o mínimo exigido (nunca um
    número inventado). Limitação documentada: preços do COTAHIST não são ajustados
    por proventos/desdobramentos.
- Séries: registros 070/080 do pregão cuja raiz (4 primeiras letras do CODNEG)
  é a raiz do ativo-objeto (4 primeiras letras do símbolo). Se mais de um
  ativo-objeto do pregão tiver a mesma raiz, desempate pela classe em ESPECI (ON/PN/
  UNT nos 2–3 primeiros caracteres não brancos) e, se o cadastro trouxer
  `UndrlygTckrSymb1` preenchido, ele prevalece. Ambíguo -> `RejectedSeries`.
  Registre a regra de vínculo como premissa a conferir com arquivo real.
  - Zero da fonte -> `None` em bid/ask/last (ADR-0003). TOTNEG -> `trades`;
    VOLTOT -> `volume` (financeiro).
  - Rejeitar com motivo (`RejectedSeries`): sem estilo no cadastro; INDOPC != 0
    (strike corrigido por índice); book cruzado na fonte; CODNEG duplicado no
    pregão; DATVEN anterior ao pregão.
  - `OptionTerms(underlying=symbol, strike=PREEXE/FATCOT, expiry=DATVEN,
    option_type, exercise_style)` — NUNCA confiar no default EUROPEAN.
- Cache `sqlite3` opcional por pregão: chave = (impressão digital de cada arquivo:
  caminho absoluto, tamanho, mtime) + pregão; guarda os registros já parseados
  necessários (pregão + histórico de fechamentos do ativo-objeto). Cache inválido
  ou ausente -> reparse. Testes com `tmp_path`; nunca gravar fora do caminho dado.
- Fixture **sintética** versionada em `tests/data/cotahist/` (não redistribuir
  dados reais da B3): um COTAHIST com header/trailer corretos, ~25 pregões de
  fechamento de PETR4 e VALE3 para a vol realizada e, no pregão de referência
  (2026-10-23, sexta), séries de calls e puts com: book completo, só bid, só ask,
  book vazio com negócio, book vazio sem negócio, série sem estilo no cadastro,
  INDOPC != 0, dois vencimentos (2026-11-19, quinta, porque 20/11 é feriado nacional, e 2026-12-18), strikes ao redor do spot;
  e um cadastro CSV sintético coerente. Inclua um script gerador
  (`tests/data/cotahist/build_fixture.py`) que reproduz os arquivos de forma
  determinística e documente no README da pasta que os dados são sintéticos.
- Testes: subclasse da `OptionChainPortContract` com a fixture; parser (linha
  truncada/tamanho errado/trailer divergente -> erro com número da linha);
  fronteira zero -> `None`; FATCOT != 1; cadastro com preâmbulo e `;`/`,`; cache
  hit/miss/invalidação; vol realizada contra cálculo manual; ativo sem ofertas;
  histórico insuficiente.

## 3. Trilha B — preço teórico e ranking (branch `feat/rank-income`)

### 3.1 Smile e preço TEÓRICO (domínio, `domain/pricing/smile.py` ou similar)
- Volatilidade implícita por série com book completo, a partir do **mid** (o mid só
  serve para o smile — ADR-0004), com spot do snapshot, `q = 0`, taxa contínua do
  snapshot e tau em BUSINESS_252 resolvido pelo calendário. Só `CONVERGED` vira
  ponto do smile.
- Um smile por vencimento combinando calls e puts: em strikes com as duas, use a
  série fora do dinheiro (put se K < spot, call se K >= spot). Interpolação linear
  em strike entre os vizinhos; **sem extrapolação**: fora do intervalo de pontos não
  há preço teórico (motivo "fora do smile"). Sem pontos -> sem teórico.
- TEÓRICO só para `quote.is_theoretical_eligible` (book vazio e sem negócio):
  `LegPremium(bs_price(vol interpolada), TEORICO)`.
- Delta e N(d2) (rotulado "probabilidade risco-neutra de exercício") por série com a
  vol implícita da própria série (mid) quando houver, senão a vol do smile; sem
  nenhuma das duas -> série sem delta, excluída dos filtros por delta com motivo.
- Call americana: aproximação europeia com marca (ADR-0002); put americana -> fora,
  motivo "put americana não suportada (ADR-0002)".

### 3.2 Tabela de custos versionada (adapter de configuração)
- `src/options_engine/adapters/outbound/data/cost_schedules.csv` empacotado (mesmo
  padrão do `b3_holidays.csv`), com loader `StaticCostScheduleTable` e seleção da
  tabela vigente por data numa função pura do domínio (`schedule_on(schedules, d)`:
  a de maior `valid_from <= d`; nenhuma -> erro de domínio claro).
- Linha inicial **[mesa]**: emolumentos de opções 0,001340; à vista/exercício
  0,000300; corretagem por ordem 0,00; corretagem de exercício 0,00; IR 0,15;
  `valid_from = 2025-08-01` (OC 025/2025-VPC: nova tarifação do à vista desde
  01/08/2025 sem mudança em derivativos; página de opções consultada em 26/10/2026)
  — documente a origem de cada número no próprio CSV (coluna `fonte`) ou ao lado.

### 3.3 `RankIncomeOpportunitiesService` (application)
- Contrato inbound `RankIncomeOpportunitiesUseCase` + `RankIncomeCommand` em
  `application/ports/inbound.py`; implementação em
  `application/use_cases/rank_income.py`; tipos de resultado como VOs do domínio
  (`domain/income/ranking.py`), sem lógica na apresentação.
- Command: `underlyings: tuple[str, ...]` (lista do usuário **[mesa]**);
  `structures: frozenset[IncomeStructure]` (default as três); `delta_min = 0.15`,
  `delta_max = 0.35` (módulo) **[mesa]**; `expiries = 2` (os N próximos vencimentos
  com du >= 0) **[mesa]**; `min_trades: int | None = None` e
  `max_spread_pct: float | None = None` (sem filtro padrão **[mesa]**);
  `sort_by` = enum, default rendimento anualizado LÍQUIDO **[mesa]**;
  `reference_shares = 100` **[mesa]**; `spread_width_steps = 1` (técnico: a perna
  comprada da trava é o k-ésimo strike seguinte mais fora do dinheiro, mesmo tipo e
  vencimento).
- Construtor: `OptionChainPort`, `TradingCalendar`, `PricingModel`, tabelas de custo
  (sequência de `CostSchedule`), `valuation_timezone`, `day_count = BUSINESS_252`.
  Data de valoração = data do pregão da cadeia (timestamp do snapshot no fuso de
  valoração), não o relógio.
- Estruturas: put coberta (put vendida no delta), venda coberta (call vendida no
  delta; base = spot), trava de crédito com put (bull put) e com call (bear call):
  perna vendida no delta, comprada `spread_width_steps` strikes mais fora do
  dinheiro, montada com `vertical_spread` e prêmios por lado (`executable_premium`;
  TEÓRICO quando elegível).
- Qualidade da estrutura = pior entre as pernas. **Ranking só com EXECUTAVEL**,
  ordenado pelo critério (None por último, desempate determinístico por ativo,
  estrutura, vencimento, strikes). INDICATIVO e TEORICO saem numa lista de
  referência, rotulados; nunca no ranking.
- Exclusões sempre com motivo (`Exclusion(scope, symbol, reason)`): ativo
  desconhecido; ativo indisponível (mensagem do `UnderlyingUnavailableError`);
  `rejected_series` do adapter; put americana; sem delta; fora da faixa de delta não
  é exclusão (é filtro; não polua a lista); filtros de liquidez; dado inconsistente
  vindo das métricas (`InvalidDomainValueError`, ex.: crédito >= largura) ;
  perna sem preço.
- Liquidez exibida: negócios, volume financeiro, spread % = (ask - bid)/mid quando
  houver book completo.
- Testes com fake em memória do `OptionChainPort` (em `tests/`), cobrindo os casos
  positivos/negativos/borda do ROADMAP (vencimento hoje, só bid na perna comprada,
  crédito >= largura, IV sem convergência, subjacente sem preço etc.), ordenação e
  determinismo.

## 4. Trilha C — painel HTML e CLI (branch `feat/painel-html`, sobre a trilha B)

- Adapter de apresentação em `src/options_engine/adapters/inbound/html_report.py`
  (ou pacote), só stdlib: consome o resultado do use case; nenhuma regra de negócio.
  `html.escape` em TODO texto vindo de dados; CSS inline; sem JavaScript.
- Conversões de exibição só aqui (decisão nº 8): percentuais em pt-BR (vírgula
  decimal), moeda com 2 casas, du inteiros.
- Seções: cabeçalho (pregão, CDI usado, tabela de custos usada e sua vigência,
  parâmetros do comando); ranking EXECUTAVEL por critério; referências
  INDICATIVO/TEORICO rotuladas; exclusões com motivo; notas (IR é estimativa, N(d2)
  é probabilidade risco-neutra, marca de aproximação americana, "sem ofertas").
- Colunas: ativo, estrutura, série(s), vencimento, du, prêmio + qualidade,
  rendimento no período bruto/líquido, anualizado bruto/líquido, excesso sobre o
  CDI, retorno sobre risco (travas), proteção (venda coberta), breakeven
  bruto/líquido, ganho e perda máximos bruto/líquido, delta, N(d2), IV, vol
  realizada, negócios, volume, spread %, marcas.
- **Gráfico de payoff por oportunidade** (pedido do autor, 2026-10-27): SVG
  inline gerado em Python (stdlib, sem JavaScript, sem lib de gráfico), um por
  linha do ranking, num bloco recolhível (`<details>`). Curvas: payoff BRUTO no
  vencimento e resultado LÍQUIDO (montagem, exercício e IR do cenário, mesmo
  modelo de `domain/income/`). Marcas: spot atual, strikes, breakeven bruto e
  líquido, ganho e perda máximos. Eixo x de 0,5 a 1,5 x spot (ou da grade
  usada no ranking). Os pontos vêm do domínio (`payoff_profile`/`pnl_curve`
  e uma função pura nova de resultado líquido por preço, testada contra o
  oráculo de `tests/income/test_net_profile.py`); o adapter só desenha.
  Cores e rótulos acessíveis (`<title>` no SVG), coordenadas arredondadas
  para manter a saída determinística.
- Saída determinística: mesma entrada => bytes idênticos (sem "gerado em" com
  relógio; se quiser data de geração, só se passada explicitamente).
- CLI (`__main__.py`, `argparse`): `python -m options_engine [seed]` continua
  rodando o smoke (compatibilidade, testes existentes); novo subcomando
  `python -m options_engine painel --pregao 2026-10-23 --cotahist ARQ [ARQ ...]
  --cadastro CSV --ativos PETR4,VALE3 --saida painel.html [--cdi 0.15]
  [--delta-min ...] [--delta-max ...] [--vencimentos N] [--min-negocios N]
  [--spread-max PCT] [--ordenar CRITERIO] [--acoes 100] [--cache ARQ]`.
  Erros de arquivo (`CotahistFormatError`, arquivo ausente) -> mensagem clara e
  código de saída != 0, sem traceback.
- Composition root: função `build_income_panel(...)` em `config/composition.py`
  (wiring manual, mesma disciplina).
- Testes: HTML idêntico em duas execuções para a fixture (gráficos incluídos);
  SVG de payoff com breakevens nas posições certas; escape de texto
  malicioso; e2e do subcomando com `tmp_path`; smoke antigo intacto.

# Semana 4, parte 2: IR mensal das opções — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a Carteira ganha a aba **IR mensal**: o IR estimado das opções do perfil, mês a mês, com day trade, prejuízo compensado por categoria, DARF mínimo de R$ 10 e o prazo de pagamento.

**Architecture:** regras puras no domínio (`domain/portfolio/income_tax.py`): primeiro as peças de resultado por série (day trade separado do comum), depois os meses (compensação, alíquotas, mínimo). O `PortfolioService` lê as operações do perfil, chama o domínio e põe o "pagar até" pelo `TradingCalendar`. Uma rota `GET /api/carteira/ir-mensal` e um componente React na terceira aba da Carteira.

**Tech Stack:** Python 3.12 (stdlib no domínio e na aplicação), FastAPI + pydantic no adaptador, pytest + hypothesis; React + TypeScript, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-03-semana-4-instalador-ir-alertas-design.md` §3 (regras em §3.1–3.3, tela em §3.4) e §6 critério 2.

## Global Constraints

- Sem passos de commit: as mudanças ficam no working tree (CLAUDE.md do autor). Nada de `git commit`, `git stash` nem `git push`.
- Só opções; a perna de ação fica fora. Sem isenção, sem IR retido na fonte, sem prejuízo de antes do app (§3.1).
- Operação comum a **15%**, day trade a **20%**; prejuízo compensado **dentro de cada categoria**, de um mês para os seguintes (§3.1).
- Day trade: compra e venda da mesma série no mesmo dia, pela data dos eventos; a quantidade casada é o menor entre o comprado e o vendido no dia, pelos preços médios do dia (§3.3 item 1).
- Preço médio **por série no perfil**: as pernas da mesma série em operações diferentes entram juntas (§3.3).
- Custos dentro do preço: compra soma o custo, venda desconta; custos reais do evento, senão os da tabela, pela mesma função que a Carteira usa. Pó realiza o preço médio inteiro, sem custo próprio. Exercício e atribuição não geram resultado; viram uma nota no mês (§3.2, §3.3).
- DARF mínimo de **R$ 10**: IR do mês arredondado a centavos; abaixo de R$ 10 soma nos meses seguintes; prejuízo posterior não abate IR já devido (§3.3 item 2).
- "Pagar até": último dia útil do mês seguinte pelo `TradingCalendar`; fora da cobertura, `None` / "—" (§3.3 item 3).
- Rótulo fixo na tela: "Estimativa, só opções, sem IR retido na fonte e sem prejuízo de antes do app." (§3.4).
- Domínio e aplicação só stdlib (import-linter). Somas com `math.fsum`. Nomes e mensagens em pt-BR como o código ao redor; identificadores públicos em inglês como no resto do domínio.
- Gates: `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `pytest` (cobertura mínima do projeto); frontend `npm run verificar` e `npm run build`.

## Review Focus

1. **Venda no mesmo dia em que abriu, com sobra** (o caso da mãe: vende 200 calls e recompra 100 no mesmo dia): 100 em day trade, 100 na posição comum pelo preço da venda do dia — pinado em `test_venda_e_recompra_parcial_no_mesmo_dia` (Task 1).
2. **Custos sem digitar** (o caso mais comum: `costs=None`): o resultado sai com os custos da tabela, igual ao realizado da Carteira — `test_custos_da_tabela_quando_nao_digitados` (Task 1).
3. **Mês só com prejuízo depois de um IR pequeno pendente**: o IR pendente não some — `test_prejuizo_depois_nao_apaga_ir_pendente` (Task 2).
4. **Perfil sem nenhuma opção encerrada** (o estado de quem acabou de instalar): a aba diz que não há nada ainda, sem tabela vazia nem erro — `test_sem_meses_mostra_o_vazio` (Task 4).
5. **Arquivo de operação ilegível na pasta**: a aba abre com o que dá para ler (os ilegíveis já aparecem no topo da Carteira) — `test_ir_ignora_arquivo_ilegivel` (Task 3).

## Arquivos

- Create `src/options_engine/domain/portfolio/income_tax.py` — peças, notas de exercício e meses (Tasks 1–2).
- Modify `src/options_engine/domain/portfolio/positions.py` — `_custo` vira a pública `event_costs` (Task 1).
- Create `tests/portfolio/test_income_tax_pecas.py`, `tests/portfolio/test_income_tax_meses.py`.
- Modify `src/options_engine/application/ports/portfolio.py`, `src/options_engine/application/use_cases/portfolio.py`, `src/options_engine/adapters/inbound/web/portfolio.py` (Task 3).
- Create `tests/application/test_portfolio_ir.py`; modify `tests/web/test_portfolio_api.py` (Task 3).
- Modify `frontend/src/api/carteira.ts`, `frontend/src/formatacao.ts`, `frontend/src/paginas/Carteira.tsx`, `frontend/src/aprender/glossario.ts`, `frontend/src/aprender/Telas.tsx`, `frontend/src/aprender/Termos.test.tsx`; create `frontend/src/componentes/IrMensal.tsx` e `IrMensal.test.tsx`; fixture em `frontend/src/testes/carteira.ts` (Task 4).

---

### Task 1: Peças de resultado por série

**Files:**
- Create: `src/options_engine/domain/portfolio/income_tax.py`
- Modify: `src/options_engine/domain/portfolio/positions.py` (renomear `_custo` → `event_costs`, pôr em `__all__`, manter o uso em `realized_result`)
- Test: `tests/portfolio/test_income_tax_pecas.py`

**Interfaces:**
- Consumes: `Operation`, `Open`, `Close`, `Exercise`, `Assignment`, `Expired`, `OptionLegRef`, `leg_states` (`domain/portfolio/model.py`); `event_costs(event: Event, ref: LegRef, schedules: Sequence[CostSchedule]) -> float` (positions.py, o antigo `_custo`, mesma lógica).
- Produces (usados nas Tasks 2–3):

```python
class TaxCategory(StrEnum):
    COMMON = "comum"
    DAY_TRADE = "day_trade"

class PieceKind(StrEnum):
    CLOSE = "encerramento"
    EXPIRED = "po"

@dataclass(frozen=True, slots=True)
class TaxPiece:
    on: date
    symbol: str
    category: TaxCategory
    kind: PieceKind
    result: float                  # em R$, já com os custos
    operations: tuple[str, ...]    # nomes das operações envolvidas, ordem de aparição, sem repetir

@dataclass(frozen=True, slots=True)
class ExerciseNote:
    on: date
    symbol: str
    operation: str                 # nome da operação

@dataclass(frozen=True, slots=True)
class TaxRecords:
    pieces: tuple[TaxPiece, ...]       # ordenadas por (on, symbol, category)
    exercises: tuple[ExerciseNote, ...]  # ordenadas por (on, symbol)

def tax_records(operations: Sequence[Operation], schedules: Sequence[CostSchedule]) -> TaxRecords: ...
```

**Algoritmo** (o que os testes não determinam sozinhos):

1. Para cada operação e cada perna de **opção**, refaça os eventos em ordem (como `leg_states`) para saber, em cada evento, o lado da posição: `Open` compra ou vende pelo `side`; `Close` vai no sentido oposto ao lado da posição naquele momento; `Expired` leva a quantidade aberta naquele momento; `Exercise`/`Assignment` levam a quantidade deles. Pernas de ação são ignoradas.
2. Junte os movimentos de todas as operações por `symbol`; dentro da série, agrupe por data (ordem crescente; empate na ordem das operações recebidas e dos eventos).
3. Em cada dia: compras = `Open` BUY e `Close` de posição vendida; vendas = `Open` SELL e `Close` de posição comprada. Valor da compra = `q·p + custo`; valor da venda = `q·p − custo`, com `custo = event_costs(...)`. `B`, `S` = quantidades; `DT = min(B, S)`. Se `DT > 0`: peça `DAY_TRADE`, kind `CLOSE`, `result = DT·(médio_venda_dia − médio_compra_dia)`. A sobra (`|B − S|`, ao médio do lado que sobrou) entra na posição comum da série: no mesmo sentido (ou sem posição) recalcula o preço médio; no sentido oposto encerra até a quantidade aberta — peça `COMMON`, kind `CLOSE`, `result = q·(venda − médio)` para comprada, `q·(médio − compra)` para vendida — e o que passar abre o lado oposto a esse preço.
4. Depois das negociações do dia, os outros eventos do dia, em ordem: `Expired` encerra a quantidade dele a preço zero, sem custo, sem day trade (peça `COMMON`, kind `EXPIRED`); `Exercise`/`Assignment` tiram a quantidade da posição sem resultado e geram `ExerciseNote`.
5. `operations` da peça: os nomes das operações com movimento que entrou nela (no dia, para `CLOSE`; a do evento, para `EXPIRED`).

- [ ] **Step 1: Escrever os testes que falham** em `tests/portfolio/test_income_tax_pecas.py`, com as pernas dos builders (`call(30.0)` = PETRK300, `call(32.0)` = PETRK320, `put(28.0)` = PETRW280) e `operacao(...)` de `tests/portfolio/_builders.py`; custos explícitos salvo onde dito; comparar com `pytest.approx`:

```python
OUT1, OUT15 = date(2026, 10, 1), date(2026, 10, 15)
NOV3, NOV12, NOV19 = date(2026, 11, 3), date(2026, 11, 12), date(2026, 11, 19)

def test_day_trade_parcial_separa_o_casado_do_resto():
    # compra 200 a 1,00 (custo 2,00) e vende 100 a 1,30 (custo 1,00) no mesmo dia; vende o resto a 0,50 (custo 1,00)
    op = operacao([call(30.0)], [Open(0, OUT1, Side.BUY, 200, 1.00, 2.00),
                                  Close(0, OUT1, 100, 1.30, 1.00), Close(0, OUT15, 100, 0.50, 1.00)],
                  nome="call de outubro")
    r = tax_records([op], [])
    assert [(p.on, p.category, p.kind, p.result) for p in r.pieces] == [
        (OUT1, TaxCategory.DAY_TRADE, PieceKind.CLOSE, approx(28.00)),
        (OUT15, TaxCategory.COMMON, PieceKind.CLOSE, approx(-52.00)),
    ]
    assert r.pieces[0].operations == ("call de outubro",)

def test_venda_e_recompra_parcial_no_mesmo_dia():
    # vende 200 a 1,00 e recompra 100 a 0,70 no mesmo dia (custo 0); recompra o resto a 0,40 noutro dia
    op = operacao([call(30.0)], [Open(0, NOV3, Side.SELL, 200, 1.00, 0.0),
                                  Close(0, NOV3, 100, 0.70, 0.0), Close(0, NOV12, 100, 0.40, 0.0)])
    assert [(p.category, p.result) for p in tax_records([op], []).pieces] == [
        (TaxCategory.DAY_TRADE, approx(30.00)), (TaxCategory.COMMON, approx(60.00))]

def test_po_da_vendida_realiza_o_premio_liquido_como_comum():
    op = operacao([put(28.0)], [Open(0, NOV3, Side.SELL, 200, 0.80, 2.00),
                                 Close(0, NOV12, 100, 0.20, 1.00), Expired(0, NOV19)], nome="venda de put")
    assert [(p.on, p.kind, p.result) for p in tax_records([op], []).pieces] == [
        (NOV12, PieceKind.CLOSE, approx(58.00)), (NOV19, PieceKind.EXPIRED, approx(79.00))]

def test_po_da_comprada_realiza_a_perda():
    op = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 0.50, 1.00), Expired(0, NOV19)])
    assert [p.result for p in tax_records([op], []).pieces] == [approx(-51.00)]

def test_exercicio_e_atribuicao_nao_geram_resultado_e_viram_nota():
    exercida = operacao([call(32.0)], [Open(0, NOV3, Side.BUY, 100, 0.40, 1.00),
                                        Exercise(0, NOV19, 100, 0.0)], nome="call exercida")
    atribuida = operacao([put(28.0)], [Open(0, NOV3, Side.SELL, 100, 0.60, 1.00),
                                        Assignment(0, NOV19, 100, 0.0)], id_="op2", nome="put atribuída")
    r = tax_records([exercida, atribuida], [])
    assert r.pieces == ()
    assert r.exercises == (ExerciseNote(NOV19, "PETRK320", "call exercida"),
                           ExerciseNote(NOV19, "PETRW280", "put atribuída"))

def test_virada_de_lado_no_mesmo_dia():
    # compra 100 a 1,00, vende 100 a 1,20 e vende mais 100 a 1,30 no mesmo dia; recompra 100 a 1,00 no outro
    op = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 1.00, 0.0), Close(0, NOV3, 100, 1.20, 0.0),
                                  Open(0, NOV3, Side.SELL, 100, 1.30, 0.0), Close(0, NOV12, 100, 1.00, 0.0)])
    assert [(p.category, p.result) for p in tax_records([op], []).pieces] == [
        (TaxCategory.DAY_TRADE, approx(25.00)), (TaxCategory.COMMON, approx(25.00))]

def test_mesma_serie_em_duas_operacoes_no_mesmo_dia_e_day_trade():
    x = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 1.00, 0.0)], id_="x", nome="x")
    y = operacao([call(30.0)], [Open(0, NOV3, Side.SELL, 100, 1.20, 0.0)], id_="y", nome="y")
    (peca,) = tax_records([x, y], []).pieces
    assert (peca.category, peca.result, peca.operations) == (TaxCategory.DAY_TRADE, approx(20.00), ("x", "y"))

def test_preco_medio_por_serie_junta_as_operacoes():
    x = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 1.00, 0.0),
                                 Close(0, NOV19, 100, 2.50, 0.0)], id_="x", nome="x")
    y = operacao([call(30.0)], [Open(0, NOV12, Side.BUY, 100, 2.00, 0.0)], id_="y", nome="y")
    assert [p.result for p in tax_records([x, y], []).pieces] == [approx(100.00)]  # médio 1,50, não 1,00

def test_acao_fica_de_fora():
    op = operacao([acao()], [Open(0, NOV3, Side.BUY, 100, 30.0, 0.0), Close(0, NOV12, 100, 32.0, 0.0)])
    assert tax_records([op], []) == TaxRecords((), ())

def test_custos_da_tabela_quando_nao_digitados():
    tabela = [make_cost_schedule()]
    op = operacao([call(30.0)], [Open(0, NOV3, Side.BUY, 100, 1.00), Close(0, NOV12, 100, 1.50)])
    (peca,) = tax_records([op], tabela).pieces
    assert peca.result == approx(realized_result(op, tabela))
```

E um teste de propriedade com hypothesis, `test_soma_das_pecas_bate_com_o_realizado_da_carteira`: operações só com pernas de opção, cada perna aberta em 1 a 3 `Open` do mesmo lado e zerada por `Close` em partes e/ou um `Expired` final, datas não decrescentes num intervalo de poucos dias (para gerar day trade), custos explícitos em `[0, 5]`; `fsum(p.result for p in pieces) == approx(fsum(realized_result(o, []) for o in ops), abs=1e-6)`.

- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/portfolio/test_income_tax_pecas.py -q` → falha de import (`income_tax` não existe).
- [ ] **Step 3: Implementar** `income_tax.py` (tipos e `tax_records`) e o `event_costs` público em `positions.py`. Docstring do módulo no estilo de `model.py`: regras e a IN RFB 1.585/2015.
- [ ] **Step 4: Rodar e ver passar** — `pytest tests/portfolio -q` → tudo verde (os testes da Carteira continuam passando com o `event_costs`).

---

### Task 2: Meses, compensação e DARF mínimo

**Files:**
- Modify: `src/options_engine/domain/portfolio/income_tax.py`
- Test: `tests/portfolio/test_income_tax_meses.py`

**Interfaces:**
- Consumes: `TaxRecords`, `TaxPiece`, `ExerciseNote`, `TaxCategory`, `PieceKind` (Task 1).
- Produces (Task 3):

```python
COMMON_RATE: Final[float] = 0.15
DAY_TRADE_RATE: Final[float] = 0.20
DARF_MINIMUM: Final[float] = 10.0

@dataclass(frozen=True, slots=True)
class TaxMonth:
    month: date                # dia 1 do mês
    common_result: float
    day_trade_result: float
    common_base: float         # resultado positivo menos o prejuízo comum usado
    day_trade_base: float
    common_loss: float         # prejuízo comum que sobra para os meses seguintes (>= 0)
    day_trade_loss: float
    tax: float                 # IR do próprio mês: round(15% base comum, 2) + round(20% base DT, 2)
    carried_in: float          # IR abaixo de R$ 10 que veio dos meses anteriores
    due: float                 # a pagar neste mês: round(tax + carried_in, 2) se >= 10, senão 0
    carried_out: float         # o que fica para o próximo: round(tax + carried_in, 2) se < 10, senão 0
    pieces: tuple[TaxPiece, ...]
    exercises: tuple[ExerciseNote, ...]

def monthly_tax(records: TaxRecords) -> tuple[TaxMonth, ...]: ...  # meses em ordem crescente
```

Só aparecem os meses com alguma peça ou nota; a compensação e o IR pendente atravessam os meses vazios.

- [ ] **Step 1: Escrever os testes que falham**, com `TaxRecords` montados à mão (helper local `peca(dia, categoria, resultado)`):
  - `test_mes_com_day_trade_abaixo_do_minimo_fica_para_depois`: outubro com comum −52,00 e DT +28,00 → `common_base 0`, `day_trade_base 28.00`, `common_loss 52.00`, `tax 5.60`, `due 0`, `carried_out 5.60`.
  - `test_prejuizo_comum_abate_o_mes_seguinte_e_o_ir_pendente_soma`: o outubro acima + novembro com comum +137,00 → novembro `common_base 85.00`, `common_loss 0`, `tax 12.75`, `carried_in 5.60`, `due 18.35`, `carried_out 0`.
  - `test_prejuizo_de_day_trade_nao_abate_comum`: mês 1 DT −100,00; mês 2 comum +100,00 → mês 2 `common_base 100.00`, `tax 15.00`, `day_trade_loss 100.00`.
  - `test_prejuizo_comum_nao_abate_day_trade`: mês 1 comum −100,00; mês 2 DT +100,00 → mês 2 `day_trade_base 100.00`, `tax 20.00`, `common_loss 100.00`.
  - `test_prejuizo_depois_nao_apaga_ir_pendente`: mês 1 comum +40,00 (`tax 6.00`, `carried_out 6.00`); mês 2 comum −100,00 → `tax 0`, `carried_in 6.00`, `due 0`, `carried_out 6.00`, `common_loss 100.00`.
  - `test_ir_de_exatamente_dez_paga`: DT +50,00 → `tax 10.00`, `due 10.00`, `carried_out 0`.
  - `test_mes_so_com_exercicio_aparece_com_a_nota`: só uma `ExerciseNote` em novembro → um mês com resultados e IR zerados e a nota em `exercises`.
  - `test_meses_sem_nada_nao_aparecem`: peças em outubro (comum −30,00) e dezembro (comum +130,00) → dois meses; dezembro com `common_base 100.00`.
  - `test_sem_registros_sem_meses`: `monthly_tax(TaxRecords((), ())) == ()`.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/portfolio/test_income_tax_meses.py -q`.
- [ ] **Step 3: Implementar** as constantes, `TaxMonth` e `monthly_tax`.
- [ ] **Step 4: Rodar e ver passar** — `pytest tests/portfolio -q`.

---

### Task 3: Serviço e rota `GET /api/carteira/ir-mensal`

**Files:**
- Modify: `src/options_engine/application/ports/portfolio.py`, `src/options_engine/application/use_cases/portfolio.py`, `src/options_engine/adapters/inbound/web/portfolio.py`
- Test: create `tests/application/test_portfolio_ir.py`; modify `tests/web/test_portfolio_api.py`

**Interfaces:**
- Consumes: `tax_records`, `monthly_tax`, `TaxMonth` (Tasks 1–2); `TradingCalendar.business_days_between` (já injetado no `PortfolioService`).
- Produces (Task 4 consome o JSON):

```python
# ports/portfolio.py
@dataclass(frozen=True, slots=True)
class TaxMonthView:
    month: TaxMonth
    pay_by: date | None        # só quando month.due > 0; None também fora da cobertura do calendário

# PortfolioUseCase (Protocol) e PortfolioService
def income_tax(self) -> tuple[TaxMonthView, ...]: ...   # meses em ordem crescente, como o domínio
```

O último dia útil de um mês: do último dia do mês para trás, o primeiro `d` com `business_days_between(d, d + 1 dia) == 1`; `InvalidDomainValueError` (fora da cobertura) → `None`. Arquivos ilegíveis do repositório ficam de fora, como no resto do serviço (`_operacoes`).

JSON da rota (lista, **mês mais recente primeiro**):

```
MesIrOut: mes ("2026-10"), comum, day_trade, base_comum, base_day_trade, prejuizo_comum,
          prejuizo_day_trade, ir_do_mes, ir_de_antes, ir_a_pagar, ir_para_depois,
          pagar_ate (date | null), pecas: list[PecaIrOut], exercicios: list[ExercicioIrOut]
PecaIrOut: data, ticker, categoria ("comum" | "day_trade"), tipo ("encerramento" | "po"),
           resultado, operacoes: list[str]
ExercicioIrOut: data, ticker, operacao
```

- [ ] **Step 1: Escrever os testes que falham.**
  - `tests/application/test_portfolio_ir.py::test_dois_meses_conferidos_a_mao` (critério 2 do §6): `FakeOperationRepository` com as operações do exemplo — "call de outubro" (o cenário de `test_day_trade_parcial_separa_o_casado_do_resto`), "venda de put" (o de `test_po_da_vendida_realiza_o_premio_liquido_como_comum`) e "call exercida" (Open BUY 100 a 0,40 com custo 1,00 em 03/11, `Exercise` de 100 em 19/11) — e o calendário empacotado (`StaticHolidayCalendar.from_packaged_data()`). Esperado: outubro `comum -52.00`, `day_trade 28.00`, `tax 5.60`, `due 0`, `carried_out 5.60`, `pay_by None`; novembro `comum 137.00`, `common_base 85.00`, `tax 12.75`, `carried_in 5.60`, `due 18.35`, `pay_by date(2026, 12, 30)` (31/12 é feriado na B3), uma nota de exercício de PETRK320.
  - `test_ir_ignora_arquivo_ilegivel`: repositório com um `UnreadableFile` e a "venda de put" → um mês, sem erro.
  - `test_pagar_ate_fora_da_cobertura_e_none`: um mês com `due > 0` em dezembro de 2027 (o mês seguinte sai da cobertura, que vai até 31/12/2027) → `pay_by None`.
  - `tests/web/test_portfolio_api.py::test_ir_mensal_mais_recente_primeiro`: grava a "venda de put" pelo `JsonOperationRepository` da pasta do perfil e chama `GET /api/carteira/ir-mensal` → 200; `[m["mes"] for m in corpo] == ["2026-11"]`; `corpo[0]["ir_do_mes"] == approx(20.55)`, `corpo[0]["pecas"][1] == {"data": "2026-11-19", "ticker": "PETRW280", "categoria": "comum", "tipo": "po", "resultado": approx(79.0), "operacoes": ["venda de put"]}`; e `test_ir_mensal_sem_perfil` com o mesmo status e a mesma forma de erro que `GET /api/carteira` sem perfil aberto.
- [ ] **Step 2: Rodar e ver falhar** — `pytest tests/application/test_portfolio_ir.py tests/web/test_portfolio_api.py -q`.
- [ ] **Step 3: Implementar** `TaxMonthView`, o método no Protocol e no `PortfolioService`, e a rota com os modelos pydantic no estilo dos outros de `portfolio.py`.
- [ ] **Step 4: Rodar e ver passar** — `pytest -q` inteiro e `lint-imports`.

---

### Task 4: Aba IR mensal na Carteira

**Files:**
- Modify: `frontend/src/api/carteira.ts`, `frontend/src/formatacao.ts` (+ `formatacao.test.ts`), `frontend/src/paginas/Carteira.tsx` (+ `Carteira.test.tsx`), `frontend/src/aprender/glossario.ts`, `frontend/src/aprender/Termos.test.tsx` (`"ir-mensal"` em `IDS`), `frontend/src/aprender/Telas.tsx`, `frontend/src/testes/carteira.ts`
- Create: `frontend/src/componentes/IrMensal.tsx`, `frontend/src/componentes/IrMensal.test.tsx`

**Interfaces:**
- Consumes: o JSON da Task 3.
- Produces: tipos `MesIr`, `PecaIr`, `ExercicioIr` e `lerIrMensal(): Promise<MesIr[]>` em `api/carteira.ts`; `formatarMes("2026-10") === "out/2026"`; `<IrMensal />` sem props.

**Tela:**
- Acima da tabela: "Estimativa, só opções, sem IR retido na fonte e sem prejuízo de antes do app." e `<Ajuda id="ir-mensal" />`.
- Colunas: **Mês** | **Comum** | **Day trade** | **Prejuízo a compensar** | **IR do mês** | **A pagar**.
  - Prejuízo a compensar: uma linha "comum R$ x" e/ou "day trade R$ y", só as diferentes de zero; "—" se as duas forem zero.
  - A pagar: `ir_a_pagar > 0` → "R$ 18,35 até 30/12/2026" (sem `pagar_ate`: só o valor); `ir_a_pagar == 0` e `ir_para_depois > 0` → "abaixo de R$ 10: soma no mês seguinte"; senão "—".
- O mês abre como as operações da aba Abertas (botão ▸/▾ com `aria-expanded`) e mostra: "Base: comum R$ 85,00 (15%) · day trade R$ 0,00 (20%)"; quando `ir_de_antes > 0`, "IR do mês R$ 12,75 + R$ 5,60 de meses anteriores = R$ 18,35"; a tabela das peças (Data | Série | Operação | Tipo: "Encerramento"/"Pó" | Categoria: "Comum"/"Day trade" | Resultado); e, para cada exercício, "Exercício ou atribuição de PETRK320 (call exercida) em 19/11/2026: o prêmio vai para o preço da ação e só conta quando a ação for vendida, fora desta conta."
- Vazio: "Nenhuma opção encerrada ou virada pó neste perfil ainda." Erro: a mensagem do `ErroApi`, senão "Não foi possível calcular o IR mensal."
- Carteira: terceira aba "IR mensal" (`role="tab"`), monta `<IrMensal />` quando selecionada.

**Glossário** (`ir-mensal`, texto exato):
- titulo: `IR mensal`
- texto: `A estimativa do imposto de renda das suas opções, mês a mês. Entra o resultado de cada opção encerrada ou que virou [pó](po), já com os custos. Operação comum paga 15% e day trade (comprar e vender a mesma série no mesmo dia) paga 20%. O prejuízo de um mês abate o ganho dos meses seguintes, cada tipo com o seu. IR abaixo de R$ 10 não se paga na hora: soma no mês seguinte. O [exercício](exercicio) e a [atribuição](atribuicao) não entram: o prêmio vai para o preço da ação. É estimativa, não o cálculo do imposto: ficam de fora as ações, o IR retido na fonte e o prejuízo de antes do app.`
- exemplo: `Em outubro, um prejuízo comum de R$ 52,00 e um day trade de R$ 28,00 dão R$ 5,60 de IR, que fica para novembro. Em novembro, um ganho comum de R$ 137,00 menos os R$ 52,00 dá R$ 85,00 de base e R$ 12,75 de IR; com os R$ 5,60 de outubro, o DARF fica em R$ 18,35, até o último dia útil de dezembro.`
- onde: `Na Carteira, na aba IR mensal.`

**Telas** (card Carteira): acrescentar ao fim do texto: ` Na aba IR mensal, uma estimativa do [imposto das opções](ir-mensal) mês a mês, com o prazo do DARF.`

- [ ] **Step 1: Escrever os testes que falham** (`IrMensal.test.tsx`, com `simularFetch` e uma fixture `mesIr()` em `testes/carteira.ts` com os números de novembro do exemplo):
  - `test("mostra o rótulo de estimativa e um mês por linha, o mais recente primeiro")`.
  - `test("a pagar mostra o valor e o prazo")` → "R$ 18,35 até 30/12/2026".
  - `test("abaixo de R$ 10 diz que soma no mês seguinte")` (outubro).
  - `test("abrir o mês mostra a base, as peças e a nota de exercício")`.
  - `test("sem meses mostra o vazio")` e `test("erro da API aparece")`.
  - Em `Carteira.test.tsx`: `test("a aba IR mensal busca e mostra o IR")`.
  - Em `formatacao.test.ts`: `formatarMes("2026-10") === "out/2026"` e `formatarMes("2026-01") === "jan/2026"`.
- [ ] **Step 2: Rodar e ver falhar** — `npm --prefix frontend run test -- IrMensal Carteira formatacao Termos`.
- [ ] **Step 3: Implementar** os tipos, `lerIrMensal`, `formatarMes`, `IrMensal.tsx`, a aba, o termo e o texto da Telas. CSS: reaproveitar as classes que já existem (`tabela-operacoes`, `secundario`, `num`, `sinal(...)`); só criar classe nova se nenhuma servir.
- [ ] **Step 4: Rodar e ver passar** — `npm --prefix frontend run verificar` e `npm --prefix frontend run build`.

---

### Task 5: Conferência e documentação (controlador)

- [ ] Gates completos (Global Constraints) na branch inteira, com a saída.
- [ ] App real numa pasta temporária (HOME e perfil temporários, porta livre, sem a ponte): registrar pela API as três operações do exemplo da Task 3 e conferir que `GET /api/carteira/ir-mensal` dá os números de outubro e novembro; abrir a aba no navegador e ver a tela. **Nunca** gravar operação nos perfis reais do autor.
- [ ] README (linha de status), ROADMAP (parte 2 feita), HANDOFF (seção de 04/11, parte 2) e `docs/superpowers/ledger-semana-4.md` (decisões desta parte).

# Plano de Verificação & Validação (V&V)

**Projeto:** Options Analytics Engine (`black-scholes-pricer`)
**Status:** Aprovado — decisões de negócio ratificadas pela mesa em 2026-07-02
**Última verificação numérica:** 2026-07-02, Python 3.12.10 (stdlib only: `math.erf`/`log`/`sqrt`/`exp`), Windows 11

> **Pergunta central:** como garantir precisão milimétrica de cálculos em ponto flutuante **sem falsos positivos** (testes que quebram por ruído de float entre plataformas/libms) e **sem falsos negativos** (tolerâncias tão frouxas que bugs de fórmula passam)?
>
> **Resposta em uma linha:** tolerância é decisão de engenharia derivada da **fonte do oráculo** e da **física do erro numérico** — nunca um número mágico — e a força da suíte se mede por *mutation score*, não por cobertura.

---

## 1. Política de Tolerância

### 1.1 Princípios

1. **`==` entre floats é proibido em código de teste.** Motivos concretos:
   - Aritmética IEEE-754 não é associativa — reordenar `S·N(d1) − K·df·N(d2)` muda o último bit;
   - `math.erf`/`math.exp` diferem em ~1 ulp entre libms (UCRT/Windows no dev local vs glibc/Linux no CI) — igualdade exata **vai** flakar entre os dois ambientes;
   - Upgrades de CPython podem trocar a implementação de libm.

   Exceção única e documentada: ramos de fronteira que retornam forma fechada exata (ex.: `T == 0` → `max(S − K, 0.0)`), onde o caminho aritmético é idêntico ao do valor esperado.

2. **Semântica canônica: `math.isclose`** — `abs(a−b) <= max(rel_tol·max(|a|,|b|), abs_tol)`. É semântica OR: a tolerância relativa governa a escala normal, o **piso absoluto** resgata a vizinhança do zero. `pytest.approx` tem a mesma semântica, mas **nunca com defaults** (os defaults do pytest são frouxos demais para differential testing e o `abs` default pode mascarar erro em deep OTM). `numpy.isclose` tem semântica diferente (assimétrica, aditiva) — não misturar; como o core é stdlib, `math.isclose` é a definição oficial.

3. **Por que relativa sozinha falha:** o call DEEP_OTM do corpus (S=100, K=150, T=0.25) vale **0.000118** (verificado). O preço é computado como diferença de termos com erro absoluto intrínseco de cancelamento ~`eps·S ≈ 2e-14`; exigir `rel_tol=1e-9` sobre um valor de 1e-12 seria exigir erro absoluto 1e-21 — **fisicamente impossível em float64**. Logo: piso absoluto proporcional à escala do problema (`~1e-12 · max(S, K)`).

4. **Por que absoluta apertada contra livro falha:** valores de livro-texto são **arredondados**. Hull publica a centavos: nosso call full-precision é **4.759422**; o livro publica **4.76** → desvio de 5.8e-4. **Uma tolerância de 1e-4 contra o Hull reprovaria o próprio Hull.** Contra fonte de 2 casas, a única tolerância honesta é **5e-3** (metade da última casa publicada). A tolerância pertence ao oráculo, não à grandeza isolada.

5. **Codificação única:** a tabela §1.2 vive em `tests/_tolerances.py` como constantes nomeadas (como construído: `ABS_BOOK_2DP`, `ABS_BOOK_4DP`, `ABS_BOOK_GREEKS`, `REL_REGRESSION`, `REL_SELF`, `REL_MATH_IDENTITY`, `INEQ_SLACK`, `REL_FD` e o helper de piso `fd_abs_tol`), consumidas pelo assert canônico `assert_close(...)` do mesmo módulo. **Nenhum teste declara tolerância inline** — isso elimina o "afrouxei só nesse teste pra passar". Mudar tolerância = mudar a tabela = review explícito.

### 1.2 Tabela normativa

| Grandeza | `rel_tol` | Piso `abs_tol` | Contra qual oráculo | Racional |
|---|---|---|---|---|
| Preço — golden camada *published*, Hull (2 casas) | — | **5e-3** | Hull, valores publicados | metade da última casa publicada (evidência §2.1) |
| Preço — golden camada *published*, Haug (4 casas) | — | **5e-5** | Haug, valores publicados | idem, 4 casas (verificado: \|2.133368 − 2.1334\| = 3.2e-5 ✓) |
| Gregas — golden *published* (3–4 casas) | — | **5e-4** | Hull cap. de gregas | verificado: \|0.521602 − 0.522\| = 4.0e-4 ✓ |
| Preço/gregas — golden camada *verified* (full precision) | **1e-12** | 1e-12 · max(S,K) | valores recalculados desta sessão | mesma fórmula, aritmética independente — só ruído de ulp/reordenação |
| Preço — differential testing | **1e-9** | 1e-12 · max(S,K) | scipy (job de CI separado) | acumulação de ~ulps em erf/exp/log entre libms; margem ~1e4× sobre o ruído real |
| Auto-consistência (paridade put-call, linearidade de portfólio) | **1e-12** | 1e-12 · max(S,K) | a própria implementação | mesma aritmética, mesmo binário (verificado: paridade fecha em 7.1e-15) |
| Gregas 1ª ordem (Δ, vega, Θ, ρ) — analítica vs diferença finita central | **1e-6** | `fd_abs_tol` = 1e-8 + 16·eps·\|f\|/(2h) | cross-check interno (§5) | erro ótimo de FD central ~eps^(2/3) ≈ 4e-11; piso de roundoff dependente de escala (ver §5) |
| Gamma — vs 2ª diferença central | **1e-5** | 1e-7 · escala | idem | erro ótimo de 2ª diferença ~eps^(1/2) ≈ 1.5e-8 |
| Payoff no vencimento (só somas/máximos) | 1e-12 | 1e-12 | analítico manual | aritmética trivial, sem transcendentais |
| Breakevens do Iron Condor | 1e-12 | 1e-9 | forma fechada (`K2 − crédito líq.` / `K3 + crédito líq.`) | fórmula exata, sem transcendentais |
| Invariantes de desigualdade (bounds, monotonia) | — | folga **1e-9 · escala** | matemática | desigualdade estrita vira `>= −folga` para não flakar no limite |
| Volatilidade implícita — sigma recuperado (S5) | — | `iv_sigma_abs_tol` = 1e-11 + erro de preço / vega | ida e volta pelo kernel; scipy | cota do solver (`sigma_tol` = 1e-12) mais o erro do preço que originou a inversão, propagado pelo condicionamento |
| Volatilidade implícita — preço reavaliado, ida e volta pelo kernel (S5) | — | 1e-11 · max(S,K) | o próprio kernel | vega·\|Δsigma\| <= ~2.2e-12·escala; folga ~4× |
| Volatilidade implícita — preço reavaliado contra scipy (S5) | 1e-9 | `iv_roundtrip_price_abs_tol` = 16·eps·escala de cancelamento + vega·1e-11 | scipy | ruído em ulps do maior termo subtraído, não de max(S,K) (este piso chegava a 4× o preço com K ≫ S); medido: margem 28×, cota <= 1.1e-6 do preço |
| Métricas de renda — forma fechada (S5) | 1e-12 | 1e-12 | golden à mão | produtos, razões e fsum de poucos termos + uma potência por log1p/expm1 |
| Perfil líquido de renda — oráculo numérico (S5) | 1e-12 | 1e-12 · strike · ações | P&L avaliado perna a perna | somas ingênuas contra fsum; cancelamento perto do breakeven leva o erro absoluto do maior termo |

**Convenções de unidade fixadas antes de qualquer tolerância fazer sentido** (decisão ratificada nº 8): o kernel expõe gregas em unidades canônicas — vega por 1.00 de vol, Θ como ∂V/∂t **por ano calendário**, ρ por 1.00 de taxa, `q` decimal. Conversões de mercado (vega por ponto, Θ por dia útil ÷252) pertencem exclusivamente ao adapter de apresentação (Sprint 4) e têm testes próprios. Testar grega em unidade errada é a fonte nº 1 de "tolerância que não fecha".

---

## 2. Corpus Golden — verificado por máquina

### 2.1 Tabela de referência (Python 3.12.10 stdlib, 2026-07-02)

Todos os valores abaixo foram **recalculados nesta máquina** com `N(x) = 0.5·(1+erf(x/√2))`, sem dividendos (`q=0`), 6 casas decimais. Vega por 1.00 de vol; Θ da call por ano calendário; ρ da call por 1.00 de taxa.

| Caso | S | K | r | σ | T | Call | Put | Δ_call | Γ | Vega | Θ_call/ano | ρ_call |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| HULL (Ex. 15.6) | 42 | 40 | 0.10 | 0.20 | 0.5 | 4.759422 | 0.808599 | 0.779131 | 0.049963 | 8.813415 | −4.559092 | 13.982046 |
| ATM | 100 | 100 | 0.05 | 0.20 | 1.0 | 10.450584 | 5.573526 | 0.636831 | 0.018762 | 37.524035 | −6.414028 | 53.232482 |
| DEEP_OTM | 100 | 150 | 0.05 | 0.20 | 0.25 | 0.000118 | 48.136788 | 0.000052 | 0.000022 | 0.010751 | −0.004556 | 0.001278 |
| DEEP_ITM | 100 | 50 | 0.05 | 0.20 | 0.5 | 51.234505 | ~3.5e-7 | ~1.000000 | ~4.9e-8 | 0.000049 | −2.438284 | 24.382741 |
| NEAR_EXPIRY_ATM | 100 | 100 | 0.05 | 0.20 | 1/252 | 0.512549 | 0.492710 | 0.508795 | **0.316574** | 2.512489 | **−65.833081** | 0.199869 |
| HULL_GREGAS | 49 | 50 | 0.05 | 0.20 | 0.3846 | 2.400461 | 2.448147 | **0.521602** | — | — | — | — |
| HAUG (GBS) | 60 | 65 | 0.08 | 0.30 | 0.25 | **2.133368** | 5.846282 | — | — | — | — | — |

Verificações adicionais confirmadas:

- **Paridade put-call:** `max |C − P − (S − K·e^(−rT))|` = **7.1e-15** sobre todos os casos (nível de epsilon do float64, como esperado).
- **Γ e vega idênticos entre call e put** de mesmos parâmetros (forma fechada + confirmação por diferenças finitas independentes).
- **Explosão de Γ/Θ perto do vencimento:** Γ ATM salta ~17× de T=1 ano (0.018762) para T=1 dia útil (0.316574); Θ anual vai a −65.83. Evidência concreta para os guard clauses da tabela de fronteiras (§6).
- **Contra os livros:** HULL bate com o publicado (4.76 / 0.81) dentro de 5e-3; HULL_GREGAS Δ=0.521602 vs 0.522 publicado dentro de 5e-4; HAUG 2.133368 vs 2.1334 publicado dentro de 5e-5. **A política de tolerância da §1.2 se sustenta empiricamente contra as três fontes.**

### 2.2 Formato do arquivo golden

Os valores vivem em `tests/data/golden/bs_european.json` — **nunca hardcoded em asserts** — em **duas camadas por caso**:

- **`verified`** — valores full-precision recalculados (tabela acima, com mais casas), gerados por script stdlib **independente do kernel** (erf vs erfc, ordens de operação distintas) com cross-check contra a verificação de 6 casas da sessão de 2026-07-02. Testados com `REL_REGRESSION` (rel 1e-12, piso `ABS_REGRESSION_FLOOR·max(S,K)`): detecta qualquer regressão de fórmula ao nível de ulp.
- **`published`** — o valor do livro, com a fonte e o arredondamento. Testados com o `abs_tol` da fonte (5e-3 Hull, 5e-5 Haug, 5e-4 gregas): prova aderência à literatura.

Metadados obrigatórios por caso: `source` (livro/edição/exemplo), `rounding`, `verified_by`, `verified_on`, `verification_method`. O arquivo é **imutável por convenção**: corrigir um valor exige nova verificação, novo `verified_on` e justificativa no commit — proveniência é parte do teste.

---

## 3. Differential Testing (oráculo independente)

O core é stdlib-pura; o oráculo **não pode contaminar** o `pyproject.toml` do pacote.

- **Sprint 1 (todo PR):** job de CI `oracle` com ambiente próprio (`tests/oracle/requirements.txt`: scipy). Gera ~10.000 conjuntos de parâmetros pseudo-aleatórios **com seed fixa registrada** em domínio realista (`S ∈ [0.01, 1e6]`, `σ ∈ [1e-4, 5.0]`, `T ∈ [1/252, 30]`, `r ∈ [−0.05, 0.5]` — taxa negativa incluída de propósito: CDI não é negativo, mas o core não pode quebrar). Compara preço e gregas contra reimplementação com `scipy.stats.norm` (`tests/oracle/scipy_oracle.py`, seed fixa 20260702), com `REL_ORACLE` (1e-9) e piso `ABS_ORACLE_FLOOR·max(S,K)`. O arquivo não segue o padrão `test_*.py` de propósito — a coleta local o ignora e o job de CI o invoca por caminho explícito; o build local do dev sem scipy não é afetado.
- **Sprint 5 — volatilidade implícita:** no mesmo job, 10.000 preços gerados pelo oráculo em sigma são invertidos pelo kernel (`implied_vol`) e reavaliados pelo oráculo em sigma' (domínio identificável: \|ln(F/K)\| <= 3 desvios-padrão, vol total <= 3). Exige `CONVERGED` em todos, o preço reavaliado dentro de `iv_roundtrip_price_abs_tol` e sigma dentro de `iv_sigma_abs_tol`.
- **Hardening (pós-v1.0, agendado — não prometido sem slot):** QuantLib como segundo oráculo. scipy pega bug na nossa `N(x)`; QuantLib, estruturalmente independente, pega bug **na fórmula inteira** (erro copiado, não só digitado). São modos de falha diferentes.

---

## 4. Property-Based Testing (Hypothesis) — invariantes

Arquivos `test_pricing_properties.py` / `test_greeks_properties.py`. Folga `1e-9·escala` conforme §1.2.

**Preço:**

1. **Paridade put-call:** `C − P = S·e^(−qT) − K·e^(−rT)` (tol 1e-12 — auto-consistência; falha aqui = bug estrutural).
2. **Bounds:** `max(S·e^(−qT) − K·e^(−rT), 0) ≤ C ≤ S·e^(−qT)`; `max(K·e^(−rT) − S·e^(−qT), 0) ≤ P ≤ K·e^(−rT)`.
3. **Monotonia em S e σ:** C crescente em ambos; P decrescente em S, crescente em σ.
4. **Monotonia em T — só para a call com `q = 0` E `r ≥ 0`.** Sutileza dupla que separa suíte séria de decorativa: (a) para a **put** europeia a propriedade NÃO vale (deep ITM perde valor com T maior, pelo desconto do strike); (b) com **r < 0** a call deep ITM sofre o mesmo mecanismo e também pode perder valor com T. A estratégia Hypothesis restringe o domínio da propriedade e o comentário no teste documenta o porquê — este conhecimento de negócio fica codificado, não na cabeça de alguém.
5. **Monotonia em K:** call decrescente, put crescente.
6. **Convexidade em K:** butterfly `C(K−ΔK) − 2C(K) + C(K+ΔK) ≥ 0` (não-arbitragem).
7. **Homogeneidade de grau 1:** `BS(λS, λK, ...) = λ·BS(S, K, ...)` — pega erro de escala silencioso.
8. **Convergência T→0⁺:** `C → max(S−K, 0)` (testada como limite, com T decrescente).

**Gregas:**

9. `Δ_call ∈ (0, 1)`, `Δ_put ∈ (−1, 0)`; **paridade de delta:** `Δ_call − Δ_put = e^(−qT)`.
10. `Γ ≥ 0`; `vega ≥ 0`.
11. **Γ e vega idênticos para call e put** de mesmos parâmetros (tol 1e-12 — mesma expressão analítica).

**Estruturas (Sprint 2):**

12. Preço da estrutura = soma ponderada (`side` × `quantity`) dos preços das pernas (linearidade, tol 1e-12); `greeks(portfólio) = Σ qty·greeks(leg)` — incluindo ρ.
13. **`short == −long` ponto a ponto** — o anti-inversão-de-P&L, propriedade mais importante da Sprint 2.
14. Payoff do straddle no vencimento = `|S_T − K|`; Iron Condor com ganho e perda máximos limitados pelos strikes (bounds exatos).
15. **Breakevens do Iron Condor em forma fechada:** `K2 − crédito líquido` e `K3 + crédito líquido` — o `PayoffProfile.breakevens` é testado exatamente, não por interpolação.
16. **Vega do condor CONDICIONADO à direção** (decisão ratificada nº 3: a factory aceita ambas as direções): sob shift paralelo de vol, condor **vendido** (crédito) é não-crescente; condor **comprado** (débito) é não-decrescente; straddle comprado (long vega) não-decrescente. O teste lê a direção da estrutura — nunca a assume.
17. **Semântica separada por nome:** `payoff_at_expiry` (bruto, sem prêmio) e `pnl` (líquido do prêmio, quando informado — decisão ratificada nº 4: prêmio é opcional; sem prêmio, só o payoff bruto existe). Cada uma tem seus próprios testes; nenhum teste mistura as duas.

**Configuração Hypothesis** (perfis em `conftest.py`):

| Perfil | Exemplos | Modo | Uso |
|---|---|---|---|
| `dev` | 100 | aleatório | máquina local |
| `ci-pr` | 500 | **`derandomize=True`** | todo PR — PR não pode flakar por sorteio |
| `nightly` | 10.000 | aleatório, `print_blob=True` | agendado (fase de hardening) |

Todo exemplo que falhar no nightly é **promovido permanentemente a `@example(...)`** no teste — corpus de regressão explícito e versionado, em vez de depender do banco local do Hypothesis.

---

## 5. Gregas analíticas vs Diferenças Finitas — a escolha de `h`

A diferença central `(f(x+h) − f(x−h)) / 2h` tem dois erros competindo: **truncamento** `O(h²)` (cai com h menor) e **roundoff** `O(eps/h)` (explode com h menor, por cancelamento no numerador). O mínimo do erro total está em **`h* ≈ eps^(1/3) · escala`** (`eps = 2⁻⁵² ≈ 2.2e-16` ⇒ `eps^(1/3) ≈ 6e-6`).

**Curva em U medida nesta máquina** (Δ ATM, analítico = 0.636830651176):

| h/S | \|erro\| | Regime |
|---|---|---|
| 1e-2 | 8.6e-05 | truncamento domina |
| 1e-4 | 8.6e-09 | |
| **1e-6** | **6.1e-12** | **ótimo — eps^(1/3), como a teoria prevê** |
| 1e-8 | 2.5e-09 | roundoff entrando |
| 1e-11 | 3.2e-06 | cancelamento domina |

Escolher `h=1e-8` "porque é pequeno" é o erro clássico — **500× pior** que o ótimo. Daí `REL_FD = 1e-6` (constante em `tests/_tolerances.py`): margem ~10⁴× sobre o piso de 6e-12, porque `f'''` não é unitário perto de fronteiras.

- **Δ, vega, Θ, ρ:** 1ª diferença central com `h = FD_STEP·escala` (`FD_STEP = eps^(1/3)`) no respectivo parâmetro.
- **Γ:** rota implementada — diferença central **do Δ analítico** (mantém precisão eps^(2/3) e valida consistência Δ↔Γ); rota de sanidade opcional — 2ª diferença central do preço (`h* ≈ eps^(1/4)·escala`, erro ~eps^(1/2) ≈ 1.5e-8 ⇒ tolerância mais frouxa, 1e-5).
- Rodar FD sobre grid determinístico **e** sobre amostras Hypothesis **afastadas das fronteiras** — FD perto de T→0 diverge por construção, não por bug.

**Piso de roundoff dependente de escala (`fd_abs_tol`, descoberto empiricamente na Sprint 1):** a tolerância absoluta de cada comparação FD é `ABS_FD + 16·eps·|f|/(2h)`, onde `|f|` é a magnitude dos preços avaliados. Motivo medido nesta máquina: no canto deep ITM do grid (τ=0.1, σ=0.1), a grega vale ~1e-10 mas o preço vale ~25 — o numerador da FD subtrai dois valores de 25 que diferem menos de 1 ulp, e o ruído amplificado por 1/(2h) chega a ~1e-8, duas ordens acima da grega. Abaixo desse piso a FD é *fisicamente* incapaz de resolver a derivada: apertar a tolerância ali mede ruído, não corretude (9 falsos positivos na primeira execução da suíte, previstos pela curva em U e eliminados pelo piso — sem afrouxar nenhum caso onde a grega é relevante, pois lá o ramo relativo governa).

---

## 6. Casos de Fronteira — tabela normativa

Comportamento **definido em contrato, não emergente** (referência única para kernel, V&V e roadmap — resolve quem valida o quê):

| Entrada | Classificação | Quem trata | Comportamento contratado | Verificação |
|---|---|---|---|---|
| `S ≤ 0`, `K ≤ 0`, `σ < 0`, `T < 0` | Ilegal | VO rejeita na construção | Exceção tipada filha de `DomainError` (nunca `ValueError` cru) | teste negativo por invariante |
| `T = 0` exato | Limite legal | Kernel, ramo fechado | Preço = intrínseco; Δ = degrau; Γ/vega/Θ = 0 **por convenção documentada** | igualdade exata permitida (ramo fechado) |
| `T = 1e-10` | Legal | Kernel, fórmula normal | Contínuo com o ramo T=0; `math.isfinite` em todas as saídas | tol da tabela + isfinite |
| `σ = 0` exato | Limite legal | Kernel, ramo fechado | `C = e^(−rT)·max(F−K, 0)`, `F = S·e^((r−q)T)` | igualdade exata no ramo |
| `σ = 1e-8` | Legal | Kernel | Contínuo com o ramo σ=0 | tol absoluta |
| Deep OTM (`S/K = 0.1`) | Legal | Kernel | Preço ≥ 0, sem underflow para negativo; piso absoluto governa | `p ≥ 0.0` estrito + abs_tol |
| Deep ITM (`S/K = 10`) | Legal | Kernel | `C ≈ S·e^(−qT) − K·e^(−rT)`, `Δ → e^(−qT)` | tol relativa |
| `S = K` exato | Legal | Kernel | caminho sem surpresa de sinal em `log(1) = −0.0` | golden ATM §2.1 |
| `r = 0` e `r < 0` | Legal | Kernel | fórmula válida; paridade fecha | property tests |
| **Posição vencida dentro de um grid** | Legal (decisão ratificada nº 5) | Kernel/simulação | **Intrínseco descontado** — nunca erro, nunca célula nula | teste dedicado do grid |
| Overflow de produto intermediário (S ou K perto do máximo do float64) | Legal, irrepresentável | Kernel + VOs de resultado | Saída `inf`/NaN, nunca número finito inventado; `PricingResult`/`Greeks` rejeitam | teste dedicado |
| S e K em extremos opostos do float64 | Legal | Kernel, `implied_vol` | Saída ou exceção tipada — nunca `ValueError`/`ZeroDivisionError` cru | property test de magnitude extrema |
| CALL AMERICAN | Legal, aproximação (ADR-0002) | `supports()` + `price_many` | Preço europeu marcado; r contínua < 0 → `UnsupportedExerciseStyleError`; motor de simulação rejeita | testes dedicados + property `C >= S − K` |
| PUT AMERICAN | Legal no domínio, fora do modelo (decisão nº 2) | `supports()` no use case | `UnsupportedExerciseStyleError` — nunca preço silenciosamente errado | teste dedicado |

---

## 7. Determinismo — sem ele, simulação não é testável

- **Clock injetado** (`Clock.now() -> datetime` tz-aware; nunca `datetime.now()` no core): testes usam `FixedClock` ⇒ time-to-expiry 100% determinístico.
- **RNG injetado e seedado** (`RandomSource`; nunca `random.random()` module-level): seed pertence ao chamador. `MockOrderBookAdapter` exige seed no construtor.
- **Teste de reprodutibilidade explícito:** mesma seed ⇒ resultados bit-a-bit idênticos em duas execuções; seeds diferentes ⇒ resultados diferentes (pega seed ignorada).
- **Ordem de soma é determinismo numérico:** agregação de portfólio/cenários usa ordem determinística e `math.fsum` — iterar sobre `set` muda a ordem da soma e o último bit, quebrando os testes de 1e-12.
- **Enforcement de camadas: `import-linter` no CI** (mecanismo único): `domain` só stdlib; `domain`/`application` sem fastapi/pydantic/numpy; sem `datetime.now`/`random.<func>` no core.

---

## 8. Estrutura de diretórios de teste

```
tests/
├── conftest.py                     # perfis Hypothesis, fixtures FixedClock/SeededRandom
├── _tolerances.py                  # §1.2 codificada — ÚNICA fonte de tolerâncias
│                                   # (assert canônico assert_close vive em _tolerances.py)
├── data/golden/
│   └── bs_european.json            # §2.2 — camadas verified + published, com proveniência
├── kernel/
│   ├── test_black_scholes.py       # golden (§2) + propriedades (§4) + FD (§5) + fronteiras (§6)
│   └── test_distributions.py       # norm_cdf/pdf vs valores tabelados
├── domain/                         # Sprint 2: invariantes de VOs/agregados, payoff, breakevens
├── simulation/                     # Sprint 2: determinismo do grid, vega condicional por direção
├── contracts/                      # Sprint 3: suíte de contrato herdável (MarketDataPortContract)
├── application/                    # Sprint 3: use cases com fakes
├── api/                            # Sprint 4: TestClient, mapeamento de erros
└── oracle/                         # job de CI separado — requirements próprio (scipy)
    ├── requirements.txt            # NUNCA no pyproject do core
    └── test_diff_scipy.py
```

Convenção de nomes: o nome do arquivo diz **o que** testa e **contra qual oráculo**.

---

## 9. Contract Tests dos adapters

Classe de contrato abstrata escrita uma vez contra o `Protocol`; cada implementação herda e fornece só a fixture de construção (`class TestMockOrderBook(MarketDataPortContract)`). Invariantes que **toda** implementação de `MarketDataPort` garante:

1. `spot > 0` e `bid ≤ mid ≤ ask` para símbolo conhecido; símbolo desconhecido ⇒ `UnknownSymbolError` (exceção de domínio, nunca `KeyError`/`None` vazando pelo port).
2. Timestamps tz-aware, monotônicos não-decrescentes por símbolo.
3. Taxa sempre com `compounding` explícito; vol sempre com base de anualização explícita.
4. Snapshots imutáveis (frozen); leitura idempotente e sem efeitos colaterais.
5. **Específico do mock** (testado na subclasse, não no contrato): determinismo por seed.

Quando o adapter B3/websocket chegar, ele **herda esta suíte** — o diff do PR mostra apenas a fixture. É o teste executável da fronteira hexagonal.

---

## 10. Mutation Testing — a métrica que não mente (fase de hardening)

**Cobertura é métrica de vaidade:** executar `d1 = (log(S/K) + (r + 0.5σ²)T) / (σ√T)` conta como "coberto" mesmo sem nenhum assert no resultado — e cobertura não mede a política de tolerância. **Mutation score mede exatamente o que queremos:** o `mutmut` troca `+`→`−`, `0.5`→`1.5` etc. e roda a suíte; um mutante `0.5·σ² → σ²` muda o preço ATM em ~1–2% — se sobreviver, a tolerância está frouxa. É o detector empírico de falso negativo da política do §1.

**Operacional:** `mutmut` depende de `os.fork` — **não roda no Windows** (ambiente dev local deste repo). Roda exclusivamente no CI Linux, agendado para a **fase de hardening pós-v1.0** (junto com o oráculo QuantLib e o nightly Hypothesis de 10k). Alvo: score ≥ 90% no kernel; sobreviventes triados — matar com teste novo ou registrar como mutante equivalente com justificativa versionada (`tests/mutmut_equivalents.md`).

---

## 11. Gates

**Todo PR (a partir da Sprint 1):**

| Gate | Critério |
|---|---|
| Suíte principal | unit + boundaries + properties (`ci-pr`, derandomize) + golden + contracts verdes |
| Cobertura | branch ≥ 95% no `domain/`; **100% de linhas no `domain/kernel/`** (pequeno e puro — menos é inaceitável) |
| Oracle | job scipy verde (ambiente separado) |
| Tipos e estilo | `mypy --strict` zero erros; `ruff check` + `ruff format --check` limpos |
| Arquitetura | `import-linter` verde (domain = stdlib only) |

**Hardening (pós-v1.0, agendado explicitamente — gate sem slot no roadmap é ficção):** nightly Hypothesis 10k (falha promovida a `@example`), mutmut ≥ 90% no kernel, oráculo QuantLib.

**Governança de tolerância:** toda tolerância vem de `tests/_tolerances.py` com justificativa na tabela §1.2; alterar tolerância exige alterar a tabela e passar por review explícito.

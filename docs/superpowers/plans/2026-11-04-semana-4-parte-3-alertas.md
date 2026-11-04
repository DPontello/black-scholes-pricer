# Semana 4, parte 3: alertas — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a aba **Alertas** (hoje "em breve") avisa vencimento próximo, risco de exercício, stop e alvo, e os avisos de depois do vencimento; nas operações com perna vendida, oferece a rolagem, que abre no Montador a mesma estrutura no vencimento seguinte com uma faixa que diz quanto custa zerar as pernas atuais.

**Architecture:** regras puras no domínio (`domain/alerts/`): recebem as operações já marcadas, o spot, os dias úteis até cada vencimento e os limites do perfil, e devolvem os alertas, sem I/O. O `AlertService` (aplicação) junta a visão da Carteira (`PortfolioView` + avisos de vencimento), o spot dos ativos, o calendário, os limites do perfil e os dispensados (um JSON na pasta do perfil). A rolagem é um caso de uso à parte que usa o `StrategyBuilderService.suggest`. Rotas em `/api/alertas`, a contagem e a lista no mesmo WebSocket da Carteira, e a tela em React.

**Tech Stack:** Python 3.12 (stdlib no domínio e na aplicação), FastAPI + pydantic no adaptador, pytest + hypothesis; React + TypeScript, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-11-03-semana-4-instalador-ir-alertas-design.md` §4 (regras em §4.1, como em §4.2, respostas do autor em §4.3) e §6 critério 3.

## Global Constraints

- Sem passos de commit: as mudanças ficam no working tree (CLAUDE.md do autor). Nada de `git commit`, `git stash` nem `git push`.
- **Padrões (autor, 04/11):** vencimento próximo a **5 dias úteis** ou menos; risco de exercício com a vendida dentro do dinheiro ou a menos de **2%** do strike, também a 5 du ou menos. Os dois editáveis no perfil.
- Dias úteis pelo `TradingCalendar` (intervalo meio-aberto `[hoje, vencimento)`): no dia do vencimento, 0 du. Depois do pregão do vencimento quem fala são os avisos que a Carteira já tem (`ExpiryNotice`).
- **Stop e alvo (autor, 03/11 e 04/11):** em R$, opcionais, por operação, **em qualquer operação** (também a só de ações). Comparados com o **resultado total**: realizado com custos + não realizado pelo preço de zerar. Stop dispara com `total <= -stop`; alvo com `total >= alvo`. Sem preço de zerar em alguma perna aberta (`unrealized is None`), o stop e o alvo dessa operação ficam **indeterminados**: não disparam nem limpam o dispensado.
- **Rolagem (autor, 04/11: faixa no Montador):** o domínio do Montador não aceita dois vencimentos (`strategy.py`, decisão nº 6), então o Montador abre **só a estrutura nova** no vencimento seguinte, e uma faixa no topo diz o custo de zerar as pernas atuais pelo preço de zerar e o caixa líquido da rolagem. Encerrar as atuais continua pelo Encerrar da Carteira. Nada é enviado.
- **Dispensar:** um alerta dispensado some até deixar de valer; quando ele deixa de valer numa avaliação **determinada**, o dispensado é apagado, e se voltar a valer ele reaparece (o "stop volta se o resultado piorar outra vez depois de melhorar" do §4.2). Os dispensados ficam na pasta do perfil (`alertas.json`), para valerem nos dois PCs.
- Fonte rotulada: com o Tryd fechado os alertas saem do fim de dia, e a tela diz "pelo fim de dia (B3)", como a Carteira.
- Arquivos já gravados seguem legíveis: `modelo`, `stop` e `alvo` da operação e `alertas` do perfil são campos **opcionais** no JSON, sem trocar a `versao` (como o `book` do perfil na semana 3).
- Domínio e aplicação só stdlib (import-linter). Somas com `math.fsum`. Nomes e mensagens em pt-BR como o código ao redor; identificadores públicos em inglês como no resto do domínio.
- Comentários só para um porquê não óbvio (pedido do autor).
- Gates: `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, `pytest` (cobertura mínima do projeto); frontend `npm run verificar` e `npm run build`. Por tarefa, só as checagens rápidas e as suítes tocadas; o gate completo no fim (HANDOFF §4).

## Review Focus

1. **Stop que volta:** dispensado com o total em −R$ 210 (stop R$ 200), o total melhora para −R$ 150 (dispensado apagado), piora para −R$ 205 (alerta de novo) — `test_stop_dispensado_volta_depois_de_melhorar` (Task 4).
2. **Tryd piscando:** o preço de zerar some por um ciclo; o stop dispensado **não** volta só por isso — `test_sem_preco_de_zerar_nao_limpa_o_dispensado` (Task 4).
3. **Put vendida perto do strike:** spot 30,50, strike 30,00, 2%: dentro de `30·1,02 = 30,60`, dispara "perto do strike"; spot 30,70 não dispara — `test_put_vendida_a_menos_de_2_por_cento` (Task 1).
4. **Operação de antes do app** (sem `modelo`): a rolagem abre o Montador no vencimento seguinte sem strikes sugeridos, só a faixa — `test_rolagem_sem_modelo` (Task 5).
5. **Arquivo de operação gravado antes desta parte** (sem `modelo`, `stop`, `alvo`): lê igual, e regravar não inventa campo — `test_operacao_antiga_sem_campos_novos` (Task 2).
6. **Perfil sem nenhuma operação aberta:** a aba diz que não há alertas, e o menu fica sem contagem — `test_sem_alertas_mostra_o_vazio` (Task 7).

## Arquivos

- Create `src/options_engine/domain/alerts/__init__.py`, `domain/alerts/model.py` (limites, alerta, tipos), `domain/alerts/rules.py` (as regras) (Task 1).
- Modify `src/options_engine/domain/portfolio/model.py` (`Operation` ganha `template`, `stop_loss`, `target`); `adapters/outbound/storage/operations.py`; `application/ports/portfolio.py` (`RegisterOperation`, `set_limits`); `application/use_cases/portfolio.py`; `adapters/inbound/web/portfolio.py` (Task 2).
- Modify `src/options_engine/domain/model/profile.py` (`Profile.alerts`); `adapters/outbound/storage/profiles.py`; `application/ports/inbound.py` e `application/use_cases/profiles.py` (`set_alert_settings`); `adapters/inbound/web/profiles.py` (Task 3).
- Create `src/options_engine/application/ports/alerts.py`, `application/use_cases/alerts.py`, `adapters/outbound/storage/dismissed_alerts.py` (Task 4).
- Create `application/use_cases/roll.py` (ou função no `alerts.py`, se ficar pequena) (Task 5).
- Create `src/options_engine/adapters/inbound/web/alerts.py`; modify `adapters/inbound/web/market.py` (mensagem `alertas` no WebSocket), `adapters/inbound/web/portfolio.py` (`carteira_atual` devolve também a visão e os avisos), `config/web_app.py` (Task 6).
- Frontend (Tasks 7–8): create `frontend/src/api/alertas.ts`, `frontend/src/paginas/Alertas.tsx` + teste; modify `App.tsx`, `componentes/Shell.tsx` (contagem), `api/aoVivo.ts` (mensagem `alertas`), `paginas/Carteira.tsx` (`?operacao=`, editar stop e alvo), `componentes/FormOperacao.tsx` (stop e alvo no registro), `api/carteira.ts` (`rascunhoDaAnalise` leva o `modelo`), `paginas/Montador.tsx` (faixa de rolagem), `aprender/glossario.ts`, `aprender/Telas.tsx`, `aprender/Termos.test.tsx`; fixtures em `frontend/src/testes/`.
- Tests: `tests/alerts/` (novo), `tests/portfolio/test_model.py`, `tests/adapters/storage/` (operações e perfis), `tests/application/test_alerts.py`, `tests/application/test_roll.py`, `tests/web/test_alerts_api.py`, `tests/web/test_market_api.py`, `tests/web/test_portfolio_api.py`, `tests/web/test_profiles_api.py`.

---

### Task 1: Regras dos alertas no domínio

**Files:**
- Create: `src/options_engine/domain/alerts/__init__.py`, `model.py`, `rules.py`
- Test: `tests/alerts/__init__.py`, `tests/alerts/test_rules.py`

**Interfaces (Produces, usadas nas Tasks 3–6):**

```python
@dataclass(frozen=True, slots=True)
class AlertSettings:
    expiry_days: int = 5          # 0 <= dias <= 60
    strike_distance: float = 0.02  # fração; 0 <= x <= 0.20, finita

class AlertKind(StrEnum):
    EXERCISE_TO_REGISTER = "exercicio_a_registrar"   # vem do ExpiryNotice
    STOP = "stop"
    EXERCISE_RISK = "risco_de_exercicio"
    EXPIRY_NEAR = "vencimento_proximo"
    AWAITING_CLOSE = "aguardando_fechamento"          # vem do ExpiryNotice
    TARGET = "alvo"

@dataclass(frozen=True, slots=True)
class Alert:
    key: str                      # f"{kind}:{operation_id}:{leg}" (leg "-" quando é da operação)
    kind: AlertKind
    operation_id: str
    operation_name: str
    underlying: str
    leg: int | None
    symbol: str | None
    expiry: date | None
    business_days: int | None
    in_the_money: bool | None      # só no risco de exercício
    total: float | None            # só no stop e no alvo
    limit: float | None            # o stop ou o alvo
    can_roll: bool                 # operação com perna de opção vendida aberta

@dataclass(frozen=True, slots=True)
class OperationSnapshot:
    """O que as regras precisam de uma operação aberta, já marcada pela Carteira."""
    operation: Operation
    legs: tuple[LegState, ...]
    total: float | None            # realizado + não realizado; None sem preço de zerar

@dataclass(frozen=True, slots=True)
class Evaluation:
    alerts: tuple[Alert, ...]      # em ordem de gravidade (abaixo), depois operação e perna
    undetermined: frozenset[str]   # chaves que não deu para avaliar (sem spot, sem preço de zerar)

def evaluate(
    operations: Sequence[OperationSnapshot],
    notices: Sequence[tuple[str, int, str, date, ExpiryOutcome]],  # o ExpiryNotice, sem depender da aplicação
    spots: Mapping[str, float],                                    # ativo -> spot; ausente = indeterminado
    business_days: Callable[[date], int | None],                   # vencimento -> du a partir de hoje; None fora do calendário
    settings: AlertSettings,
) -> Evaluation: ...
```

**Regras** (o que os testes não determinam sozinhos):

1. **Gravidade:** `EXERCISE_TO_REGISTER`, `STOP`, `EXERCISE_RISK`, `EXPIRY_NEAR`, `AWAITING_CLOSE`, `TARGET` (a ordem do `AlertKind`).
2. **Vencimento próximo:** cada perna de **opção** aberta com `0 <= du <= expiry_days`. `du is None` → chave indeterminada.
3. **Risco de exercício:** só perna de opção **vendida** aberta com `du <= expiry_days`. Call: dentro com `spot > strike`, perto com `spot >= strike·(1 − d)`; put: dentro com `spot < strike`, perto com `spot <= strike·(1 + d)`. Sem spot do ativo → indeterminada. Uma perna em risco tem os dois alertas (vencimento e risco); a tela agrupa por operação (Task 7).
4. **Stop e alvo:** só com `stop_loss`/`target` na operação. `total is None` → as duas chaves indeterminadas.
5. **Avisos de depois do vencimento:** viram `EXERCISE_TO_REGISTER` / `AWAITING_CLOSE` com a perna, o ticker e o vencimento do aviso.
6. `can_roll`: a operação tem alguma perna de opção **vendida** aberta e o alerta é de vencimento próximo ou risco de exercício.

- [ ] **Step 1: Testes que falham** em `tests/alerts/test_rules.py` com os builders de `tests/portfolio/_builders.py` (`call(30.0)`, `put(28.0)`, `operacao(...)`) e `business_days=lambda v: (v - HOJE).days` simplificado onde não importa:
  - `test_vencimento_a_5_du_dispara_e_a_6_nao`
  - `test_no_dia_do_vencimento_0_du_dispara`
  - `test_call_vendida_dentro_do_dinheiro`, `test_call_vendida_a_menos_de_2_por_cento`, `test_call_comprada_nao_tem_risco_de_exercicio`
  - `test_put_vendida_a_menos_de_2_por_cento` (Review Focus 3)
  - `test_risco_fora_da_janela_de_dias_nao_dispara`
  - `test_stop_dispara_no_limite_exato` (`total == -stop`), `test_alvo_dispara`, `test_stop_em_operacao_so_de_acoes`
  - `test_sem_preco_de_zerar_stop_indeterminado`, `test_sem_spot_risco_indeterminado`, `test_fora_do_calendario_indeterminado`
  - `test_avisos_de_vencimento_viram_alertas`
  - `test_ordem_por_gravidade`
  - `test_limites_invalidos_recusados` (dias negativos, distância NaN ou > 20%)
  - hypothesis: `test_chaves_unicas` — nenhuma avaliação devolve duas vezes a mesma chave.
- [ ] **Step 2:** rodar e ver falhar (`ImportError`).
- [ ] **Step 3:** implementar `model.py` e `rules.py`.
- [ ] **Step 4:** `pytest tests/alerts -q`, `ruff`, `mypy`, `lint-imports`.
- [ ] **Step 5:** entrada no ledger da semana 4.

---

### Task 2: Modelo, stop e alvo na operação

**Files:**
- Modify: `domain/portfolio/model.py`, `adapters/outbound/storage/operations.py`, `application/ports/portfolio.py`, `application/use_cases/portfolio.py`, `adapters/inbound/web/portfolio.py`
- Test: `tests/portfolio/test_model.py`, `tests/adapters/storage/test_operations.py` (ou o arquivo onde o repositório de operações já é testado), `tests/application/test_portfolio*.py`, `tests/web/test_portfolio_api.py`

**Interfaces:**

```python
# Operation (campos novos, no fim, com padrão):
template: str | None = None    # a chave do modelo do Montador de onde veio
stop_loss: float | None = None # R$ de perda, > 0
target: float | None = None    # R$ de ganho, > 0

# RegisterOperation ganha template, stop_loss, target (padrão None).
# PortfolioUseCase ganha:
def set_limits(self, operation_id: str, stop_loss: float | None, target: float | None) -> Operation: ...
```

- JSON: `"modelo"`, `"stop"`, `"alvo"` só gravados quando não são `None`; na leitura, `dados.get(...)`. `versao` continua 1.
- API: `RegistroIn` ganha `modelo: str | None`, `stop: float | None = Field(gt=0)`, `alvo: float | None = Field(gt=0)`; `OperacaoOut` ganha `modelo`, `stop`, `alvo`; rota nova `PUT /api/carteira/operacoes/{id}/limites` com `{stop, alvo}` (os dois opcionais; `null` apaga).
- `template` desconhecido do catálogo é aceito e gravado (o catálogo pode mudar); só a rolagem o ignora (Task 5).

- [ ] **Step 1: Testes que falham:** `test_stop_e_alvo_positivos` (zero, negativo e NaN recusados), `test_operacao_antiga_sem_campos_novos` (Review Focus 5: lê um JSON sem os campos e regrava sem eles), `test_registro_guarda_modelo_stop_e_alvo`, `test_limites_trocam_e_apagam`, `test_limites_em_operacao_desconhecida` (404 como as outras rotas), `test_registro_api_com_stop_e_alvo`.
- [ ] **Step 2–4:** ver falhar, implementar, checagens rápidas e as suítes tocadas.
- [ ] **Step 5:** ledger.

---

### Task 3: Limites dos alertas no perfil

**Files:**
- Modify: `domain/model/profile.py`, `adapters/outbound/storage/profiles.py`, `application/ports/inbound.py`, `application/use_cases/profiles.py`, `adapters/inbound/web/profiles.py`
- Test: as suítes de perfil do domínio, do repositório, do serviço e da API

**Interfaces:**

```python
# Profile ganha: alerts: AlertSettings | None = None; propriedade alert_settings -> AlertSettings (padrão quando None)
# ProfileUseCase ganha: def set_alert_settings(self, settings: AlertSettings) -> Profile: ...
```

- JSON do perfil: campo opcional `"alertas": {"dias_vencimento": 5, "distancia_strike": 0.02}`; leitura como o `_book_from_json` (campo ausente → `None`; tipo errado → perfil ilegível com a mensagem do campo).
- API: `PerfilOut` ganha `alertas: {dias_vencimento, distancia_strike}`; rota `PUT /api/perfil/alertas`.

- [ ] Testes: `test_perfil_sem_alertas_usa_o_padrao`, `test_alertas_gravados_e_lidos`, `test_alertas_com_tipo_errado_ilegivel`, `test_put_alertas_api`, `test_put_alertas_invalidos_422_ou_400` (seguir o padrão das outras rotas de perfil).
- [ ] Ver falhar, implementar, checagens, ledger.

---

### Task 4: `AlertService` e os dispensados

**Files:**
- Create: `application/ports/alerts.py`, `application/use_cases/alerts.py`, `adapters/outbound/storage/dismissed_alerts.py`
- Modify: `application/ports/outbound.py` (porta `DismissedAlertsRepository`)
- Test: `tests/application/test_alerts.py`, `tests/adapters/storage/test_dismissed_alerts.py`

**Interfaces:**

```python
class DismissedAlertsRepository(Protocol):
    def load(self) -> frozenset[str]: ...
    def save(self, keys: frozenset[str]) -> None: ...

@dataclass(frozen=True, slots=True)
class AlertsView:
    alerts: tuple[Alert, ...]   # sem os dispensados
    dismissed: int              # quantos estão escondidos
    source: DataSource          # a da Carteira

class AlertUseCase(Protocol):
    def evaluate(self, view: PortfolioView, notices: Sequence[ExpiryNotice]) -> AlertsView: ...
    def dismiss(self, key: str) -> None: ...
    def restore_all(self) -> None: ...
```

- `evaluate`: monta os `OperationSnapshot` da `PortfolioView` (`total = realized + unrealized` com `fsum`; `None` se `unrealized is None` com perna aberta), o spot de cada ativo por `market.get_quotes` (`last`, senão `previous_close`), os dias úteis pelo calendário (data de hoje no fuso da B3 pelo `Clock`; `InvalidDomainValueError` do calendário → `None`), os limites do perfil aberto, e chama `evaluate` do domínio.
- **Dispensados:** mantém só `dispensados ∩ (ativos ∪ indeterminados)`; grava **só quando muda** (o WebSocket avalia a cada ciclo). Arquivo `alertas.json` na pasta do perfil: `{"versao": 1, "dispensados": [...]}`, escrita atômica (`write_json_atomic`). Ilegível → trata como vazio e **não** sobrescreve (como as operações), com um aviso no log.
- `dismiss` de chave que não está ativa: aceita e grava (a tela pode estar um ciclo atrás); a próxima avaliação a limpa se não valer.

- [ ] Testes: `test_stop_dispensado_volta_depois_de_melhorar` (Review Focus 1), `test_sem_preco_de_zerar_nao_limpa_o_dispensado` (Review Focus 2), `test_grava_so_quando_muda`, `test_spot_pelo_fechamento_anterior_sem_ultimo`, `test_sem_perfil_aberto_erro_de_dominio`, `test_arquivo_ilegivel_nao_e_sobrescrito`, `test_restaurar_todos`.
- [ ] Ver falhar, implementar, checagens, ledger.

---

### Task 5: Rolagem

**Files:**
- Create: `application/use_cases/roll.py` (e o DTO em `application/ports/alerts.py`)
- Test: `tests/application/test_roll.py`

**Interfaces:**

```python
@dataclass(frozen=True, slots=True)
class RollSuggestion:
    operation_id: str
    operation_name: str
    underlying: str
    current_expiry: date
    next_expiry: date | None        # None: a cadeia não tem vencimento depois do atual
    request: BuilderRequest | None  # a estrutura nova; None sem modelo conhecido ou sem next_expiry
    close_cash: float | None        # caixa para zerar as pernas de opção abertas: + recebe, − paga; None sem preço de zerar
    source: DataSource

def roll(self, operation_id: str) -> RollSuggestion: ...
```

**Regras** (Ruling: decisão de quem escreve, revisável):

1. **Vencimento atual:** o mais próximo entre as pernas de opção vendidas abertas.
2. **Vencimento seguinte:** pela cadeia do ativo (`list_expiries`): se o atual é mensal, o **próximo mensal**; se é semanal, o próximo vencimento qualquer.
3. **Estrutura nova:** `builder.suggest(ativo, operation.template, next_expiry)`, com as quantidades multiplicadas por `q_aberta / q_sugerida` da primeira perna de opção (o modelo sugere 100 × razão); a perna de ação do modelo fica de fora quando a operação já tem a ação (a rolagem é só das opções).
4. **Caixa de zerar:** `Σ` nas pernas de opção abertas: comprada recebe `bid·q`, vendida paga `ask·q` (o mesmo preço de zerar da Carteira, pelas `LegMark`).
5. Operação sem `template`, ou com um que o catálogo não tem: `request = None` (Review Focus 4).

- [ ] Testes: `test_rolagem_mensal_vai_ao_proximo_mensal`, `test_rolagem_semanal_vai_ao_proximo`, `test_quantidades_proporcionais`, `test_caixa_de_zerar`, `test_rolagem_sem_modelo` (Review Focus 4), `test_sem_vencimento_seguinte`, `test_operacao_sem_vendida_recusada` (`InvalidDomainValueError`).
- [ ] Ver falhar, implementar, checagens, ledger.

---

### Task 6: Rotas e WebSocket

**Files:**
- Create: `adapters/inbound/web/alerts.py`
- Modify: `adapters/inbound/web/portfolio.py`, `adapters/inbound/web/market.py`, `config/web_app.py`
- Test: `tests/web/test_alerts_api.py`, `tests/web/test_market_api.py`, `tests/web/test_portfolio_api.py`, `tests/config/test_web_app.py`

- `carteira_atual` passa a devolver também a `PortfolioView` e os `ExpiryNotice` (um dataclass pequeno), para o WebSocket montar a Carteira e os alertas **da mesma consulta de mercado**.
- Rotas: `GET /api/alertas` (roda o vencimento e a Carteira, como `GET /api/carteira`), `POST /api/alertas/{chave}/dispensar` (204), `POST /api/alertas/restaurar` (204), `GET /api/alertas/rolagem/{operacao_id}`.
- `AlertaOut` em pt-BR: `chave`, `tipo`, `operacao`, `nome`, `ativo`, `perna`, `ticker`, `vencimento`, `dias_uteis`, `dentro_do_dinheiro`, `total`, `limite`, `pode_rolar`; `AlertasOut`: `fonte`, `alertas`, `dispensados`. `RolagemOut`: `operacao`, `nome`, `ativo`, `vencimento_atual`, `vencimento_novo`, `pedido` (o mesmo `PedidoAnalise` que o Book manda ao Montador), `caixa_de_zerar`, `fonte`.
- WebSocket: mensagem nova `{"tipo": "alertas", "dados": AlertasOut}`, enviada só quando muda, como as outras; sem perfil, `{"tipo": "alertas", "erro", "mensagem"}` como a da Carteira.

- [ ] Testes: as quatro rotas (feliz, sem perfil, chave/operação desconhecida), a mensagem `alertas` no WebSocket só quando muda, e a montagem no `web_app`.
- [ ] Ver falhar, implementar, checagens, ledger.

---

### Task 7: Aba Alertas e a contagem no menu

**Files:**
- Create: `frontend/src/api/alertas.ts`, `frontend/src/paginas/Alertas.tsx`, `frontend/src/paginas/Alertas.test.tsx`, fixture em `frontend/src/testes/alertas.ts`
- Modify: `App.tsx` (rota `/alertas`), `componentes/Shell.tsx` (contagem ao lado de "Alertas"), `api/aoVivo.ts` (`alertas` no estado), `paginas/Carteira.tsx` (`?operacao=<id>` abre e rola até a operação)

- Lista agrupada por operação, na ordem de gravidade do primeiro alerta; cada alerta com a frase curta (por exemplo "PETRK300 vence em 3 dias úteis", "call vendida dentro do dinheiro", "stop: −R$ 210,00 (limite −R$ 200,00)"), o botão **Abrir na Carteira**, **Rolar** quando `pode_rolar` e **Dispensar**. "Mostrar dispensados (N)" restaura todos.
- Rótulo da fonte: "pelo fim de dia (B3)" quando `fonte` é `fim_de_dia`.
- Ajustes no fim da página: dias úteis e distância do strike (em %), gravados por `PUT /api/perfil/alertas`.
- Menu: "Alertas (N)" com N = alertas não dispensados; sem alertas, só "Alertas".
- O "?" de cada tipo leva ao termo do glossário (Task 8).

- [ ] Testes: `test_sem_alertas_mostra_o_vazio` (Review Focus 6), agrupamento e ordem, dispensar chama a rota e some, rolar navega ao Montador com o `state`, contagem no menu, rótulo de fim de dia, ajustes gravam.
- [ ] `npm --prefix frontend run verificar`, ledger.

---

### Task 8: Stop e alvo na tela, faixa de rolagem e glossário

**Files:**
- Modify: `componentes/FormOperacao.tsx` (campos "Stop (perda em R$)" e "Alvo (ganho em R$)", opcionais), `api/carteira.ts` (`rascunhoDaAnalise` leva `pedido.modelo` como `modelo`), `paginas/Carteira.tsx` (editar stop e alvo da operação aberta), `paginas/Montador.tsx` (faixa de rolagem pelo `state.rolagem`), `aprender/glossario.ts` (`rolagem`, `stop-e-alvo`, `risco-de-exercicio`), `aprender/Telas.tsx` (a aba Alertas), `aprender/Termos.test.tsx`
- Faixa no Montador: "Rolagem de **<nome>**: zerar as pernas atuais (vencimento <atual>) **recebe/paga R$ X** pelo preço de zerar. Abaixo, a mesma estrutura em <novo>. Caixa líquido da rolagem: R$ Y." com `Y = caixa_de_zerar + no_vencimento.caixa` da análise da estrutura nova; sem preço de zerar, "—" e o motivo. Sem `pedido` (operação sem modelo), o Montador abre no ativo com a cadeia do vencimento novo e a faixa diz "monte a estrutura nova pela cadeia". Botão "Fechar a faixa".
- [ ] Testes: os campos do registro vão no corpo; editar stop/alvo chama `PUT .../limites`; a faixa com e sem `pedido`; os três termos no glossário.
- [ ] `npm --prefix frontend run verificar`, ledger.

---

### Task 9: Ponta a ponta e documentação

- [ ] App real numa pasta de perfil temporária, com o fim de dia importado: uma call vendida de PETR4 a ≤ 5 du e perto do strike (dois alertas e Rolar), uma operação com stop (dispara, dispensar, melhora, piora, volta), uma operação só de ações com alvo; rolagem aberta no Montador com a faixa. Anotar no ledger os números conferidos à mão.
- [ ] Ao vivo com o Tryd, se for pregão: a contagem do menu muda sem recarregar.
- [ ] Gate completo (HANDOFF §2) e `npm --prefix frontend run build`.
- [ ] README (seção do app), ROADMAP (semana 4 completa), HANDOFF (§1 e uma seção da parte 3), ledger com a revisão final.

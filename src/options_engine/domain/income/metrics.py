"""Métricas de rendimento em forma fechada — ADR-0005.

Estruturas de renda e a base de capital (denominador) de cada uma:

- put coberta (``cash_secured_put_metrics``): prêmio / strike — o capital
  reservado em caixa, a base mais conservadora (ADR-0005 §1).
- venda coberta (``covered_call_metrics``): prêmio / spot — o capital
  empatado na ação (ADR-0005 item 5).
- trava de crédito (``credit_spread_metrics``): crédito / (largura -
  crédito) — retorno sobre risco, com a largura entre strikes como proxy do
  risco; a margem real da B3 não é modelada (ADR-0005 item 6).

Unidades no nome do campo (CONVENTIONS — unidade é contrato), todas em
DECIMAL (0.02 == 2%), nunca pontos percentuais:

- ``yield_period``: rendimento no período até o vencimento, sobre a base de
  capital da estrutura.
- ``yield_annual_252``: o mesmo rendimento anualizado por capitalização
  COMPOSTA em dias úteis, base 252: ``(1 + yield_period) ** (252 / du) - 1``,
  com ``du`` contado pelo ``TradingCalendar`` (meio-aberto, CONVENTIONS §2).
- ``excess_over_cdi_annual_252``: ``yield_annual_252`` menos o CDI efetivo
  anual base 252 (diferença simples, CONVENTIONS §3).
- ``net_*`` de rendimento: os mesmos três, LÍQUIDOS dos custos do cenário
  de rendimento (montagem + IR, ``costs.py``) para o tamanho de referência
  da posição, sobre a MESMA base de capital do bruto (ADR-0005, escolha 1)
  — a diferença bruto/líquido é exatamente o custo, e o líquido é monótono
  em cada parâmetro da tabela de custos.

``du = 0`` (vencimento hoje) não tem período a anualizar: as métricas
anualizadas valem ``None`` — explícito no tipo, nunca divisão por zero nem
número inventado.

Cenário do rendimento: a opção vendida vira pó no vencimento e o prêmio é
todo ganho — é sobre esse ganho, menos a montagem, que o IR é estimado.

Perfil no vencimento, bruto e líquido (ADR-0005 item 4). O resultado
líquido no preço ``S`` do subjacente no vencimento é
``bruto(S) - montagem - exercício(S) - IR(S)``: ``exercício(S)`` das pernas
que terminam dentro do dinheiro em ``S`` (strike ultrapassado; no dinheiro
não há exercício) e ``IR(S)`` de ``estimate_income_tax`` — alíquota sobre o
resultado positivo, limitado ao resultado do prêmio. Como o IR só encolhe
resultado positivo, o sinal do líquido é o do resultado antes do IR: o
breakeven líquido é o zero do resultado antes do IR, e cada extremo líquido
é o extremo antes do IR menos o IR do próprio cenário. A regra de cada
estrutura está na docstring da sua função.

Prêmio fora dos limites
de não-arbitragem da estrutura (dado inconsistente) é rejeitado com
``InvalidDomainValueError`` e motivo explícito, nunca vira número.
"""

from dataclasses import dataclass
from enum import Enum, unique
from math import expm1, fsum, isfinite, log1p

from options_engine.domain.income.costs import (
    REFERENCE_POSITION_SHARES,
    CostSchedule,
    OperationCosts,
    OrderCosts,
    estimate_exercise_costs,
    estimate_income_tax,
    estimate_setup_costs,
)
from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
)
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidDomainValueError, InvalidStrategyError
from options_engine.domain.model.factories import vertical_spread, vertical_spread_direction
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation import net_premium_cashflow

__all__ = [
    "IncomeMetrics",
    "IncomeStructure",
    "annualize_yield_252",
    "cash_secured_put_metrics",
    "covered_call_metrics",
    "credit_spread_metrics",
    "excess_over_cdi_annual_252",
]


def _exige_cdi_efetivo_252(cdi: RiskFreeRate) -> None:
    if cdi.compounding is not Compounding.BUSINESS_DAILY_252:
        raise InvalidDomainValueError(
            f"a comparação com o CDI exige taxa efetiva anual base 252 "
            f"(Compounding.BUSINESS_DAILY_252); recebido {cdi.compounding.name} — o VO "
            f"não oferece a conversão para efetiva e o domínio não a inventa "
            f"(CONVENTIONS §3)"
        )


def _exige_preco(nome: str, valor: float) -> None:
    if not (isfinite(valor) and valor > 0.0):
        raise InvalidDomainValueError(f"{nome} deve ser finito e > 0; recebido {valor!r}")


def _exige_premio(valor: float) -> None:
    if not (isfinite(valor) and valor >= 0.0):
        raise InvalidDomainValueError(f"prêmio deve ser finito e >= 0; recebido {valor!r}")


# ---------------------------------------------------------------------------
# Anualização e comparação com o CDI
# ---------------------------------------------------------------------------


def annualize_yield_252(yield_period: float, business_days: int) -> float | None:
    """Anualização composta em dias úteis: ``(1 + r) ** (252 / du) - 1``.

    - ``du = 0`` -> ``None`` (vencimento hoje: sem período a anualizar).
    - ``du < 0`` -> ``InvalidDomainValueError``.
    - ``r <= -1`` (perda de 100% ou mais da base) -> ``InvalidDomainValueError``:
      ``1 + r <= 0`` não tem potência real.
    - resultado além do float64 (ex.: retorno sobre risco alto em poucos du)
      -> ``InvalidDomainValueError`` — nunca ``inf``.

    A base 252 vem de ``DayCountConvention.BUSINESS_252`` (nunca literal).
    Implementação via ``expm1(252/du * log1p(r))``: matematicamente idêntica
    e sem descartar dígitos de ``r`` pequeno em ``1 + r`` — a mesma
    disciplina de ``RiskFreeRate.as_continuous``.
    """
    if business_days < 0:
        raise InvalidDomainValueError(
            f"dias úteis até o vencimento devem ser >= 0; recebido {business_days!r}"
        )
    # `not (r > -1)`: NaN compara False com tudo — também rejeitado.
    if not (isfinite(yield_period) and yield_period > -1.0):
        raise InvalidDomainValueError(
            f"rendimento no período deve ser finito e > -1 (-100%) para anualizar; "
            f"recebido {yield_period!r}"
        )
    if business_days == 0:
        return None
    expoente = DayCountConvention.BUSINESS_252.days_per_year / business_days
    try:
        return expm1(expoente * log1p(yield_period))
    except OverflowError as excecao:
        raise InvalidDomainValueError(
            f"rendimento anualizado não representável em float64: r={yield_period!r} "
            f"em {business_days} du"
        ) from excecao


def excess_over_cdi_annual_252(yield_annual_252: float | None, cdi: RiskFreeRate) -> float | None:
    """Excesso sobre o CDI: ``yield_annual_252 - cdi`` (efetivo anual base 252).

    ``None`` entra, ``None`` sai (``du = 0`` não tem anualizado). O CDI é
    validado SEMPRE — taxa em capitalização contínua é rejeitada com erro
    claro em vez de comparada como se fosse efetiva.
    """
    _exige_cdi_efetivo_252(cdi)
    if yield_annual_252 is None:
        return None
    if not isfinite(yield_annual_252):
        raise InvalidDomainValueError(
            f"rendimento anualizado deve ser finito; recebido {yield_annual_252!r}"
        )
    return yield_annual_252 - cdi.rate


# ---------------------------------------------------------------------------
# Resultado único para as estruturas de renda
# ---------------------------------------------------------------------------


@unique
class IncomeStructure(Enum):
    """Estruturas de renda comparadas pelo painel (ROADMAP Sprint 5)."""

    COVERED_CALL = "covered_call"  # venda coberta
    CASH_SECURED_PUT = "cash_secured_put"  # put coberta
    CREDIT_SPREAD = "credit_spread"  # trava de crédito (vertical)


@dataclass(frozen=True, slots=True)
class IncomeMetrics:
    """Métricas de UMA oportunidade de renda — o mesmo VO para todas as estruturas.

    Tipo único: o ranking entre estruturas ordena por qualquer campo sem
    ``isinstance`` — a estrutura é dado (``structure``), não subclasse
    (mesmo princípio do agregado ``Strategy``).

    Entradas, carregadas para rastreabilidade (todo número é reconstruível):

    - ``premium_per_share``: prêmio (ou crédito líquido), moeda por ação, >= 0.
    - ``capital_base_per_share``: denominador do rendimento, moeda por ação, > 0.
    - ``business_days``: dias úteis até o vencimento, >= 0.
    - ``reference_shares``: tamanho da posição dos custos e dos valores
      ``*_per_position``.
    - ``cdi``: taxa de comparação, efetiva anual base 252.
    - ``costs``: custos do cenário de rendimento (montagem + IR), com a
      ``CostSchedule`` usada.

    Rendimentos em decimal (ver docstring do módulo): ``yield_period``,
    ``yield_annual_252``, ``excess_over_cdi_annual_252`` e os ``net_*``.
    Os anualizados são ``None`` se e somente se ``business_days == 0``.

    Perfil no vencimento, BRUTO (sem custos), em moeda para
    ``reference_shares``:

    - ``breakeven``: preço do subjacente no vencimento com resultado zero.
    - ``max_gain_per_position`` / ``max_loss_per_position``: melhor e pior
      resultado. ``max_loss_per_position`` é VALOR (<= 0), não magnitude —
      mesma semântica de ``PayoffProfile.max_loss``. As estruturas de renda
      são todas LIMITADAS (ação não vale menos que zero; trava limitada pela
      largura), por isso os extremos são ``float`` e nunca ``None`` (que no
      ``PayoffProfile`` significa ilimitado).

    Perfil no vencimento, LÍQUIDO (ADR-0005 item 4), na mesma unidade e com a
    mesma semântica de sinal — montagem, exercício das pernas exercidas e IR
    estimado do cenário (docstring do módulo; regra de cada estrutura na
    docstring da sua função):

    - ``net_breakeven``: preço do subjacente no vencimento em que o resultado
      líquido troca de sinal; no salto do custo de exercício, o strike da
      perna vendida. ``None`` quando o resultado líquido nunca chega a zero
      (custos maiores que o prêmio) — explícito no tipo, nunca número
      inventado.
    - ``net_max_gain_per_position`` / ``net_max_loss_per_position``:
      resultado líquido do cenário de ganho máximo e do de perda máxima. O
      ganho máximo paga IR só sobre o prêmio; perda não paga IR.

    - ``downside_protection``: só na venda coberta — fração de queda do spot
      coberta pelo prêmio (decimal); ``None`` nas demais estruturas.
    """

    structure: IncomeStructure
    premium_per_share: float
    capital_base_per_share: float
    business_days: int
    reference_shares: int
    cdi: RiskFreeRate
    costs: OperationCosts
    yield_period: float
    yield_annual_252: float | None
    excess_over_cdi_annual_252: float | None
    net_yield_period: float
    net_yield_annual_252: float | None
    net_excess_over_cdi_annual_252: float | None
    breakeven: float
    max_gain_per_position: float
    max_loss_per_position: float
    net_breakeven: float | None
    net_max_gain_per_position: float
    net_max_loss_per_position: float
    downside_protection: float | None

    def __post_init__(self) -> None:
        _exige_cdi_efetivo_252(self.cdi)
        _exige_premio(self.premium_per_share)
        _exige_preco("capital_base_per_share", self.capital_base_per_share)
        if self.business_days < 0 or self.reference_shares < 1:
            raise InvalidDomainValueError(
                f"business_days deve ser >= 0 e reference_shares >= 1; recebido "
                f"{self.business_days!r} e {self.reference_shares!r}"
            )
        finitos = {
            "yield_period": self.yield_period,
            "net_yield_period": self.net_yield_period,
            "breakeven": self.breakeven,
            "max_gain_per_position": self.max_gain_per_position,
            "max_loss_per_position": self.max_loss_per_position,
            "net_max_gain_per_position": self.net_max_gain_per_position,
            "net_max_loss_per_position": self.net_max_loss_per_position,
        }
        for nome, valor in finitos.items():
            if not isfinite(valor):
                raise InvalidDomainValueError(f"{nome} deve ser finito; recebido {valor!r}")
        if self.net_breakeven is not None and not isfinite(self.net_breakeven):
            raise InvalidDomainValueError(
                f"net_breakeven deve ser finito ou None; recebido {self.net_breakeven!r}"
            )
        anualizados = {
            "yield_annual_252": self.yield_annual_252,
            "excess_over_cdi_annual_252": self.excess_over_cdi_annual_252,
            "net_yield_annual_252": self.net_yield_annual_252,
            "net_excess_over_cdi_annual_252": self.net_excess_over_cdi_annual_252,
        }
        for nome, anual in anualizados.items():
            if (anual is None) != (self.business_days == 0):
                raise InvalidDomainValueError(
                    f"{nome} é None se e somente se business_days == 0; recebido "
                    f"{anual!r} com {self.business_days} du"
                )
            if anual is not None and not isfinite(anual):
                raise InvalidDomainValueError(f"{nome} deve ser finito; recebido {anual!r}")
        protecao = self.downside_protection
        if (protecao is None) != (self.structure is not IncomeStructure.COVERED_CALL):
            raise InvalidDomainValueError(
                f"downside_protection existe só na venda coberta; recebido {protecao!r} "
                f"para {self.structure.name}"
            )
        if protecao is not None and not isfinite(protecao):
            raise InvalidDomainValueError(
                f"downside_protection deve ser finito; recebido {protecao!r}"
            )


def _depois_do_ir(schedule: CostSchedule, resultado: float, premium_result: float) -> float:
    """Resultado líquido de um cenário: o resultado antes do IR menos o IR estimado dele."""
    imposto = estimate_income_tax(schedule, pre_tax_result=resultado, premium_result=premium_result)
    return fsum((resultado, -imposto))


def _metricas(
    structure: IncomeStructure,
    *,
    premium_per_share: float,
    capital_base_per_share: float,
    setup: OrderCosts,
    premium_result: float,
    breakeven: float,
    max_gain_per_share: float,
    max_loss_per_share: float,
    net_breakeven: float | None,
    pre_tax_max_gain_per_position: float,
    pre_tax_max_loss_per_position: float,
    downside_protection: float | None,
    business_days: int,
    cdi: RiskFreeRate,
    reference_shares: int,
) -> IncomeMetrics:
    """Núcleo comum: IR, rendimento bruto/líquido, anualização, excesso e extremos.

    Cada estrutura só decide a SUA geometria (base de capital, breakeven,
    extremos brutos e antes do IR) e os SEUS custos de montagem e exercício;
    o IR e o resto são idênticos para todas — um único lugar.
    ``premium_result``: prêmio x ações menos as ordens de opção (o teto da
    base do IR, ``estimate_income_tax``).
    """
    schedule = setup.schedule
    receita = premium_per_share * reference_shares
    antes_do_ir = fsum((receita, -setup.total))
    custos = OperationCosts(
        setup=setup,
        income_tax=estimate_income_tax(
            schedule, pre_tax_result=antes_do_ir, premium_result=premium_result
        ),
    )
    bruto = premium_per_share / capital_base_per_share
    liquido = fsum((receita, -custos.total)) / (capital_base_per_share * reference_shares)
    anual = annualize_yield_252(bruto, business_days)
    anual_liquido = annualize_yield_252(liquido, business_days)
    return IncomeMetrics(
        structure=structure,
        premium_per_share=premium_per_share,
        capital_base_per_share=capital_base_per_share,
        business_days=business_days,
        reference_shares=reference_shares,
        cdi=cdi,
        costs=custos,
        yield_period=bruto,
        yield_annual_252=anual,
        excess_over_cdi_annual_252=excess_over_cdi_annual_252(anual, cdi),
        net_yield_period=liquido,
        net_yield_annual_252=anual_liquido,
        net_excess_over_cdi_annual_252=excess_over_cdi_annual_252(anual_liquido, cdi),
        breakeven=breakeven,
        max_gain_per_position=max_gain_per_share * reference_shares,
        max_loss_per_position=max_loss_per_share * reference_shares,
        net_breakeven=net_breakeven,
        net_max_gain_per_position=_depois_do_ir(
            schedule, pre_tax_max_gain_per_position, premium_result
        ),
        net_max_loss_per_position=_depois_do_ir(
            schedule, pre_tax_max_loss_per_position, premium_result
        ),
        downside_protection=downside_protection,
    )


# ---------------------------------------------------------------------------
# Estruturas
# ---------------------------------------------------------------------------


def cash_secured_put_metrics(
    *,
    strike: float,
    premium_per_share: float,
    business_days: int,
    cdi: RiskFreeRate,
    cost_schedule: CostSchedule,
    reference_shares: int = REFERENCE_POSITION_SHARES,
) -> IncomeMetrics:
    """Put coberta: venda de put com o strike inteiro reservado em caixa.

    Por ação (ADR-0005 §1): rendimento = prêmio / strike; breakeven =
    strike - prêmio; ganho máximo = prêmio (put vira pó); pior resultado =
    -(strike - prêmio) (exercida com a ação a zero). Uma ordem (uma perna).

    Líquido (ADR-0005 item 4), por posição de ``n`` ações; a put exercida
    compra as ações ao strike e paga o exercício:

    - ganho máximo: put vira pó (S >= K), sem exercício: prêmio x n -
      montagem - IR;
    - perda máxima: exercida com a ação a zero: -(K - prêmio) x n - montagem
      - exercício; sem IR;
    - breakeven: no trecho exercido, ``K - prêmio + (montagem + exercício) /
      n``. Se esse ponto não fica abaixo de K, o resultado só fica >= 0 em K,
      onde o exercício some: breakeven = K. Prêmio menos montagem negativo:
      ``None``.

    Prêmio >= strike -> ``InvalidDomainValueError``: uma put nunca vale o
    strike ou mais (arbitragem ou dado inconsistente).
    """
    _exige_preco("strike", strike)
    _exige_premio(premium_per_share)
    if not (premium_per_share < strike):
        raise InvalidDomainValueError(
            f"put coberta exige prêmio < strike (arbitragem ou dado inconsistente); "
            f"recebido prêmio={premium_per_share!r}, strike={strike!r}"
        )
    n = reference_shares
    montagem = estimate_setup_costs(
        cost_schedule, option_leg_premiums_per_share=(premium_per_share,), shares=n
    )
    exercicio = estimate_exercise_costs(cost_schedule, exercised_strikes=(strike,), shares=n)
    resultado_do_premio = fsum((premium_per_share * n, -montagem.total))
    if resultado_do_premio < 0.0:
        breakeven_liquido = None
    else:
        custo_por_acao = fsum((montagem.total, exercicio.total)) / n
        breakeven_liquido = min(fsum((strike, -premium_per_share, custo_por_acao)), strike)
    return _metricas(
        IncomeStructure.CASH_SECURED_PUT,
        premium_per_share=premium_per_share,
        capital_base_per_share=strike,
        setup=montagem,
        premium_result=resultado_do_premio,
        breakeven=strike - premium_per_share,
        max_gain_per_share=premium_per_share,
        max_loss_per_share=-(strike - premium_per_share),
        net_breakeven=breakeven_liquido,
        pre_tax_max_gain_per_position=resultado_do_premio,
        pre_tax_max_loss_per_position=fsum(
            (-(strike - premium_per_share) * n, -montagem.total, -exercicio.total)
        ),
        downside_protection=None,
        business_days=business_days,
        cdi=cdi,
        reference_shares=n,
    )


def covered_call_metrics(
    *,
    spot: float,
    strike: float,
    premium_per_share: float,
    business_days: int,
    cdi: RiskFreeRate,
    cost_schedule: CostSchedule,
    reference_shares: int = REFERENCE_POSITION_SHARES,
) -> IncomeMetrics:
    """Venda coberta: ação em carteira + call vendida, em forma fechada.

    Por ação (decisão da mesa, ADR-0005 item 5): rendimento = prêmio / spot
    (o capital empatado na ação); proteção = prêmio / spot — fração de queda
    do spot coberta pelo prêmio (mesmo número do rendimento por causa da
    base escolhida, semântica distinta); breakeven = spot - prêmio; ganho
    máximo = strike - spot + prêmio (exercida); pior resultado =
    -(spot - prêmio) (ação a zero).

    Montagem (ADR-0005 item 3): a ordem da opção (emolumentos de opções sobre
    o prêmio + corretagem) e a compra das ações (emolumentos do à vista sobre
    ``spot x ações`` + corretagem de uma ordem). O rendimento líquido
    desconta a montagem inteira, na mesma base do bruto (o spot).

    Líquido (ADR-0005 itens 3 e 4), por posição de ``n`` ações:

    - ganho máximo: call exercida (S > K), as ações saem ao strike pagando o
      exercício: (K - spot + prêmio) x n - montagem - exercício - IR, com o
      IR só sobre o prêmio menos a ordem da opção (a valorização da ação
      fica fora, ADR-0005 escolha 2). Com S = K a call não é exercida e a
      ação fica marcada a K sem custo de venda: esse ponto vale mais que o
      ganho máximo, no máximo pelo custo de exercício. A mesa mede o ganho
      máximo no cenário exercido;
    - perda máxima: ação a zero, call vira pó: -(spot - prêmio) x n -
      montagem; sem IR;
    - breakeven: no trecho não exercido, ``spot - prêmio + montagem / n``.
      Se o resultado em S = K (não exercido) é negativo, esse ponto passa do
      strike e nenhum preço zera o resultado líquido (o exercido é ainda
      menor): ``None``. A decisão é tomada em moeda, não no preço
      arredondado — custo abaixo da resolução do preço não vira breakeven.

    Limites de não-arbitragem: ``max(spot - strike, 0) <= prêmio < spot`` —
    call abaixo do intrínseco ou valendo o spot inteiro é dado inconsistente
    -> ``InvalidDomainValueError``.
    """
    _exige_preco("spot", spot)
    _exige_preco("strike", strike)
    _exige_premio(premium_per_share)
    if not (max(spot - strike, 0.0) <= premium_per_share < spot):
        raise InvalidDomainValueError(
            f"venda coberta exige intrínseco <= prêmio < spot (arbitragem ou dado "
            f"inconsistente); recebido prêmio={premium_per_share!r}, spot={spot!r}, "
            f"strike={strike!r}"
        )
    n = reference_shares
    montagem = estimate_setup_costs(
        cost_schedule,
        option_leg_premiums_per_share=(premium_per_share,),
        stock_purchase_price_per_share=spot,
        shares=n,
    )
    ordem_da_opcao = estimate_setup_costs(
        cost_schedule, option_leg_premiums_per_share=(premium_per_share,), shares=n
    )
    exercicio = estimate_exercise_costs(cost_schedule, exercised_strikes=(strike,), shares=n)
    ganho_maximo = fsum((strike, -spot, premium_per_share))
    breakeven_liquido: float | None = None
    if fsum((ganho_maximo * n, -montagem.total)) >= 0.0:
        # O min só segura o arredondamento do preço contra o strike.
        breakeven_liquido = min(fsum((spot, -premium_per_share, montagem.total / n)), strike)
    return _metricas(
        IncomeStructure.COVERED_CALL,
        premium_per_share=premium_per_share,
        capital_base_per_share=spot,
        setup=montagem,
        premium_result=fsum((premium_per_share * n, -ordem_da_opcao.total)),
        breakeven=spot - premium_per_share,
        max_gain_per_share=ganho_maximo,
        max_loss_per_share=-(spot - premium_per_share),
        net_breakeven=breakeven_liquido,
        pre_tax_max_gain_per_position=fsum((ganho_maximo * n, -montagem.total, -exercicio.total)),
        pre_tax_max_loss_per_position=fsum((-(spot - premium_per_share) * n, -montagem.total)),
        downside_protection=premium_per_share / spot,
        business_days=business_days,
        cdi=cdi,
        reference_shares=n,
    )


def credit_spread_metrics(
    spread: Strategy,
    *,
    business_days: int,
    cdi: RiskFreeRate,
    cost_schedule: CostSchedule,
    reference_shares: int = REFERENCE_POSITION_SHARES,
) -> IncomeMetrics:
    """Trava de crédito — trava de alta com put ou trava de baixa com call.

    Reutiliza o agregado (ROADMAP Sprint 5): a composição é revalidada por
    ``vertical_spread``, a direção vem de ``vertical_spread_direction`` e o
    crédito de ``net_premium_cashflow`` (sinal e prêmios num único lugar,
    CONVENTIONS §4-5), normalizado por ação pela quantidade das pernas — os
    valores por posição usam ``reference_shares``, não a quantidade das legs.

    Por ação (decisão da mesa, ADR-0005 item 6): largura = K alto - K baixo;
    risco = largura - crédito (largura como proxy — a margem da B3 não é
    modelada); retorno sobre risco = crédito / risco; breakeven = K alto -
    crédito (puts) ou K baixo + crédito (calls); ganho máximo = crédito;
    pior resultado = -risco. Duas ordens; emolumento sobre cada perna.

    Líquido (ADR-0005 item 4), por posição de ``n`` ações; cada perna que
    termina dentro do dinheiro paga o exercício ao próprio strike:

    - ganho máximo: as duas viram pó, sem exercício: crédito x n - montagem
      - IR;
    - perda máxima: as duas exercidas: -(largura - crédito) x n - montagem -
      exercício das duas; sem IR;
    - breakeven: no trecho em que só a vendida é exercida, ``K alto -
      crédito + (montagem + exercício da vendida) / n`` (puts) ou ``K baixo
      + crédito - (montagem + exercício da vendida) / n`` (calls). Se esse
      ponto sai do trecho pelo lado do ganho, o resultado troca de sinal no
      strike vendido, onde o exercício some: breakeven = strike vendido.
      Crédito menos montagem negativo: ``None``.

    Rejeições, todas com motivo explícito (o painel exclui o candidato):

    - trava de débito ou estrutura que não é trava -> ``InvalidStrategyError``;
    - prêmio ausente em alguma perna -> ``MissingPremiumError``;
    - crédito < 0 (prêmios formam débito) ou crédito >= largura (risco nulo
      ou negativo) -> ``InvalidDomainValueError``: arbitragem ou dado
      inconsistente, nunca um retorno infinito.
    """
    trava = vertical_spread(spread.legs, name=spread.name)
    if vertical_spread_direction(trava) is not Side.SELL:
        raise InvalidStrategyError(
            f"métricas de trava de crédito exigem a direção crédito (trava de alta com "
            f"put ou de baixa com call); recebido {trava.name!r}"
        )
    perna_baixa, perna_alta = trava.legs
    credito = net_premium_cashflow(trava) / perna_baixa.quantity
    k_baixo, k_alto = perna_baixa.terms.strike, perna_alta.terms.strike
    largura = k_alto - k_baixo
    if not (0.0 <= credito < largura):
        raise InvalidDomainValueError(
            f"trava de crédito exige 0 <= crédito < largura (arbitragem ou dado "
            f"inconsistente); recebido crédito={credito!r}, largura={largura!r}"
        )
    # Crédito: a perna vendida é a mais valiosa — put de strike maior, call de
    # strike menor (vertical_spread_direction já garantiu a direção).
    de_puts = perna_baixa.terms.option_type is OptionType.PUT
    strike_vendido = k_alto if de_puts else k_baixo
    # Todas as pernas têm prêmio (net_premium_cashflow já exigiu); o filtro
    # só estreita o tipo para float.
    premios = tuple(leg.premium for leg in trava.legs if leg.premium is not None)
    n = reference_shares
    montagem = estimate_setup_costs(cost_schedule, option_leg_premiums_per_share=premios, shares=n)
    exercicio_da_vendida = estimate_exercise_costs(
        cost_schedule, exercised_strikes=(strike_vendido,), shares=n
    )
    exercicio_das_duas = estimate_exercise_costs(
        cost_schedule, exercised_strikes=(k_baixo, k_alto), shares=n
    )
    resultado_do_premio = fsum((credito * n, -montagem.total))
    custo_por_acao = fsum((montagem.total, exercicio_da_vendida.total)) / n
    breakeven_liquido: float | None
    if resultado_do_premio < 0.0:
        breakeven_liquido = None
    elif de_puts:
        breakeven_liquido = min(fsum((k_alto, -credito, custo_por_acao)), k_alto)
    else:
        breakeven_liquido = max(fsum((k_baixo, credito, -custo_por_acao)), k_baixo)
    return _metricas(
        IncomeStructure.CREDIT_SPREAD,
        premium_per_share=credito,
        capital_base_per_share=largura - credito,
        setup=montagem,
        premium_result=resultado_do_premio,
        breakeven=k_alto - credito if de_puts else k_baixo + credito,
        max_gain_per_share=credito,
        max_loss_per_share=-(largura - credito),
        net_breakeven=breakeven_liquido,
        pre_tax_max_gain_per_position=resultado_do_premio,
        pre_tax_max_loss_per_position=fsum(
            (-(largura - credito) * n, -montagem.total, -exercicio_das_duas.total)
        ),
        downside_protection=None,
        business_days=business_days,
        cdi=cdi,
        reference_shares=n,
    )

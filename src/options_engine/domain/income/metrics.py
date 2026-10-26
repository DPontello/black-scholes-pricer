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
- ``net_*``: os mesmos três, LÍQUIDOS dos custos estimados da montagem
  (``costs.py``) para o tamanho de referência da posição, sobre a MESMA base
  de capital do bruto — a diferença bruto/líquido é exatamente o custo, e o
  líquido é monótono em cada parâmetro da tabela de custos.

``du = 0`` (vencimento hoje) não tem período a anualizar: as métricas
anualizadas valem ``None`` — explícito no tipo, nunca divisão por zero nem
número inventado.

Cenário do rendimento: a opção vendida vira pó no vencimento e o prêmio é
todo ganho — é sobre esse ganho que o IR é estimado. Prêmio fora dos limites
de não-arbitragem da estrutura (dado inconsistente) é rejeitado com
``InvalidDomainValueError`` e motivo explícito, nunca vira número.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, unique
from math import expm1, fsum, isfinite, log1p

from options_engine.domain.income.costs import (
    REFERENCE_POSITION_SHARES,
    CostSchedule,
    OperationCosts,
    estimate_operation_costs,
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
    - ``costs``: custos estimados da montagem, com a ``CostSchedule`` usada.

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
        }
        for nome, valor in finitos.items():
            if not isfinite(valor):
                raise InvalidDomainValueError(f"{nome} deve ser finito; recebido {valor!r}")
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


def _metricas(
    structure: IncomeStructure,
    *,
    premium_per_share: float,
    capital_base_per_share: float,
    leg_premiums_per_share: Sequence[float],
    breakeven: float,
    max_gain_per_share: float,
    max_loss_per_share: float,
    downside_protection: float | None,
    business_days: int,
    cdi: RiskFreeRate,
    cost_schedule: CostSchedule,
    reference_shares: int,
) -> IncomeMetrics:
    """Núcleo comum: custos, rendimento bruto/líquido, anualização e excesso.

    Cada estrutura só decide a SUA geometria (base de capital, breakeven,
    extremos, pernas); o resto é idêntico para todas — um único lugar.
    """
    receita = premium_per_share * reference_shares
    custos = estimate_operation_costs(
        cost_schedule,
        leg_premiums_per_share=leg_premiums_per_share,
        gross_gain=receita,
        shares=reference_shares,
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
    return _metricas(
        IncomeStructure.CASH_SECURED_PUT,
        premium_per_share=premium_per_share,
        capital_base_per_share=strike,
        leg_premiums_per_share=(premium_per_share,),
        breakeven=strike - premium_per_share,
        max_gain_per_share=premium_per_share,
        max_loss_per_share=-(strike - premium_per_share),
        downside_protection=None,
        business_days=business_days,
        cdi=cdi,
        cost_schedule=cost_schedule,
        reference_shares=reference_shares,
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

    Custos: uma ordem, só a perna de opção — a compra da ação e o exercício
    ficam fora (a perna de ação não é modelada na Sprint 5).

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
    return _metricas(
        IncomeStructure.COVERED_CALL,
        premium_per_share=premium_per_share,
        capital_base_per_share=spot,
        leg_premiums_per_share=(premium_per_share,),
        breakeven=spot - premium_per_share,
        max_gain_per_share=fsum((strike, -spot, premium_per_share)),
        max_loss_per_share=-(spot - premium_per_share),
        downside_protection=premium_per_share / spot,
        business_days=business_days,
        cdi=cdi,
        cost_schedule=cost_schedule,
        reference_shares=reference_shares,
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
    largura = perna_alta.terms.strike - perna_baixa.terms.strike
    if not (0.0 <= credito < largura):
        raise InvalidDomainValueError(
            f"trava de crédito exige 0 <= crédito < largura (arbitragem ou dado "
            f"inconsistente); recebido crédito={credito!r}, largura={largura!r}"
        )
    if perna_baixa.terms.option_type is OptionType.PUT:
        breakeven = perna_alta.terms.strike - credito
    else:
        breakeven = perna_baixa.terms.strike + credito
    # Todas as pernas têm prêmio (net_premium_cashflow já exigiu); o filtro
    # só estreita o tipo para float.
    premios = tuple(leg.premium for leg in trava.legs if leg.premium is not None)
    return _metricas(
        IncomeStructure.CREDIT_SPREAD,
        premium_per_share=credito,
        capital_base_per_share=largura - credito,
        leg_premiums_per_share=premios,
        breakeven=breakeven,
        max_gain_per_share=credito,
        max_loss_per_share=-(largura - credito),
        downside_protection=None,
        business_days=business_days,
        cdi=cdi,
        cost_schedule=cost_schedule,
        reference_shares=reference_shares,
    )

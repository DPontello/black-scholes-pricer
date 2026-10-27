"""Custos estimados de uma operação de renda — tabela parametrizável (ADR-0005).

Modelo decidido pela mesa (ADR-0005, "Modelo de custos e decisões de
cálculo"), com uma função pura para cada parte:

- **montagem** (``estimate_setup_costs``): o que se paga para abrir a
  estrutura, e o que o rendimento líquido desconta. Cada perna de opção paga
  emolumentos de opções sobre o valor financeiro do PRÓPRIO prêmio (comprada
  ou vendida) e uma ordem de corretagem; a venda coberta paga também a compra
  das ações (emolumentos do à vista sobre ``spot x ações`` + uma ordem).
- **exercício** (``estimate_exercise_costs``): o que se paga no vencimento
  por perna que termina dentro do dinheiro — emolumentos do à vista sobre
  ``strike x ações`` (a B3 cobra o exercício pela tabela do à vista) + a
  corretagem de exercício. Depende do cenário: só entra onde a perna é
  exercida.
- **IR** (``estimate_income_tax``): alíquota sobre o resultado POSITIVO do
  cenário depois de montagem e exercício, limitado ao resultado do prêmio
  (prêmio menos as ordens de opção) — a valorização da ação fica fora da
  estimativa (ADR-0005, escolha 2) e perda não paga IR (item 4). É
  ESTIMATIVA por operação, não cálculo fiscal (sem apuração mensal, sem
  compensação de prejuízos).

Nenhum valor de tabela vive no código: os números chegam da configuração
versionada dentro de um ``CostSchedule`` com data de vigência — a
rastreabilidade de qual tabela gerou cada número (ADR-0005, Consequências).
Corretagem fixa não escala com o prêmio, por isso todo custo é calculado
para um tamanho de posição explícito (default nomeado:
``REFERENCE_POSITION_SHARES``).

Somas com ``math.fsum`` em ordem determinística (CONVENTIONS §6).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from math import fsum, isfinite
from typing import Final

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "REFERENCE_POSITION_SHARES",
    "CostSchedule",
    "OperationCosts",
    "OrderCosts",
    "estimate_exercise_costs",
    "estimate_income_tax",
    "estimate_setup_costs",
    "schedule_on",
]

REFERENCE_POSITION_SHARES: Final[int] = 100
"""Tamanho de referência da posição: 100 ações por estrutura (decisão da mesa).

Torna o rendimento líquido comparável entre estruturas — a corretagem fixa
pesa diferente conforme o tamanho; é default de parâmetro, nunca constante
enterrada no cálculo.
"""


def _exige_fracao(nome: str, valor: float) -> None:
    # `not (0 <= x < 1)`: NaN compara False com tudo — também rejeitado.
    if not (isfinite(valor) and 0.0 <= valor < 1.0):
        raise InvalidDomainValueError(
            f"{nome} é fração decimal e deve estar em [0, 1); recebido {valor!r}"
        )


def _exige_nao_negativo(nome: str, valor: float) -> None:
    if not (isfinite(valor) and valor >= 0.0):
        raise InvalidDomainValueError(f"{nome} deve ser finito e >= 0; recebido {valor!r}")


def _exige_positivo(nome: str, valor: float) -> None:
    if not (isfinite(valor) and valor > 0.0):
        raise InvalidDomainValueError(f"{nome} deve ser finito e > 0; recebido {valor!r}")


def _exige_finito(nome: str, valor: float) -> None:
    if not isfinite(valor):
        raise InvalidDomainValueError(f"{nome} deve ser finito; recebido {valor!r}")


def _exige_acoes(shares: int) -> None:
    if shares < 1:
        raise InvalidDomainValueError(f"shares deve ser >= 1; recebido {shares!r}")


@dataclass(frozen=True, slots=True)
class CostSchedule:
    """Tabela de custos vigente a partir de ``valid_from`` (inclusive).

    Unidade no nome do campo (CONVENTIONS — unidade é contrato):

    - ``option_exchange_fee_rate``: emolumentos da B3 de opções como fração
      DECIMAL do valor financeiro do prêmio de cada perna (0.00134 ==
      0,1340%), em [0, 1).
    - ``spot_exchange_fee_rate``: emolumentos da B3 do mercado à vista como
      fração DECIMAL do valor financeiro (0.0003 == 0,0300%), em [0, 1).
      Vale para a compra da ação na venda coberta e para o exercício, que a
      B3 cobra pela tabela do à vista sobre ``strike x ações``.
    - ``brokerage_per_order``: corretagem fixa, em moeda, por ordem; >= 0.
      Vale para as ordens de opção e para a ordem de compra da ação.
    - ``exercise_brokerage_per_order``: corretagem fixa, em moeda, por
      exercício de uma perna; >= 0.
    - ``income_tax_rate``: alíquota de IR como fração DECIMAL do ganho
      positivo (0.15 == 15%), em [0, 1).

    Taxas de 100% ou mais não têm semântica econômica e quebrariam a
    monotonia "mais prêmio -> mais rendimento líquido". A escolha da tabela
    vigente numa data é da configuração; aqui vive só o VO validado.
    """

    valid_from: date
    option_exchange_fee_rate: float
    spot_exchange_fee_rate: float
    brokerage_per_order: float
    exercise_brokerage_per_order: float
    income_tax_rate: float

    def __post_init__(self) -> None:
        _exige_fracao("option_exchange_fee_rate", self.option_exchange_fee_rate)
        _exige_fracao("spot_exchange_fee_rate", self.spot_exchange_fee_rate)
        _exige_nao_negativo("brokerage_per_order", self.brokerage_per_order)
        _exige_nao_negativo("exercise_brokerage_per_order", self.exercise_brokerage_per_order)
        _exige_fracao("income_tax_rate", self.income_tax_rate)


@dataclass(frozen=True, slots=True)
class OrderCosts:
    """Emolumentos e corretagem de um conjunto de ordens ou exercícios, em moeda.

    Sem IR: o imposto depende do resultado do cenário, não das ordens.
    Carrega a ``CostSchedule`` que o produziu — todo número é reconstruível
    a posteriori (mesma disciplina de auditoria do ``PricingResult``).
    """

    schedule: CostSchedule
    exchange_fees: float
    brokerage: float

    def __post_init__(self) -> None:
        _exige_nao_negativo("exchange_fees", self.exchange_fees)
        _exige_nao_negativo("brokerage", self.brokerage)

    @property
    def total(self) -> float:
        """Emolumentos + corretagem, em moeda."""
        return fsum((self.exchange_fees, self.brokerage))


@dataclass(frozen=True, slots=True)
class OperationCosts:
    """Custos do cenário de rendimento de UMA operação: montagem + IR estimado.

    É o custo que o rendimento líquido desconta. No cenário de rendimento a
    opção vendida vira pó: não há exercício. ``income_tax`` é ESTIMATIVA por
    operação, não cálculo fiscal. A ``CostSchedule`` usada vem da montagem.
    """

    setup: OrderCosts
    income_tax: float

    def __post_init__(self) -> None:
        _exige_nao_negativo("income_tax", self.income_tax)

    @property
    def schedule(self) -> CostSchedule:
        """Tabela de custos que produziu estes números."""
        return self.setup.schedule

    @property
    def total(self) -> float:
        """Montagem (emolumentos + corretagem) + IR estimado, em moeda."""
        return fsum((self.setup.exchange_fees, self.setup.brokerage, self.income_tax))


def schedule_on(schedules: Sequence[CostSchedule], on: date) -> CostSchedule:
    """A tabela vigente em ``on``: a de maior ``valid_from <= on``.

    Nenhuma vigente -> ``InvalidDomainValueError``: um custo sem tabela seria
    número inventado. Duas tabelas com a mesma vigência também: qual delas
    vale seria uma escolha silenciosa.
    """
    vigencias = [s.valid_from for s in schedules]
    repetidas = sorted({d for d in vigencias if vigencias.count(d) > 1})
    if repetidas:
        raise InvalidDomainValueError(
            f"tabelas de custo com a mesma vigência: {[d.isoformat() for d in repetidas]!r}"
        )
    vigentes = [s for s in schedules if s.valid_from <= on]
    if not vigentes:
        primeira = min(vigencias).isoformat() if vigencias else "nenhuma tabela"
        raise InvalidDomainValueError(
            f"nenhuma tabela de custos vigente em {on.isoformat()} (primeira vigência: {primeira})"
        )
    return max(vigentes, key=lambda s: s.valid_from)


def estimate_setup_costs(
    schedule: CostSchedule,
    *,
    option_leg_premiums_per_share: Sequence[float],
    stock_purchase_price_per_share: float | None = None,
    shares: int = REFERENCE_POSITION_SHARES,
) -> OrderCosts:
    """Custos de montar a operação com ``shares`` ações em cada perna.

    - emolumentos = ``option_exchange_fee_rate`` x soma de (prêmio_i x
      ``shares``) — valor financeiro de CADA perna de opção, comprada ou
      vendida — mais, com ação comprada, ``spot_exchange_fee_rate`` x
      (preço da ação x ``shares``);
    - corretagem = ``brokerage_per_order`` x número de ordens: uma por perna
      de opção e, com ação comprada, mais uma.

    ``option_leg_premiums_per_share``: prêmio unitário (moeda por ação) de
    cada perna de opção. ``stock_purchase_price_per_share``: preço de compra
    da ação, só na venda coberta; ``None`` nas estruturas sem ação.
    """
    if len(option_leg_premiums_per_share) == 0:
        raise InvalidDomainValueError("operação exige ao menos uma perna (uma ordem por perna)")
    for premio in option_leg_premiums_per_share:
        _exige_nao_negativo("prêmio da perna", premio)
    _exige_acoes(shares)
    emolumentos_opcoes = schedule.option_exchange_fee_rate * fsum(
        p * shares for p in option_leg_premiums_per_share
    )
    ordens = len(option_leg_premiums_per_share)
    if stock_purchase_price_per_share is None:
        emolumentos = emolumentos_opcoes
    else:
        _exige_positivo("preço de compra da ação", stock_purchase_price_per_share)
        emolumentos_acao = schedule.spot_exchange_fee_rate * stock_purchase_price_per_share * shares
        emolumentos = fsum((emolumentos_opcoes, emolumentos_acao))
        ordens += 1
    return OrderCosts(
        schedule=schedule,
        exchange_fees=emolumentos,
        brokerage=schedule.brokerage_per_order * ordens,
    )


def estimate_exercise_costs(
    schedule: CostSchedule,
    *,
    exercised_strikes: Sequence[float],
    shares: int = REFERENCE_POSITION_SHARES,
) -> OrderCosts:
    """Custos do exercício das pernas que terminam dentro do dinheiro num cenário.

    - emolumentos = ``spot_exchange_fee_rate`` x soma de (strike_i x
      ``shares``) — a B3 cobra o exercício pela tabela do à vista, sobre o
      volume financeiro ao strike;
    - corretagem = ``exercise_brokerage_per_order`` x número de pernas
      exercidas.

    ``exercised_strikes`` vazio é o cenário sem exercício: custo zero.
    """
    for strike in exercised_strikes:
        _exige_positivo("strike exercido", strike)
    _exige_acoes(shares)
    return OrderCosts(
        schedule=schedule,
        exchange_fees=schedule.spot_exchange_fee_rate * fsum(k * shares for k in exercised_strikes),
        brokerage=schedule.exercise_brokerage_per_order * len(exercised_strikes),
    )


def estimate_income_tax(
    schedule: CostSchedule,
    *,
    pre_tax_result: float,
    premium_result: float,
) -> float:
    """IR estimado de um cenário: ``income_tax_rate`` x max(min(resultado, prêmio), 0).

    ``pre_tax_result``: resultado do cenário em moeda, depois de montagem e
    exercício. ``premium_result``: resultado do prêmio em moeda — prêmio (ou
    crédito) recebido menos os custos das ordens de OPÇÃO. O limite pelo
    prêmio tira da base a valorização da ação (venda coberta exercida) sem
    deixar de abater uma perda da ação; nas estruturas sem ação o resultado
    nunca passa do prêmio e o limite não atua. Resultado <= 0 não paga IR.
    """
    _exige_finito("pre_tax_result", pre_tax_result)
    _exige_finito("premium_result", premium_result)
    return schedule.income_tax_rate * max(min(pre_tax_result, premium_result), 0.0)

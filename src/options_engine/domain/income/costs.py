"""Custos estimados de uma operação de renda — tabela parametrizável (ADR-0005).

Modelo decidido pela mesa (ADR-0005 §4, detalhado na Sprint 5):

- **emolumentos da B3:** TAXA sobre o valor financeiro do prêmio de CADA
  perna (a compra e a venda pagam);
- **corretagem:** valor FIXO por ordem — uma ordem por perna;
- **IR:** alíquota sobre o ganho POSITIVO da operação, depois de
  emolumentos e corretagem. É ESTIMATIVA por operação, não cálculo fiscal
  (sem apuração mensal, sem compensação de prejuízos).

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
    "estimate_operation_costs",
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
class OperationCosts:
    """Custos estimados de UMA operação, em moeda, para o tamanho de posição usado.

    Carrega a ``CostSchedule`` que os produziu — todo número é reconstruível
    a posteriori (mesma disciplina de auditoria do ``PricingResult``).
    ``income_tax`` é ESTIMATIVA por operação, não cálculo fiscal.
    """

    schedule: CostSchedule
    exchange_fees: float
    brokerage: float
    income_tax: float

    def __post_init__(self) -> None:
        _exige_nao_negativo("exchange_fees", self.exchange_fees)
        _exige_nao_negativo("brokerage", self.brokerage)
        _exige_nao_negativo("income_tax", self.income_tax)

    @property
    def total(self) -> float:
        """Soma dos custos (emolumentos + corretagem + IR estimado), em moeda."""
        return fsum((self.exchange_fees, self.brokerage, self.income_tax))


def estimate_operation_costs(
    schedule: CostSchedule,
    *,
    leg_premiums_per_share: Sequence[float],
    gross_gain: float,
    shares: int = REFERENCE_POSITION_SHARES,
) -> OperationCosts:
    """Custos de montar a operação com ``shares`` ações em cada perna.

    - emolumentos = ``option_exchange_fee_rate`` x soma de (prêmio_i x ``shares``)
      — valor financeiro de CADA perna, comprada ou vendida;
    - corretagem = ``brokerage_per_order`` x número de pernas;
    - IR = ``income_tax_rate`` x max(ganho bruto - emolumentos - corretagem, 0).

    ``leg_premiums_per_share``: prêmio unitário (moeda por ação) de cada
    perna — uma ordem por perna. ``gross_gain``: resultado bruto da operação
    em moeda, para ``shares`` ações, no cenário em que o rendimento é medido
    (o prêmio/crédito recebido); ``<= 0`` não paga IR.
    """
    if len(leg_premiums_per_share) == 0:
        raise InvalidDomainValueError("operação exige ao menos uma perna (uma ordem por perna)")
    for premio in leg_premiums_per_share:
        _exige_nao_negativo("prêmio da perna", premio)
    if shares < 1:
        raise InvalidDomainValueError(f"shares deve ser >= 1; recebido {shares!r}")
    if not isfinite(gross_gain):
        raise InvalidDomainValueError(f"gross_gain deve ser finito; recebido {gross_gain!r}")
    emolumentos = schedule.option_exchange_fee_rate * fsum(
        p * shares for p in leg_premiums_per_share
    )
    corretagem = schedule.brokerage_per_order * len(leg_premiums_per_share)
    base_do_ir = fsum((gross_gain, -emolumentos, -corretagem))
    imposto = schedule.income_tax_rate * max(base_do_ir, 0.0)
    return OperationCosts(
        schedule=schedule,
        exchange_fees=emolumentos,
        brokerage=corretagem,
        income_tax=imposto,
    )

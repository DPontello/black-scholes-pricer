"""Perfil de resultado no vencimento, bruto e líquido, de uma estrutura de renda.

Fonte dos pontos do gráfico de payoff do painel (plano da fase 2 §4): o
adapter só desenha. O motor de simulação não serve aqui — é europeu-only
(ADR-0002, nota 2) e não modela a perna de ação da venda coberta — então o
resultado por preço é calculado neste módulo, pelo MESMO modelo de custos de
``costs.py`` que as métricas em forma fechada usam:

    bruto(S)   = soma das pernas: sinal x ações x (prêmio - intrínseco(S))
                 + ações x (S - preço de compra) na venda coberta
    líquido(S) = bruto(S) - montagem - exercício(S) - IR(S)

com ``exercício(S)`` das pernas estritamente dentro do dinheiro em ``S`` e
``IR(S)`` de ``estimate_income_tax`` (alíquota sobre o resultado positivo,
limitado ao resultado do prêmio). Nos pontos de extremo e de breakeven, o
líquido daqui bate com os campos ``net_*`` de ``IncomeMetrics``.

Eixo: 0,5 a 1,5 x spot, com os strikes e os breakevens incluídos — a curva
é linear por partes, e incluir as quinas a torna exata em qualquer escala.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from math import fsum, isfinite
from typing import Final

from options_engine.domain.income.costs import (
    CostSchedule,
    estimate_exercise_costs,
    estimate_income_tax,
    estimate_setup_costs,
)
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "AXIS_POINTS",
    "IncomeProfile",
    "PositionLeg",
    "ProfilePoint",
    "income_profile",
    "result_at_expiry",
]

AXIS_POINTS: Final = 101
_AXIS_LOW: Final = 0.5
_AXIS_HIGH: Final = 1.5


@dataclass(frozen=True, slots=True)
class PositionLeg:
    """Perna de opção da estrutura: tipo, lado, strike e prêmio por ação."""

    option_type: OptionType
    side: Side
    strike: float
    premium: float

    def __post_init__(self) -> None:
        if not (isfinite(self.strike) and self.strike > 0.0):
            raise InvalidDomainValueError(f"strike deve ser finito e > 0; recebido {self.strike!r}")
        if not (isfinite(self.premium) and self.premium >= 0.0):
            raise InvalidDomainValueError(
                f"prêmio deve ser finito e >= 0; recebido {self.premium!r}"
            )

    def intrinsic(self, spot: float) -> float:
        if self.option_type is OptionType.CALL:
            return max(spot - self.strike, 0.0)
        return max(self.strike - spot, 0.0)


@dataclass(frozen=True, slots=True)
class ProfilePoint:
    """Resultado no vencimento com o subjacente a ``spot``, em moeda por posição."""

    spot: float
    gross: float
    net: float


@dataclass(frozen=True, slots=True)
class IncomeProfile:
    """Pontos do perfil (spot crescente) e o spot atual do subjacente."""

    points: tuple[ProfilePoint, ...]
    current_spot: float

    def __post_init__(self) -> None:
        spots = [p.spot for p in self.points]
        if len(spots) < 2 or any(b <= a for a, b in pairwise(spots)):
            raise InvalidDomainValueError("perfil exige ao menos 2 pontos com spot crescente")


def result_at_expiry(
    legs: Sequence[PositionLeg],
    spot: float,
    *,
    schedule: CostSchedule,
    shares: int,
    stock_purchase_price: float | None = None,
) -> tuple[float, float]:
    """(bruto, líquido) em moeda por posição com o subjacente a ``spot`` no vencimento.

    ``stock_purchase_price``: preço de compra da ação na venda coberta;
    ``None`` nas estruturas sem ação.
    """
    if not legs:
        raise InvalidDomainValueError("perfil exige ao menos uma perna de opção")
    if not (isfinite(spot) and spot >= 0.0):
        raise InvalidDomainValueError(f"spot deve ser finito e >= 0; recebido {spot!r}")
    sinais = [1.0 if leg.side is Side.SELL else -1.0 for leg in legs]
    parcelas = [
        sinal * shares * (leg.premium - leg.intrinsic(spot))
        for sinal, leg in zip(sinais, legs, strict=True)
    ]
    if stock_purchase_price is not None:
        parcelas.append(shares * (spot - stock_purchase_price))
    bruto = fsum(parcelas)
    premios = [leg.premium for leg in legs]
    montagem = estimate_setup_costs(
        schedule,
        option_leg_premiums_per_share=premios,
        stock_purchase_price_per_share=stock_purchase_price,
        shares=shares,
    )
    ordens_de_opcao = estimate_setup_costs(
        schedule, option_leg_premiums_per_share=premios, shares=shares
    )
    exercicio = estimate_exercise_costs(
        schedule,
        exercised_strikes=[leg.strike for leg in legs if leg.intrinsic(spot) > 0.0],
        shares=shares,
    )
    antes_do_ir = fsum((bruto, -montagem.total, -exercicio.total))
    resultado_do_premio = fsum(
        (
            *(sinal * leg.premium * shares for sinal, leg in zip(sinais, legs, strict=True)),
            -ordens_de_opcao.total,
        )
    )
    imposto = estimate_income_tax(
        schedule, pre_tax_result=antes_do_ir, premium_result=resultado_do_premio
    )
    return bruto, fsum((antes_do_ir, -imposto))


def income_profile(
    legs: Sequence[PositionLeg],
    *,
    current_spot: float,
    schedule: CostSchedule,
    shares: int,
    stock_purchase_price: float | None = None,
    breakevens: Sequence[float | None] = (),
    points: int = AXIS_POINTS,
) -> IncomeProfile:
    """Perfil de 0,5 a 1,5 x ``current_spot``, com strikes e breakevens no eixo.

    Cada strike entra duas vezes: no próprio preço (perna NÃO exercida) e no
    float seguinte acima (call) ou abaixo (put), onde o exercício e o custo
    dele já valem — sem isso o salto do custo de exercício viraria rampa no
    desenho.
    """
    if not (isfinite(current_spot) and current_spot > 0.0):
        raise InvalidDomainValueError(
            f"spot atual deve ser finito e > 0; recebido {current_spot!r}"
        )
    if points < 2:
        raise InvalidDomainValueError(f"perfil exige ao menos 2 pontos; recebido {points!r}")
    baixo, alto = _AXIS_LOW * current_spot, _AXIS_HIGH * current_spot
    eixo = {baixo + (alto - baixo) * i / (points - 1) for i in range(points)}
    for leg in legs:
        if baixo <= leg.strike <= alto:
            eixo.add(leg.strike)
            vizinho = leg.strike + leg.strike * 1e-9 * (
                1.0 if leg.option_type is OptionType.CALL else -1.0
            )
            if baixo <= vizinho <= alto:
                eixo.add(vizinho)
    for breakeven in breakevens:
        if breakeven is not None and baixo <= breakeven <= alto:
            eixo.add(breakeven)
    pontos = []
    for spot in sorted(eixo):
        bruto, liquido = result_at_expiry(
            legs,
            spot,
            schedule=schedule,
            shares=shares,
            stock_purchase_price=stock_purchase_price,
        )
        pontos.append(ProfilePoint(spot, bruto, liquido))
    return IncomeProfile(points=tuple(pontos), current_spot=current_spot)

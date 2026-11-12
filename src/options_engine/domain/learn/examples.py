"""Exemplo fixo de cada operação do catálogo (``TEMPLATES``), para a aba Aprender.

Cada modelo vira uma ``Strategy`` real pelo ``Template.build`` do Montador e os números saem de
``expiry_pnl`` e ``expiry_summary``: o texto e o gráfico da tela nunca divergem da conta do app.
O exemplo é sem custos nem IR: PETR4 a R$ 50,00, strikes de R$ 2 em R$ 2, prêmios de Black-Scholes.
"""

from dataclasses import dataclass, replace
from datetime import date
from typing import Final

from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.kernel.payoff import linspace
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.strategy import StockLeg, Strategy, StrategyLeg
from options_engine.domain.model.templates import TEMPLATES, Family, Template
from options_engine.domain.simulation.engine import net_premium_cashflow
from options_engine.domain.simulation.valuation import expiry_pnl, expiry_summary

__all__ = ["Example", "ExampleLeg", "example", "examples"]

_ATIVO: Final = "PETR4"
_SPOT: Final = 50.0
_PASSO_DO_STRIKE: Final = 2.0
_LOTE: Final = 100
_TAU: Final = 21 / 252  # 21 dias úteis
_TAXA: Final = 0.14
_VOL: Final = 0.30
_CENARIOS: Final = (45.0, 50.0, 55.0)
_CURVA_DE: Final = 30.0
_CURVA_ATE: Final = 70.0
_CURVA_PONTOS: Final = 81
# Só para a Strategy validar: o resultado no vencimento não depende da data.
_VENCIMENTO: Final = date(2026, 12, 21)


@dataclass(frozen=True, slots=True)
class ExampleLeg:
    option_type: OptionType
    side: Side
    strike: float
    premium: float
    quantity: int


@dataclass(frozen=True, slots=True)
class Example:
    """``net_premium`` > 0 recebe e < 0 paga (só as opções); ``max_loss`` é positivo e ``None`` em
    ``max_gain``/``max_loss`` é sem limite. Valores em reais, com centavos."""

    key: str
    name: str
    family: Family
    spot: float
    legs: tuple[ExampleLeg, ...]
    stock_quantity: int
    net_premium: float
    scenarios: tuple[tuple[float, float], ...]
    breakevens: tuple[float, ...]
    max_gain: float | None
    max_loss: float | None
    curve: tuple[tuple[float, float], ...]


def _centavos(valor: float) -> float:
    # A soma de prêmios de 2 casas por lotes inteiros chega com ruído de float (1,14 x 100 =
    # 113,99999999999999); `+ 0.0` tira o sinal do zero negativo.
    return round(valor, 2) + 0.0


def example(template: Template) -> Example:
    pernas: list[ExampleLeg] = []
    for perna in template.legs:
        strike = _SPOT + _PASSO_DO_STRIKE * perna.offset
        premio = round(
            bs_price(_SPOT, strike, _TAU, _TAXA, _VOL, is_call=perna.option_type.is_call), 2
        )
        pernas.append(
            ExampleLeg(perna.option_type, perna.side, strike, premio, _LOTE * perna.ratio)
        )
    acao = None
    if template.stock is not None:
        acao = StockLeg(_ATIVO, template.stock, _LOTE, _SPOT)
    estrategia = template.build([_perna_da_estrategia(p) for p in pernas], acao)

    empates, maximo, minimo = expiry_summary(estrategia)
    return Example(
        key=template.key,
        name=template.name,
        family=template.family,
        spot=_SPOT,
        legs=tuple(pernas),
        stock_quantity=0 if acao is None else acao.quantity,
        net_premium=_centavos(net_premium_cashflow(replace(estrategia, stock_legs=()))),
        scenarios=_resultados(estrategia, _CENARIOS),
        breakevens=empates,
        max_gain=None if maximo is None else _centavos(maximo),
        max_loss=None if minimo is None else _centavos(max(0.0, -minimo)),
        curve=_resultados(estrategia, linspace(_CURVA_DE, _CURVA_ATE, _CURVA_PONTOS)),
    )


def examples() -> tuple[Example, ...]:
    return tuple(example(modelo) for modelo in TEMPLATES)


def _perna_da_estrategia(perna: ExampleLeg) -> StrategyLeg:
    sufixo = "C" if perna.option_type.is_call else "P"
    return StrategyLeg(
        f"{_ATIVO}{sufixo}{perna.strike:g}",
        OptionTerms(_ATIVO, perna.strike, _VENCIMENTO, perna.option_type),
        perna.side,
        perna.quantity,
        perna.premium,
    )


def _resultados(estrategia: Strategy, precos: tuple[float, ...]) -> tuple[tuple[float, float], ...]:
    return tuple((preco, _centavos(expiry_pnl(estrategia, preco))) for preco in precos)

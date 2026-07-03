"""Resultados de precificação — gregas canônicas e resultado auditável.

Unidade no nome do campo é critério de review, não estilo (CONVENTIONS §1):
``theta_per_year`` e ``vega_per_vol_unit`` carregam a convenção que os
tornaria "falsos bugs" se fosse implícita. Conversões de exibição (Θ/dia
útil, vega/ponto) pertencem ao adapter de apresentação (decisão nº 8).
"""

from dataclasses import dataclass
from math import isfinite

from options_engine.domain.model.conventions import TimeToExpiry
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["Greeks", "PricingResult"]


@dataclass(frozen=True, slots=True)
class Greeks:
    """Gregas em unidades canônicas do kernel (CONVENTIONS §1).

    Rho entra desde o dia 1: o ``StressScenario`` tem ``rate_shift``, logo a
    grega correspondente existe. Agregação de portfólio é soma ponderada por
    ``side.sign * quantity`` — feita no motor de simulação com ``math.fsum``
    em ordem determinística (CONVENTIONS §6), nunca aqui dentro.
    """

    delta: float
    gamma: float
    theta_per_year: float
    vega_per_vol_unit: float
    rho: float

    def __post_init__(self) -> None:
        campos = {
            "delta": self.delta,
            "gamma": self.gamma,
            "theta_per_year": self.theta_per_year,
            "vega_per_vol_unit": self.vega_per_vol_unit,
            "rho": self.rho,
        }
        for nome, valor in campos.items():
            if not isfinite(valor):
                raise InvalidDomainValueError(f"{nome} deve ser finito; recebido {valor!r}")


@dataclass(frozen=True, slots=True)
class PricingResult:
    """Preço + gregas + o modelo e os inputs que os produziram.

    Carregar os inputs junto ao output dá rastreabilidade e reprodutibilidade
    de graça: todo número do sistema é reconstruível a posteriori (ARCH §2.1).
    ``model_id`` (ex.: "black-scholes-v1") identifica o modelo para auditoria.
    """

    price: float
    greeks: Greeks
    model_id: str
    snapshot: MarketSnapshot
    time_to_expiry: TimeToExpiry

    def __post_init__(self) -> None:
        if not isfinite(self.price):
            raise InvalidDomainValueError(f"price deve ser finito; recebido {self.price!r}")
        if not self.model_id:
            raise InvalidDomainValueError("model_id não pode ser vazio")

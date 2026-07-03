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

__all__ = ["Greeks", "PayoffProfile", "PricingResult"]


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


@dataclass(frozen=True, slots=True)
class PayoffProfile:
    """Perfil de payoff/P&L no vencimento sobre um eixo crescente de spots.

    Semânticas distintas por NOME (CONVENTIONS §5) — nenhum campo mistura:

    - ``payoff_at_expiry``: valor BRUTO no vencimento; sempre presente.
    - ``pnl``: resultado LÍQUIDO do prêmio; ``None`` quando alguma leg não
      tem prêmio informado (decisão nº 4 — prêmio é opcional).
    - ``breakevens``: zeros do pnl. ``None`` = não calculável (sem prêmio);
      tupla vazia = calculável e sem cruzamento. As duas coisas são
      diferentes e o tipo as distingue.
    - ``max_gain`` / ``max_loss``: extremos da curva de RESULTADO
      disponível — pnl quando há prêmio, payoff bruto caso contrário.
      ``None`` = ILIMITADO (explícito no tipo, não convenção mágica).
      ``max_loss`` é o pior VALOR da curva (tipicamente negativo), não uma
      magnitude: |max_loss| é a perda máxima.
    """

    spots: tuple[float, ...]
    payoff_at_expiry: tuple[float, ...]
    pnl: tuple[float, ...] | None
    breakevens: tuple[float, ...] | None
    max_gain: float | None
    max_loss: float | None

    def __post_init__(self) -> None:
        if len(self.spots) == 0:
            raise InvalidDomainValueError("perfil exige ao menos um ponto de spot")
        if any(not isfinite(s) for s in self.spots):
            raise InvalidDomainValueError("eixo de spots deve ser todo finito")
        if any(not (a < b) for a, b in zip(self.spots, self.spots[1:], strict=False)):
            raise InvalidDomainValueError("eixo de spots deve ser estritamente crescente")
        if len(self.payoff_at_expiry) != len(self.spots):
            raise InvalidDomainValueError(
                f"payoff_at_expiry tem {len(self.payoff_at_expiry)} pontos para "
                f"{len(self.spots)} spots"
            )
        if any(not isfinite(v) for v in self.payoff_at_expiry):
            raise InvalidDomainValueError("payoff_at_expiry deve ser todo finito")
        if (self.pnl is None) != (self.breakevens is None):
            raise InvalidDomainValueError(
                "pnl e breakevens andam juntos: ambos presentes (com prêmio) "
                "ou ambos None (sem prêmio, decisão nº 4)"
            )
        if self.pnl is not None:
            if len(self.pnl) != len(self.spots):
                raise InvalidDomainValueError(
                    f"pnl tem {len(self.pnl)} pontos para {len(self.spots)} spots"
                )
            if any(not isfinite(v) for v in self.pnl):
                raise InvalidDomainValueError("pnl deve ser todo finito")
        if self.breakevens is not None and any(not isfinite(b) for b in self.breakevens):
            raise InvalidDomainValueError("breakevens devem ser todos finitos")
        for nome, extremo in (("max_gain", self.max_gain), ("max_loss", self.max_loss)):
            if extremo is not None and not isfinite(extremo):
                raise InvalidDomainValueError(
                    f"{nome} deve ser finito ou None (= ilimitado); recebido {extremo!r}"
                )

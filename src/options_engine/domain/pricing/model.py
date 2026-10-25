"""Contrato de precificação — único, canônico e batch-first (ARCH §3).

A decisão irreversível do projeto, tomada no dia 1: um port escalar
``price(request)`` condenaria qualquer backend vetorizado futuro a receber
um item por vez — NumPy chamado 10.000 vezes com arrays de tamanho 1 é mais
lento que pure Python — e consertar depois quebraria adapters, use cases e
testes. A assinatura batch preserva o caminho PurePython → NumPy → Numba
atrás da MESMA interface; o escalar é açúcar derivado (``price_one``).

O tau entra RESOLVIDO no request: calcular tempo exige ``Clock`` +
``TradingCalendar``, e um modelo que consultasse o relógio deixaria de ser
referencialmente transparente. A application resolve o tempo; o modelo
permanece puro (ARCH §3, nota de pureza).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.conventions import TimeToExpiry
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    MixedAnnualizationBaseError,
)
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.results import PricingResult

__all__ = ["PricingModel", "PricingRequest", "price_one"]


@dataclass(frozen=True, slots=True)
class PricingRequest:
    """Pedido de precificação: termos + snapshot atômico + tau resolvido.

    Invariantes de coerência (estado inválido é irrepresentável):

    - o snapshot é do MESMO subjacente dos termos — precificar a opção de
      PETR4 com o snapshot de VALE3 é preço errado sem erro de runtime;
    - vol e tau na MESMA base de anualização (CONVENTIONS §2) — a armadilha
      que o ``MixedAnnualizationBaseError`` existe para tornar detectável.
    """

    terms: OptionTerms
    snapshot: MarketSnapshot
    time_to_expiry: TimeToExpiry

    def __post_init__(self) -> None:
        if self.terms.underlying != self.snapshot.underlying_symbol:
            raise InvalidDomainValueError(
                f"snapshot de {self.snapshot.underlying_symbol!r} não precifica termos de "
                f"{self.terms.underlying!r} — subjacente do snapshot e dos termos devem coincidir"
            )
        if self.snapshot.volatility.annualization_base is not self.time_to_expiry.convention:
            raise MixedAnnualizationBaseError(
                f"vol anualizada em {self.snapshot.volatility.annualization_base.name} com tau "
                f"em {self.time_to_expiry.convention.name}: misturar bases produz preço errado "
                f"sem erro de runtime (CONVENTIONS §2)"
            )


@runtime_checkable
class PricingModel(Protocol):
    """Strategy pattern intra-domínio (ARCH §3) — o contrato de precificação.

    Unidades canônicas FAZEM PARTE do contrato: tau em fração de ano, sigma
    anualizada decimal, taxa contínua, gregas nas unidades do VO ``Greeks``
    (``theta_per_year``, ``vega_per_vol_unit``, rho por 1.00 de taxa).
    """

    @property
    def model_id(self) -> str:
        """Identificador para auditoria no ``PricingResult`` (ex.: "black-scholes-v1")."""
        ...

    def supports(self, terms: OptionTerms) -> bool:
        """True se o modelo precifica estes termos.

        Permite ao use case falhar explicitamente
        (``UnsupportedExerciseStyleError``) em vez de deixar o modelo
        devolver um preço silenciosamente errado (decisão nº 2).
        """
        ...

    def price_many(self, requests: Sequence[PricingRequest]) -> Sequence[PricingResult]:
        """Precifica o lote inteiro — o método PRIMÁRIO do contrato.

        ``results[i]`` corresponde a ``requests[i]`` (mesma ordem, mesmo
        tamanho). Request não suportado → exceção tipada, nunca resultado
        parcial silencioso.
        """
        ...


def price_one(model: PricingModel, request: PricingRequest) -> PricingResult:
    """Açúcar escalar derivado do contrato batch, escrito UMA vez.

    ``price_one(m, r) == m.price_many([r])[0]`` por definição — função livre
    em vez de método do Protocol para que o contrato permaneça mínimo e
    nenhuma implementação precise reescrever a derivação (ARCH §3).
    """
    return model.price_many((request,))[0]

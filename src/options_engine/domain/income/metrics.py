"""Métricas de rendimento em forma fechada — ADR-0005.

Unidades no nome do campo (CONVENTIONS — unidade é contrato), todas em
DECIMAL (0.02 == 2%), nunca pontos percentuais:

- ``yield_period``: rendimento no período até o vencimento, sobre a base de
  capital da estrutura.
- ``yield_annual_252``: o mesmo rendimento anualizado por capitalização
  COMPOSTA em dias úteis, base 252: ``(1 + yield_period) ** (252 / du) - 1``,
  com ``du`` contado pelo ``TradingCalendar`` (meio-aberto, CONVENTIONS §2).
- ``excess_over_cdi_annual_252``: ``yield_annual_252`` menos o CDI efetivo
  anual base 252 (diferença simples, CONVENTIONS §3).

``du = 0`` (vencimento hoje) não tem período a anualizar: as métricas
anualizadas valem ``None`` — explícito no tipo, nunca divisão por zero nem
número inventado.
"""

from math import expm1, isfinite, log1p

from options_engine.domain.model.conventions import (
    Compounding,
    DayCountConvention,
    RiskFreeRate,
)
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["annualize_yield_252", "excess_over_cdi_annual_252"]


def _exige_cdi_efetivo_252(cdi: RiskFreeRate) -> None:
    if cdi.compounding is not Compounding.BUSINESS_DAILY_252:
        raise InvalidDomainValueError(
            f"a comparação com o CDI exige taxa efetiva anual base 252 "
            f"(Compounding.BUSINESS_DAILY_252); recebido {cdi.compounding.name} — o VO "
            f"não oferece a conversão para efetiva e o domínio não a inventa "
            f"(CONVENTIONS §3)"
        )


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

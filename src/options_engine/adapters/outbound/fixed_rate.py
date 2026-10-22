"""Taxa fixa de configuração — CDI flat com compounding explícito.

NÃO é um port (painel de design, 2026-07-04): nenhum use case consome taxa
fora do ``MarketSnapshot`` — ela chega atômica, dentro da foto. Este adapter
é a FONTE de configuração da taxa que o composition root injeta no mock de
mercado; quando um feed real de curva existir, ele nasce adapter do
``MarketDataPort``, não daqui.
"""

from dataclasses import dataclass

from options_engine.domain.model.conventions import Compounding, RiskFreeRate

__all__ = ["FixedRateAdapter"]


@dataclass(frozen=True, slots=True)
class FixedRateAdapter:
    """Taxa livre de risco constante, SEMPRE como VO com compounding.

    Taxa como ``float`` nu é proibida em qualquer fronteira (CONVENTIONS
    §3) — o construtor recebe o VO pronto; o atalho ``from_cdi_annual``
    carrega a convenção correta do CDI (efetiva anual, base 252 dias úteis).
    """

    rate: RiskFreeRate

    def current_rate(self) -> RiskFreeRate:
        return self.rate

    @classmethod
    def from_cdi_annual(cls, cdi: float) -> "FixedRateAdapter":
        """CDI cotado como taxa efetiva anual (decimal: 0.15 == 15% a.a.)."""
        return cls(RiskFreeRate(cdi, Compounding.BUSINESS_DAILY_252))

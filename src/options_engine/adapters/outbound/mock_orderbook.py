"""``MockOrderBookAdapter`` — feed de mercado sintético via GBM (ARCH §8).

Implementa ``MarketDataPort`` com um passeio geométrico browniano sobre a
``RandomSource`` injetada (seed obrigatória — CONVENTIONS §7): mesma seed ⇒
mesma sequência de snapshots, bit a bit. Determinismo é requisito do smoke
executável e dos contract tests, não conveniência.

Semântica ADVANCE-THEN-RETURN: cada ``get_snapshot`` avança o passeio UM
passo e devolve a foto nova — duas chamadas seguidas são dois instantes de
mercado distintos (um feed real também nunca repete o mesmo tick). O spot
inicial de configuração é o estado ANTERIOR ao primeiro snapshot.

Sinalizado (ARCH §8): a vol do snapshot é PARÂMETRO de configuração — o
mock gera preços com ela, e é ela que o pricer consome como vol de
referência. Estimar vol do book gerado é extensão futura, não isto.
"""

from math import exp, isfinite, sqrt

from options_engine.application.ports.outbound import Clock, RandomSource
from options_engine.domain.model.conventions import RiskFreeRate, Volatility
from options_engine.domain.model.errors import InvalidDomainValueError, UnknownSymbolError
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["MockOrderBookAdapter"]


class MockOrderBookAdapter:
    """Feed sintético de UM subjacente, 100% determinístico dada a seed.

    ``dt_years`` está na MESMA base de anualização da vol injetada — o
    default ``1/252`` é um pregão em base ``BUSINESS_252``; quem configurar
    vol em base 365 deve ajustar o passo junto (mesma armadilha do
    CONVENTIONS §2, aqui na geração).

    Book coerente por construção: ``mid = spot`` e
    ``bid/ask = mid·(1 ∓ spread/2)`` com ``spread`` relativo — a ordem
    ``0 <= bid <= mid <= ask`` exigida pelo contrato sai da fórmula, e o VO
    ``MarketSnapshot`` a reverifica na construção.
    """

    def __init__(
        self,
        *,
        underlying_symbol: str,
        initial_spot: float,
        drift: float,
        volatility: Volatility,
        risk_free_rate: RiskFreeRate,
        random_source: RandomSource,
        clock: Clock,
        spread: float = 0.002,
        dt_years: float = 1.0 / 252.0,
    ) -> None:
        if not underlying_symbol:
            raise InvalidDomainValueError("underlying_symbol não pode ser vazio")
        if not (isfinite(initial_spot) and initial_spot > 0.0):
            raise InvalidDomainValueError(
                f"initial_spot deve ser finito e > 0; recebido {initial_spot!r}"
            )
        if not isfinite(drift):
            raise InvalidDomainValueError(f"drift deve ser finito; recebido {drift!r}")
        # spread >= 2 faria bid <= 0 e violaria o contrato do port na
        # primeira chamada — melhor falhar na configuração que no uso.
        if not (isfinite(spread) and 0.0 <= spread < 2.0):
            raise InvalidDomainValueError(
                f"spread relativo deve estar em [0, 2); recebido {spread!r}"
            )
        if not (isfinite(dt_years) and dt_years > 0.0):
            raise InvalidDomainValueError(f"dt_years deve ser finito e > 0; recebido {dt_years!r}")
        self._symbol = underlying_symbol
        self._spot = initial_spot
        self._drift = drift
        self._volatility = volatility
        self._rate = risk_free_rate
        self._random = random_source
        self._clock = clock
        self._spread = spread
        self._dt = dt_years

    def get_snapshot(self, underlying_symbol: str) -> MarketSnapshot:
        if underlying_symbol != self._symbol:
            raise UnknownSymbolError(
                f"símbolo desconhecido no mock: {underlying_symbol!r} "
                f"(configurado: {self._symbol!r})"
            )
        self._advance()
        mid = self._spot
        return MarketSnapshot(
            underlying_symbol=self._symbol,
            spot=self._spot,
            bid=mid * (1.0 - self._spread / 2.0),
            ask=mid * (1.0 + self._spread / 2.0),
            mid=mid,
            risk_free_rate=self._rate,
            volatility=self._volatility,
            timestamp=self._clock.now(),
        )

    def _advance(self) -> None:
        """Um passo exato do GBM: S ← S·exp((mu - sigma²/2)·dt + sigma·√dt·Z)."""
        sigma = self._volatility.value
        (z,) = self._random.gaussians(1)
        self._spot *= exp(
            (self._drift - 0.5 * sigma * sigma) * self._dt + sigma * sqrt(self._dt) * z
        )

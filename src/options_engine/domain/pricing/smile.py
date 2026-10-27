"""Smile de volatilidade implícita por vencimento e preço TEÓRICO (ADR-0004, plano da fase 2 §3.1).

- Vol implícita por série só com book COMPLETO, a partir do MID: o mid
  serve só para o smile, nunca para rendimento (ADR-0004). Spot do snapshot,
  ``q = 0``, taxa contínua e tau em BUSINESS_252 resolvidos pelo chamador.
  Só ``CONVERGED`` com sigma > 0 vira ponto: sigma = 0 (preço no intrínseco
  descontado, regra 5 do ``implied_vol``) não carrega informação sobre a
  vol e entortaria a interpolação — escolha técnica da fase 2.
- Um smile por vencimento, calls e puts juntos: num strike com as duas, vale
  a série fora do dinheiro (put se K < spot, call se K >= spot).
- Interpolação LINEAR em strike entre os vizinhos, SEM extrapolação: fora do
  intervalo dos pontos não há vol do smile (o chamador exclui com o motivo
  "fora do smile"); smile sem pontos não interpola nada.
- Preço TEÓRICO só para ``quote.is_theoretical_eligible`` (book vazio e sem
  negócio no pregão): ``LegPremium(bs_price(vol interpolada), TEORICO)``.
- Delta e N(d2) por série com a vol implícita da própria série, senão a do
  smile; N(d2) da call (N(-d2) da put) é a probabilidade RISCO-NEUTRA de
  exercício, não a probabilidade real.

A call americana entra aqui pela mesma fórmula europeia: a marca de
aproximação (ADR-0002) é responsabilidade de quem monta o resultado, e a
put americana nem chega a este módulo.
"""

from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from math import isfinite

from options_engine.domain.kernel.black_scholes import bs_outputs, bs_price, d1_d2
from options_engine.domain.kernel.distributions import norm_cdf
from options_engine.domain.kernel.implied_vol import ImpliedVolStatus, implied_vol
from options_engine.domain.model.chain import LegPremium, OptionQuote, PriceQuality
from options_engine.domain.model.enums import OptionType
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "SeriesMarket",
    "SeriesRisk",
    "SmilePoint",
    "VolSmile",
    "build_smile",
    "mid_implied_vol",
    "series_risk",
    "theoretical_premium",
]


@dataclass(frozen=True, slots=True)
class SeriesMarket:
    """Mercado comum às séries de um vencimento: spot, taxa contínua e tau (anos, BUS/252)."""

    spot: float
    rate_continuous: float
    tau: float

    def __post_init__(self) -> None:
        if not (isfinite(self.spot) and self.spot > 0.0):
            raise InvalidDomainValueError(f"spot deve ser finito e > 0; recebido {self.spot!r}")
        if not isfinite(self.rate_continuous):
            raise InvalidDomainValueError(
                f"taxa deve ser finita; recebido {self.rate_continuous!r}"
            )
        if not (isfinite(self.tau) and self.tau >= 0.0):
            raise InvalidDomainValueError(f"tau deve ser finito e >= 0; recebido {self.tau!r}")


@dataclass(frozen=True, slots=True)
class SmilePoint:
    """Um ponto do smile: strike, vol implícita (decimal, BUS/252) e a série que o gerou."""

    strike: float
    implied_vol: float
    symbol: str


@dataclass(frozen=True, slots=True)
class VolSmile:
    """Smile de UM vencimento: pontos com strikes estritamente crescentes e vol > 0."""

    expiry: date
    points: tuple[SmilePoint, ...]

    def __post_init__(self) -> None:
        strikes = [p.strike for p in self.points]
        if any(b <= a for a, b in pairwise(strikes)):
            raise InvalidDomainValueError(
                f"smile de {self.expiry.isoformat()} exige strikes estritamente crescentes; "
                f"recebido {strikes!r}"
            )
        for ponto in self.points:
            if not (isfinite(ponto.implied_vol) and ponto.implied_vol > 0.0):
                raise InvalidDomainValueError(
                    f"vol do ponto {ponto.symbol!r} deve ser finita e > 0; "
                    f"recebido {ponto.implied_vol!r}"
                )

    def vol_at(self, strike: float) -> float | None:
        """Vol linear em strike entre os vizinhos; fora do intervalo dos pontos, ``None``."""
        if not self.points:
            return None
        strikes = [p.strike for p in self.points]
        if not strikes[0] <= strike <= strikes[-1]:
            return None
        direita = bisect_left(strikes, strike)
        if strikes[direita] == strike:
            return self.points[direita].implied_vol
        esquerda = self.points[direita - 1]
        vizinho = self.points[direita]
        peso = (strike - esquerda.strike) / (vizinho.strike - esquerda.strike)
        return esquerda.implied_vol + peso * (vizinho.implied_vol - esquerda.implied_vol)


def mid_implied_vol(quote: OptionQuote, market: SeriesMarket) -> float | None:
    """Vol implícita do mid da série; ``None`` sem book completo, com tau = 0 ou sem solução > 0."""
    if quote.bid is None or quote.ask is None or market.tau == 0.0:
        return None
    termos = quote.contract.terms
    resultado = implied_vol(
        (quote.bid + quote.ask) / 2.0,
        market.spot,
        termos.strike,
        market.tau,
        market.rate_continuous,
        0.0,
        is_call=termos.option_type.is_call,
    )
    if resultado.status is not ImpliedVolStatus.CONVERGED or resultado.sigma is None:
        return None
    return resultado.sigma if resultado.sigma > 0.0 else None


def build_smile(expiry: date, quotes: Iterable[OptionQuote], market: SeriesMarket) -> VolSmile:
    """Smile do vencimento ``expiry`` a partir das séries com vol implícita pelo mid.

    Num strike com call e put, vale a fora do dinheiro; com duas séries do
    mesmo tipo e strike (tickers distintos), vale a de menor ticker —
    escolha determinística.
    """
    por_strike: dict[float, dict[OptionType, SmilePoint]] = {}
    for quote in sorted(quotes, key=lambda q: q.contract.symbol):
        termos = quote.contract.terms
        if termos.expiry != expiry:
            continue
        sigma = mid_implied_vol(quote, market)
        if sigma is None:
            continue
        tipos = por_strike.setdefault(termos.strike, {})
        tipos.setdefault(
            termos.option_type, SmilePoint(termos.strike, sigma, quote.contract.symbol)
        )
    pontos = []
    for strike in sorted(por_strike):
        tipos = por_strike[strike]
        fora = OptionType.PUT if strike < market.spot else OptionType.CALL
        pontos.append(tipos.get(fora) or next(iter(tipos.values())))
    return VolSmile(expiry=expiry, points=tuple(pontos))


def theoretical_premium(
    quote: OptionQuote, smile: VolSmile, market: SeriesMarket
) -> LegPremium | None:
    """Prêmio TEÓRICO da série elegível (book vazio, sem negócio) pela vol do smile.

    ``None`` se a série não é elegível ou se o strike está fora do smile.
    """
    if not quote.is_theoretical_eligible:
        return None
    termos = quote.contract.terms
    sigma = smile.vol_at(termos.strike)
    if sigma is None:
        return None
    preco = bs_price(
        market.spot,
        termos.strike,
        market.tau,
        market.rate_continuous,
        sigma,
        is_call=termos.option_type.is_call,
    )
    return LegPremium(preco, PriceQuality.TEORICO)


@dataclass(frozen=True, slots=True)
class SeriesRisk:
    """Vol, delta e probabilidade risco-neutra de exercício de uma série.

    ``implied_vol``: da própria série (mid), ``None`` se não houver;
    ``vol``: a usada no delta (a da série, senão a do smile; ``None`` com
    tau = 0, onde a vol não importa).
    """

    implied_vol: float | None
    vol: float | None
    delta: float
    exercise_probability: float


def series_risk(quote: OptionQuote, smile: VolSmile, market: SeriesMarket) -> SeriesRisk | None:
    """Delta e N(d2) (N(-d2) na put) com a vol da série, senão a do smile; sem vol -> ``None``.

    Tau = 0: delta é o degrau do kernel e a probabilidade é 1 dentro do
    dinheiro, 0 fora e 0,5 no dinheiro (mesma convenção do delta) — a vol
    não entra.
    """
    termos = quote.contract.terms
    is_call = termos.option_type.is_call
    if market.tau == 0.0:
        delta = bs_outputs(
            market.spot, termos.strike, 0.0, market.rate_continuous, 0.0, is_call=is_call
        ).delta
        return SeriesRisk(None, None, delta, abs(delta))
    propria = mid_implied_vol(quote, market)
    sigma = propria if propria is not None else smile.vol_at(termos.strike)
    if sigma is None:
        return None
    saidas = bs_outputs(
        market.spot, termos.strike, market.tau, market.rate_continuous, sigma, is_call=is_call
    )
    _, d2 = d1_d2(market.spot, termos.strike, market.tau, market.rate_continuous, sigma)
    probabilidade = norm_cdf(d2) if is_call else norm_cdf(-d2)
    return SeriesRisk(propria, sigma, saidas.delta, probabilidade)

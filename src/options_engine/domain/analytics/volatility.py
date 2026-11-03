"""Vol no prazo fixo, IV rank, percentil e regime de vol (spec da semana 3, §2.1).

A IV de 30 dias úteis interpola a variância total ``σ² x τ`` em τ, e não a vol: interpolar a vol
direto não preserva a variância acumulada entre os vencimentos.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum, unique
from math import isfinite, sqrt
from typing import Final

from options_engine.domain.model.conventions import DayCountConvention
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "HIGH_RANK",
    "HORIZON_BUSINESS_DAYS",
    "HV_MARGIN",
    "LOW_RANK",
    "MIN_EXPIRY_BUSINESS_DAYS",
    "RANK_MIN_SESSIONS",
    "RANK_WINDOW_SESSIONS",
    "DailyVol",
    "ExpiryVol",
    "HorizonVol",
    "VolContext",
    "VolRegime",
    "end_of_day_context",
    "iv_at_horizon",
    "iv_percentile",
    "iv_rank",
    "vol_context",
    "vol_regime",
]

HORIZON_BUSINESS_DAYS: Final = 30
MIN_EXPIRY_BUSINESS_DAYS: Final = 5
RANK_WINDOW_SESSIONS: Final = 252
RANK_MIN_SESSIONS: Final = 60
HIGH_RANK: Final = 0.50
LOW_RANK: Final = 0.30
HV_MARGIN: Final = 0.10

_DAYS_PER_YEAR: Final = DayCountConvention.BUSINESS_252.days_per_year


def _exige_vol(nome: str, valor: float) -> None:
    if not (isfinite(valor) and valor > 0.0):
        raise InvalidDomainValueError(f"{nome} deve ser finita e > 0; recebido {valor!r}")


@dataclass(frozen=True, slots=True)
class ExpiryVol:
    """Vol no dinheiro de um vencimento, a ``business_days`` dias úteis do pregão."""

    business_days: int
    vol: float

    def __post_init__(self) -> None:
        if self.business_days < 0:
            raise InvalidDomainValueError(
                f"dias úteis deve ser >= 0; recebido {self.business_days!r}"
            )
        _exige_vol("vol", self.vol)


@dataclass(frozen=True, slots=True)
class HorizonVol:
    """Vol no prazo pedido; ``extrapolated`` quando só havia vencimentos de um lado do prazo."""

    vol: float
    extrapolated: bool


@dataclass(frozen=True, slots=True)
class DailyVol:
    """Fechamento, IV de 30 dias úteis e HV de 21 de um pregão; ``None`` quando não deu para
    calcular (sem smile no spot, histórico curto)."""

    session: date
    close: float
    iv30: float | None
    extrapolated: bool
    hv21: float | None

    def __post_init__(self) -> None:
        _exige_vol("fechamento", self.close)
        if self.iv30 is not None:
            _exige_vol("IV 30", self.iv30)
        elif self.extrapolated:
            raise InvalidDomainValueError("IV 30 ausente não pode ser marcada como extrapolada")
        if self.hv21 is not None:
            _exige_vol("HV 21", self.hv21)


def iv_at_horizon(
    points: Sequence[ExpiryVol],
    horizon_days: int = HORIZON_BUSINESS_DAYS,
    min_days: int = MIN_EXPIRY_BUSINESS_DAYS,
) -> HorizonVol | None:
    """IV no prazo de ``horizon_days`` dias úteis; ``None`` se nenhum vencimento chega ao mínimo."""
    if horizon_days < 1 or min_days < 0:
        raise InvalidDomainValueError(
            f"prazo deve ser >= 1 e mínimo >= 0; recebido {horizon_days!r} e {min_days!r}"
        )
    validos = sorted(
        (p for p in points if p.business_days >= min_days), key=lambda p: p.business_days
    )
    dias = [p.business_days for p in validos]
    if len(set(dias)) != len(dias):
        raise InvalidDomainValueError(f"vencimentos repetidos nos dias úteis {dias!r}")
    if not validos:
        return None
    antes = [p for p in validos if p.business_days <= horizon_days]
    depois = [p for p in validos if p.business_days >= horizon_days]
    if antes and depois:
        curto, longo = antes[-1], depois[0]
        if curto is longo:
            return HorizonVol(curto.vol, extrapolated=False)
        tau_curto, tau_longo, tau = (
            d / _DAYS_PER_YEAR for d in (curto.business_days, longo.business_days, horizon_days)
        )
        w_curto, w_longo = curto.vol**2 * tau_curto, longo.vol**2 * tau_longo
        w = w_curto + (w_longo - w_curto) * (tau - tau_curto) / (tau_longo - tau_curto)
        return HorizonVol(sqrt(w / tau), extrapolated=False)
    mais_perto = antes[-1] if antes else depois[0]
    return HorizonVol(mais_perto.vol, extrapolated=True)


def _janela(history: Sequence[float], today: float) -> list[float] | None:
    _exige_vol("IV de hoje", today)
    for valor in history:
        _exige_vol("IV do histórico", valor)
    janela = list(history[-RANK_WINDOW_SESSIONS:])
    return janela if len(janela) >= RANK_MIN_SESSIONS else None


def iv_rank(history: Sequence[float], today: float) -> float | None:
    """``(hoje - mínima) / (máxima - mínima)`` nos últimos 252 pregões com IV, hoje incluído.

    ``None`` com menos de 60 pregões ou com a janela inteira na mesma IV.
    """
    janela = _janela(history, today)
    if janela is None:
        return None
    minima, maxima = min(*janela, today), max(*janela, today)
    if maxima == minima:
        return None
    return (today - minima) / (maxima - minima)


def iv_percentile(history: Sequence[float], today: float) -> float | None:
    """Fração dos últimos 252 pregões com IV abaixo da de hoje; ``None`` com menos de 60."""
    janela = _janela(history, today)
    if janela is None:
        return None
    return sum(1 for valor in janela if valor < today) / len(janela)


@unique
class VolRegime(Enum):
    ALTA = "alta"
    BAIXA = "baixa"
    NEUTRA = "neutra"


def vol_regime(iv: float, hv: float, rank: float | None) -> tuple[VolRegime, bool]:
    """Regime da vol e se ele veio só da IV contra a HV (sem rank, pela margem de 10%)."""
    _exige_vol("IV", iv)
    _exige_vol("HV", hv)
    if rank is None:
        if iv > (1.0 + HV_MARGIN) * hv:
            return VolRegime.ALTA, True
        if iv < (1.0 - HV_MARGIN) * hv:
            return VolRegime.BAIXA, True
        return VolRegime.NEUTRA, True
    if not (isfinite(rank) and 0.0 <= rank <= 1.0):
        raise InvalidDomainValueError(f"IV rank deve estar em [0, 1]; recebido {rank!r}")
    if rank >= HIGH_RANK and iv >= hv:
        return VolRegime.ALTA, False
    if rank <= LOW_RANK and iv <= hv:
        return VolRegime.BAIXA, False
    return VolRegime.NEUTRA, False


@dataclass(frozen=True, slots=True)
class VolContext:
    """IV 30 e HV 21 de um ativo, o rank e o percentil da IV contra o histórico, e o regime;
    ``regime_from_hv`` quando não havia rank e o regime saiu da margem sobre a HV."""

    underlying: str
    iv30: float
    hv21: float
    iv_rank: float | None
    iv_percentile: float | None
    regime: VolRegime
    regime_from_hv: bool
    extrapolated: bool = False


def vol_context(
    underlying: str,
    iv30: float,
    hv21: float,
    history: Sequence[float],
    *,
    extrapolated: bool = False,
) -> VolContext:
    """Contexto da IV de hoje contra ``history`` (as IVs dos pregões anteriores, em ordem)."""
    rank = iv_rank(history, iv30)
    regime, from_hv = vol_regime(iv30, hv21, rank)
    return VolContext(
        underlying,
        iv30,
        hv21,
        rank,
        iv_percentile(history, iv30),
        regime,
        from_hv,
        extrapolated,
    )


def end_of_day_context(underlying: str, history: Sequence[DailyVol]) -> VolContext | str:
    """Contexto do último pregão do histórico contra os anteriores; senão o motivo."""
    if not history:
        return f"{underlying}: sem histórico de IV"
    hoje = history[-1]
    dia = hoje.session.isoformat()
    if hoje.iv30 is None:
        return f"{underlying}: sem IV 30 no pregão {dia} (sem smile no spot)"
    if hoje.hv21 is None:
        return f"{underlying}: sem HV 21 no pregão {dia} (histórico curto)"
    anteriores = [d.iv30 for d in history[:-1] if d.iv30 is not None]
    return vol_context(underlying, hoje.iv30, hoje.hv21, anteriores, extrapolated=hoje.extrapolated)

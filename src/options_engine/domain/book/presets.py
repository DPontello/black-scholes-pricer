"""Presets do book (spec da semana 3, §3.2), salvos no perfil com os valores editados."""

from dataclasses import dataclass
from enum import Enum, unique
from math import isfinite

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["BookPreset", "BookSettings"]


@unique
class BookPreset(Enum):
    CONSERVADOR = "conservador"
    MODERADO = "moderado"
    ARROJADO = "arrojado"


@dataclass(frozen=True, slots=True)
class BookSettings:
    """Filtros do book; ``max_spread_pct`` e ``protection_floor`` em decimal (0.20 == 20%).

    ``max_risk`` (R$) vale só nas estruturas sem ação; ``protection_floor`` é a fração do spot
    abaixo da qual a proteção não serve.
    """

    preset: BookPreset
    delta_min: float
    delta_max: float
    min_trades: int
    max_spread_pct: float
    max_risk: float
    expiries: int
    protection_floor: float
    allow_unlimited_loss: bool

    def __post_init__(self) -> None:
        if not (0.0 <= self.delta_min <= self.delta_max <= 1.0):
            raise InvalidDomainValueError(
                f"faixa de delta exige 0 <= mínimo <= máximo <= 1; recebido "
                f"{self.delta_min!r} a {self.delta_max!r}"
            )
        if self.min_trades < 0:
            raise InvalidDomainValueError(
                f"negócios mínimos deve ser >= 0; recebido {self.min_trades!r}"
            )
        if self.expiries < 1:
            raise InvalidDomainValueError(f"vencimentos deve ser >= 1; recebido {self.expiries!r}")
        for nome, valor in (
            ("spread máximo", self.max_spread_pct),
            ("risco máximo", self.max_risk),
        ):
            if not (isfinite(valor) and valor > 0.0):
                raise InvalidDomainValueError(f"{nome} deve ser finito e > 0; recebido {valor!r}")
        if not (isfinite(self.protection_floor) and 0.0 < self.protection_floor <= 1.0):
            raise InvalidDomainValueError(
                f"piso da proteção deve estar em (0, 1]; recebido {self.protection_floor!r}"
            )

    @classmethod
    def default(cls, preset: BookPreset) -> "BookSettings":
        return _DEFAULTS[preset]


_DEFAULTS = {
    BookPreset.CONSERVADOR: BookSettings(
        BookPreset.CONSERVADOR, 0.10, 0.25, 20, 0.10, 1_000.0, 2, 0.95, False
    ),
    BookPreset.MODERADO: BookSettings(
        BookPreset.MODERADO, 0.15, 0.35, 10, 0.20, 3_000.0, 2, 0.90, False
    ),
    BookPreset.ARROJADO: BookSettings(
        BookPreset.ARROJADO, 0.25, 0.45, 3, 0.35, 10_000.0, 3, 0.85, True
    ),
}

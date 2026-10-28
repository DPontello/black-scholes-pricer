"""Perfil do usuário do app: nome, watchlist e CDI.

O perfil é dado do usuário, não do mercado: vive numa pasta que o usuário
escolhe (nuvem, pendrive) e viaja entre PCs. Este módulo só diz o que é um
perfil válido — onde ele fica e quem o trava é dos adapters.
"""

from collections import Counter
from dataclasses import dataclass
from math import isfinite

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["Profile", "ProfileEntry", "normalize_ticker"]

_NOME_MAX = 40


def normalize_ticker(raw: str) -> str:
    """Ticker em maiúsculas, sem espaços nas pontas; só letras e dígitos ASCII.

    ``isascii`` porque ``str.isalnum`` aceita letras de qualquer alfabeto
    (``"É"``), e ticker da B3 é sempre ASCII.
    """
    ticker = raw.strip()
    if not (ticker and ticker.isascii() and ticker.isalnum()):
        raise InvalidDomainValueError(
            f"ticker deve ter só letras e dígitos (ASCII) e não ser vazio; recebido {raw!r}"
        )
    return ticker.upper()


@dataclass(frozen=True, slots=True)
class Profile:
    """Nome, watchlist e CDI anual de um perfil.

    ``watchlist`` guarda tickers JÁ normalizados (``normalize_ticker``) e sem
    repetição: o VO não normaliza em silêncio, rejeita — quem monta o perfil
    (API, leitura do arquivo) normaliza antes, e assim o que está salvo é
    igual ao que foi mostrado. ``cdi_annual`` é fração anual (0.15 = 15% a.a.)
    e fica em ``0 <= cdi < 1``.
    """

    name: str
    watchlist: tuple[str, ...]
    cdi_annual: float

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip() or len(self.name) > _NOME_MAX:
            raise InvalidDomainValueError(
                f"nome do perfil deve ser não vazio, sem espaços nas pontas e ter até "
                f"{_NOME_MAX} caracteres; recebido {self.name!r}"
            )
        for ticker in self.watchlist:
            if normalize_ticker(ticker) != ticker:
                raise InvalidDomainValueError(
                    f"ticker da watchlist deve vir normalizado "
                    f"({normalize_ticker(ticker)!r}); recebido {ticker!r}"
                )
        contagem = Counter(self.watchlist)
        repetidos = sorted(ticker for ticker, vezes in contagem.items() if vezes > 1)
        if repetidos:
            raise InvalidDomainValueError(
                f"watchlist do perfil {self.name!r} repete tickers: {repetidos!r}"
            )
        # Forma negada: NaN falha em qualquer comparação e passaria por um
        # `cdi < 0.0 or cdi >= 1.0`.
        if not (isfinite(self.cdi_annual) and 0.0 <= self.cdi_annual < 1.0):
            raise InvalidDomainValueError(
                f"cdi_annual deve ser finito e 0 <= cdi < 1 (fração anual); "
                f"recebido {self.cdi_annual!r}"
            )


@dataclass(frozen=True, slots=True)
class ProfileEntry:
    """Perfil conhecido pelo app: nome e a pasta onde ele mora."""

    name: str
    folder: str

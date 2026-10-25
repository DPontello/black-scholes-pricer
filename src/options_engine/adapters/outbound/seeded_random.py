"""Fonte de aleatoriedade seedável — ``random.Random(seed)`` stdlib, encapsulado.

Seed OBRIGATÓRIA no construtor, sem default (CONVENTIONS §7): mesma seed ⇒
sequência bit a bit idêntica; seed implícita seria não-determinismo
disfarçado de conveniência. O ``random`` global do módulo é proibido —
estado compartilhado escondido acopla testes entre si e quebra o
determinismo na primeira execução paralela.
"""

from math import isfinite
from random import Random

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["SeededRandomSource"]


class SeededRandomSource:
    """Implementação stdlib do port ``RandomSource``.

    Um ``Random`` PRÓPRIO por instância: duas fontes com seeds distintas são
    fluxos independentes por construção, sem interferência mútua.
    """

    def __init__(self, seed: int) -> None:
        self._random = Random(seed)

    def gaussians(self, n: int) -> tuple[float, ...]:
        """``n`` amostras N(0, 1) — o bloco de construção do GBM (e do MC futuro)."""
        if n < 0:
            raise InvalidDomainValueError(f"n deve ser >= 0; recebido {n!r}")
        return tuple(self._random.gauss(0.0, 1.0) for _ in range(n))

    def uniform(self, low: float, high: float) -> float:
        """Amostra uniforme em ``[low, high]``."""
        if not (isfinite(low) and isfinite(high)):
            raise InvalidDomainValueError(
                f"extremos devem ser finitos; recebido low={low!r}, high={high!r}"
            )
        if not (low <= high):
            raise InvalidDomainValueError(
                f"exigido low <= high; recebido low={low!r}, high={high!r}"
            )
        return self._random.uniform(low, high)

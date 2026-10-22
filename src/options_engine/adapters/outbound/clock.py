"""Relógios concretos — ``SystemClock`` (produção) e ``FixedClock`` (determinismo).

O contrato do port ``Clock`` exige tz-aware sempre (UTC interno; conversão
nas bordas — ARCH §4.1). ``datetime.now()`` nu espalhado pelo código é o
assassino nº 1 de testes de pricing; este módulo é o ÚNICO lugar autorizado
a chamá-lo (CONVENTIONS §7).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["FixedClock", "SystemClock"]


class SystemClock:
    """Relógio de produção: o agora em UTC, sempre tz-aware."""

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Relógio congelado num instante — smoke reprodutível e reprocessamento.

    Não é um fake escondido de teste: data de valoração fixa é requisito do
    smoke executável (ROADMAP S3 — saída reprodutível dada a seed) e de
    qualquer reavaliação auditável de uma posição em data passada.
    """

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None or self.instant.tzinfo.utcoffset(self.instant) is None:
            raise InvalidDomainValueError(
                f"Clock é tz-aware por contrato (ARCH §4.1); recebido {self.instant!r}"
            )

    def now(self) -> datetime:
        return self.instant

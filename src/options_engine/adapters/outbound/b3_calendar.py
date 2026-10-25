"""Calendário estático de dias úteis da B3 — arquivo versionado (decisão nº 7).

Implementa o port ``TradingCalendar`` com a lista de feriados empacotada em
``data/b3_holidays.csv`` (uma data ISO por linha; fonte e data de
verificação no cabeçalho do próprio arquivo). Atualizar o calendário =
editar o CSV + estender a cobertura — nunca tocar em código.

Guarda de COBERTURA: consultar fora do intervalo coberto levanta exceção em
vez de contar um feriado inexistente como dia útil — um calendário que
responde errado em silêncio produz tau errado e preço errado sem nenhum
sinal de runtime.
"""

from collections.abc import Iterable
from datetime import date, timedelta, timezone
from importlib import resources

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["B3_UTC_OFFSET", "StaticHolidayCalendar"]

# Fuso de valoração da B3: UTC-3 FIXO — o horário de verão brasileiro foi
# abolido em 2019 (Decreto 9.772), então um offset constante é correto e
# dispensa tzdata. É a constante que o composition root injeta como
# ``valuation_timezone`` dos services.
B3_UTC_OFFSET = timezone(timedelta(hours=-3), name="America/Sao_Paulo (UTC-3 fixo)")

# Cobertura da lista empacotada — DEVE casar com o cabeçalho do CSV.
_PACKAGED_COVERAGE_START = date(2024, 1, 1)
_PACKAGED_COVERAGE_END = date(2027, 12, 31)

_SATURDAY = 5  # date.weekday(): 5 = sábado, 6 = domingo


class StaticHolidayCalendar:
    """Implementação estática do port ``TradingCalendar``.

    Contrato do port (ARCH §4.1): intervalo MEIO-ABERTO ``[start, end)`` —
    ``start == end`` → 0 (no dia do vencimento resta 0 dia útil, decisão
    nº 5); ``start > end`` → ``InvalidDomainValueError``.
    """

    def __init__(
        self,
        holidays: Iterable[date],
        *,
        coverage_start: date,
        coverage_end: date,
    ) -> None:
        if coverage_start > coverage_end:
            raise InvalidDomainValueError(
                f"cobertura invertida: [{coverage_start}, {coverage_end}]"
            )
        self._holidays = frozenset(holidays)
        fora = sorted(d for d in self._holidays if not coverage_start <= d <= coverage_end)
        if fora:
            raise InvalidDomainValueError(
                f"feriados fora da cobertura declarada [{coverage_start}, {coverage_end}]: "
                f"{[d.isoformat() for d in fora]!r} — a cobertura é uma promessa, não decoração"
            )
        self._coverage_start = coverage_start
        self._coverage_end = coverage_end

    @classmethod
    def from_packaged_data(cls) -> "StaticHolidayCalendar":
        """Calendário com a lista de feriados B3 empacotada no wheel."""
        csv = resources.files("options_engine.adapters.outbound").joinpath("data/b3_holidays.csv")
        holidays = []
        for raw_line in csv.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            holidays.append(date.fromisoformat(line))
        return cls(
            holidays,
            coverage_start=_PACKAGED_COVERAGE_START,
            coverage_end=_PACKAGED_COVERAGE_END,
        )

    def business_days_between(self, start: date, end: date) -> int:
        """Dias úteis d com ``start <= d < end`` (meio-aberto, ARCH §4.1)."""
        if start > end:
            raise InvalidDomainValueError(
                f"contagem negativa não tem semântica; recebido [{start}, {end}) — "
                f"opção vencida é guarda do use case (ExpiredOptionError), nunca daqui"
            )
        if start < self._coverage_start or end > self._coverage_end:
            raise InvalidDomainValueError(
                f"consulta [{start}, {end}) fora da cobertura do calendário "
                f"[{self._coverage_start}, {self._coverage_end}] — responder contaria "
                f"feriado desconhecido como dia útil; estenda o CSV empacotado"
            )
        count = 0
        day = start
        while day < end:
            if day.weekday() < _SATURDAY and day not in self._holidays:
                count += 1
            day += timedelta(days=1)
        return count

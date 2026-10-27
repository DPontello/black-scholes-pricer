"""Tabelas de custos versionadas — arquivo empacotado (ADR-0005), mesmo padrão do calendário.

``data/cost_schedules.csv`` traz uma tabela por vigência, com a origem de
cada número no próprio arquivo (comentários e coluna ``fonte``). Atualizar
custos = acrescentar uma linha com a nova ``valid_from``; a escolha da
tabela vigente numa data é a função pura ``schedule_on`` do domínio.
"""

import csv
from collections.abc import Iterable
from datetime import date
from importlib import resources
from typing import Final

from options_engine.domain.income.costs import CostSchedule, schedule_on

__all__ = ["StaticCostScheduleTable"]

_COLUMNS: Final = (
    "valid_from",
    "option_exchange_fee_rate",
    "spot_exchange_fee_rate",
    "brokerage_per_order",
    "exercise_brokerage_per_order",
    "income_tax_rate",
)


class StaticCostScheduleTable:
    """Sequência de ``CostSchedule`` em ordem de vigência, com a tabela vigente por data."""

    def __init__(self, schedules: Iterable[CostSchedule]) -> None:
        self._schedules = tuple(sorted(schedules, key=lambda s: s.valid_from))

    @classmethod
    def from_csv_text(cls, text: str) -> "StaticCostScheduleTable":
        """Lê o CSV (comentários com ``#``); coluna faltando -> ``ValueError`` com o nome."""
        linhas = [
            linha for linha in text.splitlines() if linha.strip() and not linha.startswith("#")
        ]
        leitor = csv.DictReader(linhas)
        faltando = [c for c in _COLUMNS if c not in (leitor.fieldnames or ())]
        if faltando:
            raise ValueError(f"tabela de custos sem as colunas {faltando!r}")
        return cls(
            CostSchedule(
                valid_from=date.fromisoformat(linha["valid_from"].strip()),
                option_exchange_fee_rate=float(linha["option_exchange_fee_rate"]),
                spot_exchange_fee_rate=float(linha["spot_exchange_fee_rate"]),
                brokerage_per_order=float(linha["brokerage_per_order"]),
                exercise_brokerage_per_order=float(linha["exercise_brokerage_per_order"]),
                income_tax_rate=float(linha["income_tax_rate"]),
            )
            for linha in leitor
        )

    @classmethod
    def from_packaged_data(cls) -> "StaticCostScheduleTable":
        """A tabela empacotada no wheel (``data/cost_schedules.csv``)."""
        arquivo = resources.files("options_engine.adapters.outbound").joinpath(
            "data/cost_schedules.csv"
        )
        return cls.from_csv_text(arquivo.read_text(encoding="utf-8"))

    @property
    def schedules(self) -> tuple[CostSchedule, ...]:
        return self._schedules

    def on(self, day: date) -> CostSchedule:
        """A tabela vigente em ``day`` (``schedule_on``)."""
        return schedule_on(self._schedules, day)

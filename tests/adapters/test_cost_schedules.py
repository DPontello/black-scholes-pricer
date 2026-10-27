"""Tabela de custos empacotada e a escolha da tabela vigente por data (ADR-0005)."""

from datetime import date

import pytest

from options_engine.adapters.outbound.cost_schedules import StaticCostScheduleTable
from options_engine.domain.income import CostSchedule, schedule_on
from options_engine.domain.model.errors import InvalidDomainValueError
from tests.income._builders import make_cost_schedule

_CABECALHO = (
    "valid_from,option_exchange_fee_rate,spot_exchange_fee_rate,"
    "brokerage_per_order,exercise_brokerage_per_order,income_tax_rate,fonte"
)


def test_tabela_empacotada_e_a_linha_da_mesa() -> None:
    """Linha inicial decidida pela mesa: vigência 2025-08-01 e os valores do spike."""
    tabela = StaticCostScheduleTable.from_packaged_data()
    (unica,) = tabela.schedules
    assert unica == CostSchedule(
        valid_from=date(2025, 8, 1),
        option_exchange_fee_rate=0.00134,
        spot_exchange_fee_rate=0.0003,
        brokerage_per_order=0.0,
        exercise_brokerage_per_order=0.0,
        income_tax_rate=0.15,
    )
    assert tabela.on(date(2026, 10, 23)) == unica


def test_vigente_e_a_de_maior_valid_from_ate_a_data() -> None:
    texto = "\n".join(
        [
            "# comentário",
            _CABECALHO,
            "2025-08-01,0.00134,0.0003,0,0,0.15,a",
            "2026-11-01,0.00140,0.0003,0,0,0.175,b",
        ]
    )
    tabela = StaticCostScheduleTable.from_csv_text(texto)
    assert tabela.on(date(2026, 10, 31)).income_tax_rate == 0.15
    assert tabela.on(date(2026, 11, 1)).income_tax_rate == 0.175


def test_antes_da_primeira_vigencia_e_erro_de_dominio() -> None:
    with pytest.raises(
        InvalidDomainValueError, match="nenhuma tabela de custos vigente em 2025-07-31"
    ):
        StaticCostScheduleTable.from_packaged_data().on(date(2025, 7, 31))


def test_sem_tabela_alguma_e_erro_de_dominio() -> None:
    with pytest.raises(InvalidDomainValueError, match="nenhuma tabela"):
        schedule_on((), date(2026, 10, 23))


def test_duas_tabelas_com_a_mesma_vigencia_sao_ambiguas() -> None:
    a = make_cost_schedule(valid_from=date(2026, 1, 2))
    b = make_cost_schedule(valid_from=date(2026, 1, 2), income_tax_rate=0.2)
    with pytest.raises(InvalidDomainValueError, match="mesma vigência"):
        schedule_on((a, b), date(2026, 10, 23))


def test_coluna_faltando_e_apontada() -> None:
    with pytest.raises(ValueError, match="income_tax_rate"):
        StaticCostScheduleTable.from_csv_text("valid_from,option_exchange_fee_rate\n2025-08-01,0.1")

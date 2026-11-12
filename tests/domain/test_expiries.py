"""Vencimentos listados e a escolha padrão (o mais próximo e o próximo mensal)."""

from datetime import date

import pytest

from options_engine.domain.model.expiries import (
    ListedExpiry,
    default_expiries,
    is_weekly_series,
    list_expiries,
)

HOJE = date(2026, 10, 28)
W5 = date(2026, 10, 30)
W1 = date(2026, 11, 6)
NOVEMBRO = date(2026, 11, 19)
DEZEMBRO = date(2026, 12, 18)


@pytest.mark.parametrize(
    ("ticker", "semanal"),
    [
        ("PETRK380W1", True),
        ("BOVAJ137W5", True),
        ("PETRW30W2", True),
        ("PETRK1", False),
        ("PETRK526", False),
        ("PETRW300", False),  # put de novembro: o W é a letra da série
        ("WEGEK400", False),
        ("PETR4", False),
    ],
)
def test_semanal_pelo_w_e_a_semana_no_fim_do_ticker(ticker: str, semanal: bool) -> None:
    assert is_weekly_series(ticker) is semanal


def test_lista_ordenada_sem_vencidos_e_semanal_so_se_todas_as_series_sao() -> None:
    series = [
        ("PETRK300", NOVEMBRO),
        ("PETRJ300W5", W5),
        ("PETRJ290", date(2026, 10, 16)),
        ("PETRL300", DEZEMBRO),
        ("PETRK380W1", W1),
        ("PETRW300", NOVEMBRO),
        ("PETRK390W1", W1),
    ]
    assert list_expiries(series, HOJE) == (
        ListedExpiry(W5, weekly=True),
        ListedExpiry(W1, weekly=True),
        ListedExpiry(NOVEMBRO, weekly=False),
        ListedExpiry(DEZEMBRO, weekly=False),
    )
    assert list_expiries([("PETRJ300W5", W5), ("PETRJ300", W5)], HOJE) == (
        ListedExpiry(W5, weekly=False),
    )


def test_padrao_e_o_mais_proximo_e_o_proximo_mensal() -> None:
    listados = list_expiries(
        [("PETRJ300W5", W5), ("PETRK380W1", W1), ("PETRK300", NOVEMBRO), ("PETRL300", DEZEMBRO)],
        HOJE,
    )
    assert default_expiries(listados) == {W5, NOVEMBRO}
    assert default_expiries(listados[2:]) == {NOVEMBRO}
    assert default_expiries(listados[:2]) == {W5}  # sem mensal: só o mais próximo
    assert default_expiries(()) == frozenset()

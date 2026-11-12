"""Presets do book com os valores da spec da semana 3 (§3.2) e a validação das faixas."""

from dataclasses import replace
from typing import Any

import pytest

from options_engine.domain.book.presets import BookPreset, BookSettings
from options_engine.domain.model.errors import InvalidDomainValueError


def test_os_tres_presets_tem_os_valores_da_spec() -> None:
    assert BookSettings.default(BookPreset.CONSERVADOR) == BookSettings(
        BookPreset.CONSERVADOR, 0.10, 0.25, 20, 0.10, 1_000.0, 2, 0.95, False
    )
    assert BookSettings.default(BookPreset.MODERADO) == BookSettings(
        BookPreset.MODERADO, 0.15, 0.35, 10, 0.20, 3_000.0, 2, 0.90, False
    )
    assert BookSettings.default(BookPreset.ARROJADO) == BookSettings(
        BookPreset.ARROJADO, 0.25, 0.45, 3, 0.35, 10_000.0, 3, 0.85, True
    )


def test_valores_editados_continuam_no_preset_escolhido() -> None:
    editado = replace(BookSettings.default(BookPreset.MODERADO), min_trades=50)
    assert (editado.preset, editado.min_trades) == (BookPreset.MODERADO, 50)


@pytest.mark.parametrize(
    "campos",
    [
        {"delta_min": -0.01},
        {"delta_max": 1.01},
        {"delta_min": 0.40, "delta_max": 0.30},
        {"min_trades": -1},
        {"expiries": 0},
        {"max_spread_pct": 0.0},
        {"max_spread_pct": float("nan")},
        {"max_risk": 0.0},
        {"max_risk": float("inf")},
        {"protection_floor": 0.0},
        {"protection_floor": 1.01},
    ],
)
def test_valores_invalidos_sao_recusados(campos: dict[str, Any]) -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(BookSettings.default(BookPreset.MODERADO), **campos)

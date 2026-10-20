"""VOs de cenário — invariantes de especificação e de relatório."""

import pytest

from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.scenarios import (
    ScenarioGrid,
    ScenarioOutcome,
    SpotAxis,
    StressGridResult,
    StressScenario,
    StressTestReport,
)
from tests.domain._builders import make_snapshot

# ---------------------------------------------------------------------------
# StressScenario
# ---------------------------------------------------------------------------


def test_cenario_neutro_por_default() -> None:
    """Sem choque explícito, o cenário é a identidade (spot x1, shifts 0)."""
    cenario = StressScenario(label="base")
    assert (cenario.spot_shift, cenario.vol_shift, cenario.rate_shift) == (1.0, 0.0, 0.0)


def test_cenario_de_crise_carrega_unidades_canonicas() -> None:
    """-20% de spot é multiplicativo (0.8); +10 pontos de vol é aditivo
    decimal (0.10) — unidades do CONVENTIONS, não percentuais soltos."""
    crise = StressScenario(label="crise", spot_shift=0.80, vol_shift=0.10, rate_shift=0.02)
    assert crise.spot_shift == 0.80
    assert crise.vol_shift == 0.10


def test_label_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        StressScenario(label="")


@pytest.mark.parametrize("spot_shift", [0.0, -0.5, float("nan"), float("inf")])
def test_spot_shift_ilegal_e_irrepresentavel(spot_shift: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        StressScenario(label="x", spot_shift=spot_shift)


def test_shifts_nao_finitos_sao_irrepresentaveis() -> None:
    with pytest.raises(InvalidDomainValueError):
        StressScenario(label="x", vol_shift=float("nan"))
    with pytest.raises(InvalidDomainValueError):
        StressScenario(label="x", rate_shift=float("inf"))


# ---------------------------------------------------------------------------
# ScenarioGrid
# ---------------------------------------------------------------------------


def _grid_valido(**overrides: float | int) -> ScenarioGrid:
    campos: dict[str, float | int] = {
        "spot_min": 24.0,
        "spot_max": 36.0,
        "spot_steps": 13,
        "vol_min": 0.15,
        "vol_max": 0.45,
        "vol_steps": 7,
    }
    campos.update(overrides)
    return ScenarioGrid(**campos)  # type: ignore[arg-type]  # dict heterogêneo é detalhe do builder


def test_grid_valido() -> None:
    grid = _grid_valido()
    assert grid.spot_steps == 13
    assert grid.vol_steps == 7


@pytest.mark.parametrize(
    "overrides",
    [
        {"spot_min": 0.0},  # spot precisa ser > 0
        {"spot_min": 40.0},  # min > max
        {"spot_steps": 0},
        {"vol_min": -0.1},  # vol >= 0
        {"vol_min": 0.5},  # min > max
        {"vol_steps": -1},
        {"spot_steps": 1},  # eixo degenerado exige min == max
        {"spot_max": float("nan")},
    ],
)
def test_especificacao_ilegal_e_irrepresentavel(overrides: dict[str, float | int]) -> None:
    with pytest.raises(InvalidDomainValueError):
        _grid_valido(**overrides)


def test_eixo_degenerado_com_min_igual_max_e_legal() -> None:
    """Grid 1D (vol fixa) é caso de uso legítimo: payoff só varia em spot."""
    grid = _grid_valido(vol_min=0.25, vol_max=0.25, vol_steps=1)
    assert grid.vol_steps == 1


# ---------------------------------------------------------------------------
# StressGridResult
# ---------------------------------------------------------------------------


def _resultado_valido() -> StressGridResult:
    grid = _grid_valido(spot_steps=3, vol_steps=2, vol_min=0.2, vol_max=0.3)
    return StressGridResult(
        grid=grid,
        spots=(24.0, 30.0, 36.0),
        vols=(0.2, 0.3),
        values=((1.0, 1.1), (0.5, 0.6), (-0.2, -0.1)),
    )


def test_resultado_coerente_com_a_especificacao() -> None:
    resultado = _resultado_valido()
    assert resultado.values[2][1] == -0.1  # values[spot][vol]


def test_eixos_incoerentes_com_o_grid_sao_rejeitados() -> None:
    valido = _resultado_valido()
    with pytest.raises(InvalidDomainValueError):
        StressGridResult(
            grid=valido.grid, spots=(24.0, 30.0), vols=valido.vols, values=valido.values[:2]
        )


def test_linha_com_largura_errada_e_rejeitada() -> None:
    valido = _resultado_valido()
    with pytest.raises(InvalidDomainValueError):
        StressGridResult(
            grid=valido.grid,
            spots=valido.spots,
            vols=valido.vols,
            values=((1.0, 1.1), (0.5,), (-0.2, -0.1)),
        )


def test_celula_nao_finita_e_rejeitada() -> None:
    """Decisão nº 5 na prática: posição vencida vira intrínseco descontado,
    nunca NaN — um buraco no grid é bug, não dado."""
    valido = _resultado_valido()
    with pytest.raises(InvalidDomainValueError):
        StressGridResult(
            grid=valido.grid,
            spots=valido.spots,
            vols=valido.vols,
            values=((1.0, 1.1), (0.5, float("nan")), (-0.2, -0.1)),
        )


def test_numero_de_linhas_diferente_dos_spots_e_rejeitado() -> None:
    valido = _resultado_valido()
    with pytest.raises(InvalidDomainValueError):
        StressGridResult(
            grid=valido.grid,
            spots=valido.spots,
            vols=valido.vols,
            values=((1.0, 1.1), (0.5, 0.6)),  # 2 linhas para 3 spots
        )


# ---------------------------------------------------------------------------
# SpotAxis
# ---------------------------------------------------------------------------


def test_spot_axis_valido() -> None:
    axis = SpotAxis(spot_min=24.0, spot_max=36.0, steps=13)
    assert (axis.spot_min, axis.spot_max, axis.steps) == (24.0, 36.0, 13)


@pytest.mark.parametrize(
    ("spot_min", "spot_max", "steps"),
    [
        (0.0, 36.0, 13),  # spot precisa ser > 0
        (-1.0, 36.0, 13),
        (40.0, 36.0, 13),  # min > max
        (24.0, 36.0, 0),
        (24.0, 36.0, 1),  # eixo degenerado exige min == max
        (24.0, float("nan"), 13),
        (float("inf"), 36.0, 13),
    ],
)
def test_spot_axis_ilegal_e_irrepresentavel(spot_min: float, spot_max: float, steps: int) -> None:
    with pytest.raises(InvalidDomainValueError):
        SpotAxis(spot_min=spot_min, spot_max=spot_max, steps=steps)


def test_spot_axis_degenerado_com_min_igual_max_e_legal() -> None:
    """Amostrar um único spot é caso legítimo — espelho do contrato de linspace."""
    axis = SpotAxis(spot_min=30.0, spot_max=30.0, steps=1)
    assert axis.steps == 1


# ---------------------------------------------------------------------------
# ScenarioOutcome e StressTestReport
# ---------------------------------------------------------------------------

TTX_252 = TimeToExpiry(0.5, DayCountConvention.BUSINESS_252)


def _outcome(label: str, value: float = 1.0) -> ScenarioOutcome:
    return ScenarioOutcome(scenario=StressScenario(label=label), value=value)


def _report_valido(
    outcomes: tuple[ScenarioOutcome, ...] | None = None,
    base_value: float = 2.0,
    strategy_name: str = "iron condor vendido (crédito)",
) -> StressTestReport:
    return StressTestReport(
        strategy_name=strategy_name,
        base_snapshot=make_snapshot(),
        time_to_expiry=TTX_252,
        base_value=base_value,
        outcomes=(
            outcomes if outcomes is not None else (_outcome("crise", 0.5), _outcome("alta", 2.6))
        ),
    )


def test_outcome_carrega_cenario_e_valor() -> None:
    outcome = _outcome("crise", 0.5)
    assert outcome.scenario.label == "crise"
    assert outcome.value == 0.5


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_outcome_nao_finito_e_irrepresentavel(value: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        _outcome("crise", value)


def test_report_valido_e_variacao_derivada() -> None:
    """A variação contra a base é MÉTODO, nunca campo — sem dupla fonte de verdade."""
    report = _report_valido(base_value=2.0)
    assert report.change_from_base(report.outcomes[0]) == 0.5 - 2.0
    assert report.change_from_base(report.outcomes[1]) == 2.6 - 2.0


def test_report_sem_cenarios_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        _report_valido(outcomes=())


def test_report_com_labels_duplicados_e_irrepresentavel() -> None:
    """Label é a chave de rastreabilidade do relatório — duplicado é ambíguo."""
    with pytest.raises(InvalidDomainValueError):
        _report_valido(outcomes=(_outcome("crise", 0.5), _outcome("crise", 0.6)))


def test_report_com_nome_vazio_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError):
        _report_valido(strategy_name="")


@pytest.mark.parametrize("base_value", [float("nan"), float("inf")])
def test_report_com_base_nao_finita_e_irrepresentavel(base_value: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        _report_valido(base_value=base_value)


def test_report_e_imutavel() -> None:
    report = _report_valido()
    with pytest.raises(AttributeError):
        report.base_value = 0.0  # type: ignore[misc]

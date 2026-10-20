"""Cenários de estresse — choques nomeados, eixos e especificações de grid.

Separação deliberada (ARCH §2.1/§5): o VO é a ESPECIFICAÇÃO declarativa,
barata e auditável; a MATERIALIZAÇÃO (floats, malha uniforme) pertence ao
kernel (``linspace``) e é orquestrada pelo motor de simulação.
"""

from dataclasses import dataclass
from math import isfinite

from options_engine.domain.model.conventions import TimeToExpiry
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.market import MarketSnapshot

__all__ = [
    "ScenarioGrid",
    "ScenarioOutcome",
    "SpotAxis",
    "StressGridResult",
    "StressScenario",
    "StressTestReport",
]


def _validar_eixo(nome: str, lo: float, hi: float, steps: int, *, minimo_exclusivo: bool) -> None:
    """Regras comuns a todo eixo de especificação (SpotAxis e ScenarioGrid).

    Um eixo degenerado (steps == 1) exige min == max — espelho do contrato de
    ``linspace``, para que toda especificação construível seja materializável.
    """
    limite_ok = lo > 0.0 if minimo_exclusivo else lo >= 0.0
    operador = ">" if minimo_exclusivo else ">="
    if not (isfinite(lo) and isfinite(hi) and limite_ok):
        raise InvalidDomainValueError(
            f"eixo de {nome} exige extremos finitos e {nome}_min {operador} 0; "
            f"recebido [{lo!r}, {hi!r}]"
        )
    if steps < 1:
        raise InvalidDomainValueError(f"{nome}_steps deve ser >= 1; recebido {steps!r}")
    if not (lo <= hi):
        raise InvalidDomainValueError(f"eixo de {nome} exige min <= max; recebido [{lo!r}, {hi!r}]")
    if steps == 1 and lo != hi:
        raise InvalidDomainValueError(
            f"eixo de {nome} com steps == 1 exige min == max; recebido [{lo!r}, {hi!r}]"
        )


@dataclass(frozen=True, slots=True)
class StressScenario:
    """Choque nomeado e imutável sobre um snapshot de mercado.

    Unidades (CONVENTIONS §1 — decimal em tudo):
    - ``spot_shift`` MULTIPLICATIVO: 1.10 = spot +10%; sempre > 0.
    - ``vol_shift`` ADITIVO em vol decimal: 0.02 = +2 pontos de vol.
    - ``rate_shift`` ADITIVO sobre a taxa em capitalização CONTÍNUA
      (a base canônica do kernel) — casa com a grega ``rho``.

    ``label`` existe para relatório auditável: um choque sem nome não
    aparece de forma rastreável no report.
    """

    label: str
    spot_shift: float = 1.0
    vol_shift: float = 0.0
    rate_shift: float = 0.0

    def __post_init__(self) -> None:
        if not self.label:
            raise InvalidDomainValueError("label do cenário não pode ser vazio")
        if not (isfinite(self.spot_shift) and self.spot_shift > 0.0):
            raise InvalidDomainValueError(
                f"spot_shift é multiplicativo e deve ser finito e > 0; recebido {self.spot_shift!r}"
            )
        if not (isfinite(self.vol_shift) and isfinite(self.rate_shift)):
            raise InvalidDomainValueError(
                f"vol_shift e rate_shift devem ser finitos; recebido "
                f"vol_shift={self.vol_shift!r}, rate_shift={self.rate_shift!r}"
            )


@dataclass(frozen=True, slots=True)
class SpotAxis:
    """Eixo declarativo de spots para amostragem de payoff (1D).

    Especificação, não malha: os floats saem do ``linspace`` do kernel na
    materialização. Spot em valor ABSOLUTO, na moeda do subjacente — mesma
    disciplina do eixo de spot do ``ScenarioGrid``, com quem compartilha a
    validação de eixo.
    """

    spot_min: float
    spot_max: float
    steps: int

    def __post_init__(self) -> None:
        _validar_eixo("spot", self.spot_min, self.spot_max, self.steps, minimo_exclusivo=True)


@dataclass(frozen=True, slots=True)
class ScenarioGrid:
    """Especificação declarativa de um grid spot x vol.

    Eixos em valores ABSOLUTOS nas unidades canônicas: spot na moeda do
    subjacente, vol anualizada decimal (na mesma base do tau do pricing).
    """

    spot_min: float
    spot_max: float
    spot_steps: int
    vol_min: float
    vol_max: float
    vol_steps: int

    def __post_init__(self) -> None:
        _validar_eixo("spot", self.spot_min, self.spot_max, self.spot_steps, minimo_exclusivo=True)
        _validar_eixo("vol", self.vol_min, self.vol_max, self.vol_steps, minimo_exclusivo=False)


@dataclass(frozen=True, slots=True)
class StressGridResult:
    """Grid materializado: especificação + eixos + valor por célula.

    ``values[i][j]`` = valor mark-to-model da estrutura em
    ``(spots[i], vols[j])``. Carrega a especificação e os eixos junto dos
    valores — mesma disciplina de auditoria do ``PricingResult``.
    """

    grid: ScenarioGrid
    spots: tuple[float, ...]
    vols: tuple[float, ...]
    values: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if len(self.spots) != self.grid.spot_steps or len(self.vols) != self.grid.vol_steps:
            raise InvalidDomainValueError(
                f"eixos incoerentes com a especificação: {len(self.spots)} spots vs "
                f"{self.grid.spot_steps} steps, {len(self.vols)} vols vs "
                f"{self.grid.vol_steps} steps"
            )
        if len(self.values) != len(self.spots):
            raise InvalidDomainValueError(
                f"values deve ter uma linha por spot; recebido {len(self.values)} "
                f"linhas para {len(self.spots)} spots"
            )
        for i, linha in enumerate(self.values):
            if len(linha) != len(self.vols):
                raise InvalidDomainValueError(
                    f"linha {i} tem {len(linha)} células para {len(self.vols)} vols"
                )
            for j, valor in enumerate(linha):
                # Decisão nº 5 na prática: nenhuma célula pode ser NaN/inf —
                # posição vencida vira intrínseco descontado, nunca buraco.
                if not isfinite(valor):
                    raise InvalidDomainValueError(f"célula ({i}, {j}) não é finita: {valor!r}")


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """Resultado de UM cenário nomeado: o choque aplicado e o valor obtido.

    ``value`` é o valor mark-to-model BRUTO da estrutura sob o cenário (sem
    fluxo de prêmios — CONVENTIONS §5), vindo do motor de simulação. A
    variação contra a base não é campo: deriva no ``StressTestReport``
    (``change_from_base``), para que não exista dupla fonte de verdade.
    """

    scenario: StressScenario
    value: float

    def __post_init__(self) -> None:
        if not isfinite(self.value):
            # Decisão nº 5: posição vencida vale intrínseco descontado,
            # nunca NaN — um buraco no relatório é bug, não dado.
            raise InvalidDomainValueError(
                f"value do cenário {self.scenario.label!r} não é finito: {self.value!r}"
            )


@dataclass(frozen=True, slots=True)
class StressTestReport:
    """Relatório auditável de estresse por cenários nomeados.

    Mesma disciplina de auditoria do ``PricingResult``: carrega o snapshot
    base e o tau usados, para que todo número seja reconstruível a
    posteriori. SEM ``model_id`` — os valores vêm do motor de simulação
    (kernel), não de um ``PricingModel``, consistente com o
    ``StressGridResult``.
    """

    strategy_name: str
    base_snapshot: MarketSnapshot
    time_to_expiry: TimeToExpiry
    base_value: float
    outcomes: tuple[ScenarioOutcome, ...]

    def __post_init__(self) -> None:
        if not self.strategy_name:
            raise InvalidDomainValueError("strategy_name não pode ser vazio")
        if not isfinite(self.base_value):
            raise InvalidDomainValueError(
                f"base_value deve ser finito; recebido {self.base_value!r}"
            )
        if len(self.outcomes) == 0:
            raise InvalidDomainValueError(
                "relatório de estresse exige ao menos um cenário — um report vazio "
                "não responde nenhuma pergunta de risco"
            )
        labels = [outcome.scenario.label for outcome in self.outcomes]
        if len(set(labels)) != len(labels):
            raise InvalidDomainValueError(
                f"labels de cenário devem ser únicos no relatório (rastreabilidade); "
                f"recebido {labels!r}"
            )

    def change_from_base(self, outcome: ScenarioOutcome) -> float:
        """Variação do valor sob o cenário contra o valor base (mesma unidade)."""
        return outcome.value - self.base_value

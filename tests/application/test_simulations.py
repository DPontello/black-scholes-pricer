"""``SimulationService``: nome, instante e id; a pasta é a do perfil aberto."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.inbound import BuilderLegInput, BuilderRequest
from options_engine.application.ports.simulations import (
    SavedSimulation,
    SimulationUseCase,
    UnreadableFile,
)
from options_engine.application.use_cases.simulations import SimulationService
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError, UnknownRecordError

AGORA = datetime(2026, 11, 4, 14, 0, tzinfo=UTC)
PEDIDO = BuilderRequest("PETR4", (BuilderLegInput("PETRK320", Side.SELL, 100),))


@dataclass
class _Repositorio:
    salvas: dict[str, SavedSimulation] = field(default_factory=dict)
    ilegiveis: tuple[UnreadableFile, ...] = ()

    def list(self) -> tuple[SavedSimulation | UnreadableFile, ...]:
        return (*self.salvas.values(), *self.ilegiveis)

    def save(self, simulation: SavedSimulation) -> None:
        self.salvas[simulation.id] = simulation

    def load(self, simulation_id: str) -> SavedSimulation:
        if simulation_id not in self.salvas:
            raise UnknownRecordError(simulation_id)
        return self.salvas[simulation_id]

    def delete(self, simulation_id: str) -> None:
        self.load(simulation_id)
        del self.salvas[simulation_id]


def _servico(repositorio: _Repositorio) -> SimulationService:
    ids = iter(["a1", "b2", "c3"])
    return SimulationService(lambda: repositorio, FixedClock(AGORA), lambda: next(ids))


def test_cumpre_o_protocol() -> None:
    assert isinstance(_servico(_Repositorio()), SimulationUseCase)


def test_salva_com_id_instante_e_nome_sem_espacos() -> None:
    repositorio = _Repositorio()
    salva = _servico(repositorio).save("  coberta de novembro ", PEDIDO)
    assert salva == SavedSimulation("a1", "coberta de novembro", AGORA, PEDIDO)
    assert repositorio.salvas == {"a1": salva}


def test_nome_vazio_e_recusado() -> None:
    with pytest.raises(InvalidDomainValueError, match="nome"):
        _servico(_Repositorio()).save("  ", PEDIDO)


def test_lista_as_mais_novas_primeiro_e_as_ilegiveis_no_fim() -> None:
    antiga = SavedSimulation("x", "antiga", datetime(2026, 10, 1, tzinfo=UTC), PEDIDO)
    nova = SavedSimulation("y", "nova", datetime(2026, 11, 1, tzinfo=UTC), PEDIDO)
    ilegivel = UnreadableFile("/perfil/simulacoes/z.json", "JSON inválido")
    repositorio = _Repositorio({"x": antiga, "y": nova}, (ilegivel,))
    assert _servico(repositorio).list() == (nova, antiga, ilegivel)


def test_abre_e_apaga_pelo_id() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio)
    salva = servico.save("trava", PEDIDO)
    assert servico.load(salva.id) == salva
    servico.delete(salva.id)
    with pytest.raises(UnknownRecordError):
        servico.load(salva.id)

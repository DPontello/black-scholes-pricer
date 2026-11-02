"""``SimulationService``: simulações do montador na pasta do perfil aberto."""

from collections.abc import Callable

from options_engine.application.ports.inbound import BuilderRequest
from options_engine.application.ports.outbound import Clock
from options_engine.application.ports.simulations import (
    SavedSimulation,
    SimulationRepository,
    UnreadableFile,
)
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["SimulationService"]


class SimulationService:
    """``repository_for`` é chamado a cada operação: o perfil aberto pode ter mudado."""

    def __init__(
        self,
        repository_for: Callable[[], SimulationRepository],
        clock: Clock,
        new_id: Callable[[], str],
    ) -> None:
        self._repository_for = repository_for
        self._clock = clock
        self._new_id = new_id

    def list(self) -> tuple[SavedSimulation | UnreadableFile, ...]:
        itens = self._repository_for().list()
        salvas = sorted(
            (i for i in itens if isinstance(i, SavedSimulation)),
            key=lambda s: s.created_at,
            reverse=True,
        )
        return (*salvas, *(i for i in itens if isinstance(i, UnreadableFile)))

    def save(self, name: str, request: BuilderRequest) -> SavedSimulation:
        if not name.strip():
            raise InvalidDomainValueError("a simulação precisa de um nome")
        simulacao = SavedSimulation(self._new_id(), name.strip(), self._clock.now(), request)
        self._repository_for().save(simulacao)
        return simulacao

    def load(self, simulation_id: str) -> SavedSimulation:
        return self._repository_for().load(simulation_id)

    def delete(self, simulation_id: str) -> None:
        self._repository_for().delete(simulation_id)

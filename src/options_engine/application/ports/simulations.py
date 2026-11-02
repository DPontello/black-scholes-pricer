"""Simulações salvas do montador: o pedido da análise, para reabrir com os preços do momento."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from options_engine.application.ports.inbound import BuilderRequest

__all__ = [
    "SavedSimulation",
    "SimulationRepository",
    "SimulationUseCase",
    "UnreadableFile",
]


@dataclass(frozen=True, slots=True)
class UnreadableFile:
    path: str
    reason: str


@dataclass(frozen=True, slots=True)
class SavedSimulation:
    id: str
    name: str
    created_at: datetime
    request: BuilderRequest


@runtime_checkable
class SimulationRepository(Protocol):
    """``load`` e ``delete`` levantam ``UnknownRecordError``; ``load`` de arquivo ilegível,
    ``UnreadableRecordError``."""

    def list(self) -> tuple[SavedSimulation | UnreadableFile, ...]: ...

    def save(self, simulation: SavedSimulation) -> None: ...

    def load(self, simulation_id: str) -> SavedSimulation: ...

    def delete(self, simulation_id: str) -> None: ...


@runtime_checkable
class SimulationUseCase(Protocol):
    """Sempre na pasta do perfil aberto (``NoActiveProfileError`` sem perfil)."""

    def list(self) -> tuple[SavedSimulation | UnreadableFile, ...]: ...

    def save(self, name: str, request: BuilderRequest) -> SavedSimulation: ...

    def load(self, simulation_id: str) -> SavedSimulation: ...

    def delete(self, simulation_id: str) -> None: ...

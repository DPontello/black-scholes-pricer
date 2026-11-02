"""Carteira do perfil aberto: registrar, encerrar, exercer, vencer e ver as operações."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from options_engine.application.ports.outbound import UnreadableFile
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.model import LegState, Operation
from options_engine.domain.portfolio.positions import AssetTotal

__all__ = [
    "ExpiryNotice",
    "Fill",
    "OperationView",
    "PortfolioUseCase",
    "PortfolioView",
    "RegisterOperation",
    "RegisterOptionLeg",
    "RegisterStock",
]


@dataclass(frozen=True, slots=True)
class Fill:
    """Uma execução na Necton: quantidade, preço e, se o usuário souber, os custos reais."""

    quantity: int
    price: float
    costs: float | None = None


@dataclass(frozen=True, slots=True)
class RegisterOptionLeg:
    symbol: str
    terms: OptionTerms
    side: Side
    fills: tuple[Fill, ...]


@dataclass(frozen=True, slots=True)
class RegisterStock:
    """``CARTEIRA``: usa ações livres do perfil e não tem execução; ``COMPRA``: as execuções."""

    side: Side
    origin: StockOrigin
    fills: tuple[Fill, ...] = ()


@dataclass(frozen=True, slots=True)
class RegisterOperation:
    underlying: str
    name: str
    on: date
    legs: tuple[RegisterOptionLeg, ...]
    stock: RegisterStock | None = None


@dataclass(frozen=True, slots=True)
class OperationView:
    """``realized``: resultado realizado com custos (reais ou estimados), em moeda."""

    operation: Operation
    legs: tuple[LegState, ...]
    realized: float


@dataclass(frozen=True, slots=True)
class ExpiryNotice:
    operation_id: str
    leg: int
    symbol: str
    expiry: date
    outcome: ExpiryOutcome


@dataclass(frozen=True, slots=True)
class PortfolioView:
    operations: tuple[OperationView, ...]
    totals: tuple[AssetTotal, ...]
    unreadable: tuple[UnreadableFile, ...]


@runtime_checkable
class PortfolioUseCase(Protocol):
    """Sempre na pasta do perfil aberto. ``closes(ativo, dia)``: o fechamento do pregão."""

    def register(self, command: RegisterOperation) -> Operation: ...

    def add_stock(
        self, symbol: str, quantity: int, average_price: float, on: date
    ) -> Operation: ...

    def close(
        self,
        operation_id: str,
        leg: int,
        quantity: int,
        price: float,
        on: date,
        costs: float | None = None,
    ) -> Operation: ...

    def exercise(
        self, operation_id: str, leg: int, quantity: int, on: date, costs: float | None = None
    ) -> Operation: ...

    def assign(
        self, operation_id: str, leg: int, quantity: int, on: date, costs: float | None = None
    ) -> Operation: ...

    def open_operations(self) -> PortfolioView: ...

    def history(self) -> tuple[OperationView, ...]: ...

    def process_expiries(
        self, closes: Callable[[str, date], float | None]
    ) -> tuple[ExpiryNotice, ...]: ...

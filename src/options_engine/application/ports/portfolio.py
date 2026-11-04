"""Carteira do perfil aberto: registrar, encerrar, exercer, vencer e ver as operações."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol, runtime_checkable

from options_engine.application.ports.outbound import UnreadableFile
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.quotes import DataSource
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.income_tax import TaxMonth
from options_engine.domain.portfolio.model import LegState, Operation
from options_engine.domain.portfolio.positions import AssetTotal

__all__ = [
    "AssetView",
    "ExpiryNotice",
    "Fill",
    "LegMark",
    "OperationView",
    "PortfolioSymbols",
    "PortfolioUseCase",
    "PortfolioView",
    "RegisterOperation",
    "RegisterOptionLeg",
    "RegisterStock",
    "TaxMonthView",
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
class LegMark:
    """Posição aberta a mercado pelo preço de zerar: bid para a comprada, ask para a vendida
    (ADR-0004). Sem esse lado, ``price`` e ``unrealized`` são ``None`` e ``reason`` diz por quê;
    ``theoretical`` é o prêmio teórico, só nesse caso, e fica fora do total executável."""

    price: float | None
    unrealized: float | None
    theoretical: float | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperationView:
    """``realized``: resultado realizado com custos (reais ou estimados), em moeda.

    ``marks``: uma por perna, ``None`` na perna sem posição aberta (e no histórico).
    ``unrealized``: a soma das pernas abertas, ``None`` se alguma não tem preço de zerar.
    """

    operation: Operation
    legs: tuple[LegState, ...]
    realized: float
    marks: tuple[LegMark | None, ...] = ()
    unrealized: float | None = None


@dataclass(frozen=True, slots=True)
class AssetView:
    total: AssetTotal
    mark: LegMark


@dataclass(frozen=True, slots=True)
class ExpiryNotice:
    operation_id: str
    leg: int
    symbol: str
    expiry: date
    outcome: ExpiryOutcome


@dataclass(frozen=True, slots=True)
class PortfolioSymbols:
    """O que a carteira aberta precisa assinar: os ativos das operações e as séries."""

    underlyings: tuple[str, ...]
    series: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PortfolioView:
    """``source``: de onde vieram os preços de zerar (a saúde menos fresca da consulta)."""

    operations: tuple[OperationView, ...]
    totals: tuple[AssetView, ...]
    unreadable: tuple[UnreadableFile, ...]
    source: DataSource
    symbols: PortfolioSymbols


@dataclass(frozen=True, slots=True)
class TaxMonthView:
    """``pay_by``: o último dia útil do mês seguinte, só quando há DARF a pagar no mês; ``None``
    também quando esse dia cai fora da cobertura do calendário."""

    month: TaxMonth
    pay_by: date | None


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

    def income_tax(self) -> tuple[TaxMonthView, ...]:
        """O IR mensal estimado das opções, do mês mais antigo ao mais recente."""
        ...

    def average_price(self, symbol: str) -> float | None:
        """O médio das ações livres do ativo (as que uma venda "da carteira" usaria)."""
        ...

    def process_expiries(
        self, closes: Callable[[str, date], float | None]
    ) -> tuple[ExpiryNotice, ...]: ...

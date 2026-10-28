"""Fakes dos ports outbound para os testes unitários dos use cases.

Fakes, não mocks de framework: implementações mínimas e determinísticas dos
Protocols, com gravação explícita do que foi consultado — o teste afirma
comportamento observável (o que o use case pediu aos ports), nunca detalhes
de implementação.

Sem fake de ``Clock`` aqui: ``FixedClock`` (``adapters/outbound/clock.py``)
já é frozen, determinístico e valida tz-awareness na construção — duplicá-lo
sem essa validação divergiria do contrato do port sem nenhum ganho.
"""

from dataclasses import dataclass, field
from datetime import date, datetime

from options_engine.domain.model.errors import (
    DuplicateProfileError,
    InvalidDomainValueError,
    ProfileLockedError,
    UnknownProfileError,
    UnknownSymbolError,
)
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.profile import Profile, ProfileEntry

__all__ = ["FakeMarketData", "FakeProfileRepository", "FakeTradingCalendar"]


@dataclass(slots=True)
class FakeMarketData:
    """Devolve o snapshot configurado para o seu símbolo; grava as consultas.

    Símbolo divergente → ``UnknownSymbolError``, como manda o contrato do
    ``MarketDataPort`` (nunca ``KeyError``/``None``).
    """

    snapshot: MarketSnapshot
    requested_symbols: list[str] = field(default_factory=list)

    def get_snapshot(self, underlying_symbol: str) -> MarketSnapshot:
        self.requested_symbols.append(underlying_symbol)
        if underlying_symbol != self.snapshot.underlying_symbol:
            raise UnknownSymbolError(f"símbolo desconhecido no fake: {underlying_symbol!r}")
        return self.snapshot


@dataclass(slots=True)
class FakeTradingCalendar:
    """Contagem enlatada de dias úteis; grava os intervalos consultados.

    A semântica [start, end) pertence ao adapter real e à sua suíte — aqui
    só interessa QUE intervalo o use case pediu e QUANTOS dias voltaram.
    """

    business_days: int
    requested_ranges: list[tuple[date, date]] = field(default_factory=list)

    def business_days_between(self, start: date, end: date) -> int:
        if start > end:
            raise InvalidDomainValueError(
                f"contagem negativa não tem semântica; recebido [{start}, {end})"
            )
        self.requested_ranges.append((start, end))
        return self.business_days


@dataclass(slots=True)
class FakeProfileRepository:
    """Perfis em memória; grava o que o serviço pediu ao repositório.

    Só o que o serviço exercita: a semântica de pasta, arquivo e prazo da
    trava é do adapter e da sua suíte (tests/adapters/storage). ``lock_error``
    simula a trava de outro PC ainda válida — cede quando ``force`` é True.
    """

    profiles: dict[str, Profile] = field(default_factory=dict)
    folders: dict[str, str] = field(default_factory=dict)
    lock_error: ProfileLockedError | None = None
    saved: list[tuple[str, Profile]] = field(default_factory=list)
    acquired: list[tuple[str, str, datetime, bool]] = field(default_factory=list)
    released: list[tuple[str, str]] = field(default_factory=list)

    def list_profiles(self) -> tuple[ProfileEntry, ...]:
        return tuple(ProfileEntry(name, self.folders[name]) for name in self.profiles)

    def create(self, name: str, folder: str) -> Profile:
        if name in self.profiles:
            raise DuplicateProfileError(f"já existe um perfil {name!r}")
        self.profiles[name] = Profile(name, ("PETR4", "VALE3"), 0.15)
        self.folders[name] = folder
        return self.profiles[name]

    def load(self, name: str) -> Profile:
        if name not in self.profiles:
            raise UnknownProfileError(f"perfil {name!r} não está registrado")
        return self.profiles[name]

    def save(self, name: str, profile: Profile) -> None:
        self.saved.append((name, profile))
        self.profiles[name] = profile

    def acquire_lock(self, name: str, machine: str, now: datetime, force: bool) -> None:
        self.acquired.append((name, machine, now, force))
        if self.lock_error is not None and not force:
            raise self.lock_error

    def release_lock(self, name: str, machine: str) -> None:
        self.released.append((name, machine))

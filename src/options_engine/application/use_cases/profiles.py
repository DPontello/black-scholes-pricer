"""``ProfileService`` — implementação do contrato ``ProfileUseCase``.

Guarda qual perfil está aberto neste PC e mantém a trava de uso. Orquestração
pura: onde o perfil mora e como a trava vira arquivo é do ``ProfileRepository``.
"""

from collections.abc import Sequence
from dataclasses import replace
from datetime import timedelta, timezone, tzinfo

from options_engine.application.ports.outbound import Clock, ProfileRepository
from options_engine.domain.model.errors import NoActiveProfileError
from options_engine.domain.model.profile import Profile, ProfileEntry, normalize_ticker

__all__ = ["ProfileService"]

# Fuso padrão da trava: Brasília (UTC-3 fixo, DST abolido em 2019) — o mesmo de
# ``adapters.outbound.b3_calendar.B3_UTC_OFFSET``. ``application`` não importa
# ``adapters`` (camadas do import-linter), então o valor é replicado; um teste
# prende as duas cópias. Quem monta o serviço pode injetar outro.
_BRASILIA = timezone(timedelta(hours=-3), name="America/Sao_Paulo (UTC-3 fixo)")


class ProfileService:
    """Abre, trava e edita o perfil do usuário deste PC.

    ``lock_timezone`` é o fuso em que o instante da trava é gravado: a
    mensagem de ``ProfileLockedError`` mostra a hora de parede do próprio
    objeto, então o outro PC lê "desde 09:00" em horário de Brasília e não em
    UTC. Fica no construtor porque é política de instalação, como o fuso de
    valoração dos outros use cases.
    """

    def __init__(
        self,
        repository: ProfileRepository,
        clock: Clock,
        machine_name: str,
        *,
        lock_timezone: tzinfo = _BRASILIA,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._machine_name = machine_name
        self._lock_timezone = lock_timezone
        # (chave do cadastro usada no `open`, perfil): a chave é quem manda em
        # `save` e `release_lock`, nunca o `nome` que veio dentro do perfil.
        self._active: tuple[str, Profile] | None = None

    def list(self) -> tuple[ProfileEntry, ...]:
        return self._repository.list_profiles()

    def create(self, name: str, folder: str) -> Profile:
        return self._repository.create(name, folder)

    def open(self, name: str, force: bool = False) -> Profile:
        # Ler antes de travar: perfil desconhecido ou ilegível não deixa trava
        # para trás. E só solta o perfil anterior depois de travar o novo — se a
        # trava negar, o usuário continua no perfil em que estava.
        profile = self._repository.load(name)
        now = self._clock.now().astimezone(self._lock_timezone)
        self._repository.acquire_lock(name, self._machine_name, now, force)
        previous = self._active
        self._active = (name, profile)
        if previous is not None and previous[0] != name:
            self._repository.release_lock(previous[0], self._machine_name)
        return profile

    def active(self) -> Profile:
        return self._require_active()[1]

    def set_watchlist(self, tickers: Sequence[str]) -> Profile:
        key, current = self._require_active()
        # `dict.fromkeys` remove repetidos mantendo a ordem da primeira ocorrência.
        watchlist = tuple(dict.fromkeys(normalize_ticker(ticker) for ticker in tickers))
        updated = replace(current, watchlist=watchlist)
        # Grava antes de trocar o ativo: se a gravação falha, nada mudou em memória.
        self._repository.save(key, updated)
        self._active = (key, updated)
        return updated

    def close(self) -> None:
        if self._active is None:
            return
        key = self._active[0]
        self._active = None
        self._repository.release_lock(key, self._machine_name)

    def _require_active(self) -> tuple[str, Profile]:
        if self._active is None:
            raise NoActiveProfileError("nenhum perfil aberto; abra um perfil antes")
        return self._active

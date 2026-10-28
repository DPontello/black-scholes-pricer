"""``JsonProfileRepository`` — perfis em JSON na pasta que o usuário escolheu.

Dois níveis de arquivo, por desenho:

- configuração DA MÁQUINA (``config_path``): ``{"versao": 1, "perfis":
  [{"nome": ..., "pasta": ...}]}`` — quais perfis este PC conhece e onde
  moram;
- na pasta do perfil (que pode ser nuvem ou pendrive e viaja entre PCs):
  ``perfil.json`` com os dados e ``perfil.lock`` com a trava de uso.

O nome do perfil é só a chave do cadastro: nunca vira nome de pasta ou de
arquivo (a pasta é a que o usuário escolheu), então não há o que sanitizar
além das invariantes do próprio ``Profile``.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

from options_engine.adapters.outbound.storage.json_files import write_json_atomic
from options_engine.domain.model.errors import (
    DuplicateProfileError,
    InvalidDomainValueError,
    ProfileFolderUnavailableError,
    ProfileLockedError,
    UnknownProfileError,
)
from options_engine.domain.model.profile import Profile, ProfileEntry, normalize_ticker

__all__ = [
    "DEFAULT_PROFILE_CDI_ANNUAL",
    "DEFAULT_PROFILE_WATCHLIST",
    "LOCK_EXPIRY",
    "JsonProfileRepository",
]

_SCHEMA_VERSION = 1
_PROFILE_FILE = "perfil.json"
_LOCK_FILE = "perfil.lock"

# Mesmo valor de ``config.composition.DEFAULT_CDI_ANNUAL``: ``adapters`` não
# pode importar ``config`` (camadas do import-linter), então o valor é
# replicado aqui; um teste prende as duas cópias.
DEFAULT_PROFILE_CDI_ANNUAL = 0.15
DEFAULT_PROFILE_WATCHLIST = ("PETR4", "VALE3")

# Passou disso, a trava é de um PC que travou (ou foi esquecido aberto): vale
# mais seguir do que bloquear o usuário para sempre. Dentro do prazo, só
# ``force`` passa.
LOCK_EXPIRY = timedelta(hours=12)


class JsonProfileRepository:
    """Implementa ``ProfileRepository`` sobre arquivos JSON."""

    def __init__(
        self, config_path: Path, *, default_cdi_annual: float = DEFAULT_PROFILE_CDI_ANNUAL
    ) -> None:
        self._config_path = config_path
        self._default_cdi_annual = default_cdi_annual

    def list_profiles(self) -> tuple[ProfileEntry, ...]:
        return self._read_entries()

    def create(self, name: str, folder: str) -> Profile:
        entries = self._read_entries()
        _require_free_name(entries, name)
        profile_path = _require_folder(folder) / _PROFILE_FILE
        adopted = _read_profile(profile_path)
        if adopted is None:
            # O `Profile` nasce (e valida o nome) ANTES de qualquer gravação.
            profile = Profile(name, DEFAULT_PROFILE_WATCHLIST, self._default_cdi_annual)
            _write_json(profile_path, _profile_to_json(profile))
        else:
            # Perfil já existente na pasta (outro PC, nuvem): o nome do arquivo prevalece.
            profile = adopted
            _require_free_name(entries, profile.name)
        self._write_entries((*entries, ProfileEntry(profile.name, folder)))
        return profile

    def load(self, name: str) -> Profile:
        profile_path = self._folder_path(name) / _PROFILE_FILE
        profile = _read_profile(profile_path)
        if profile is None:
            # Pasta de pé, mas sem o arquivo: ponto de montagem que a nuvem
            # ainda não sincronizou. Recriar aqui esconderia o perfil real.
            raise ProfileFolderUnavailableError(
                f"perfil {name!r} sem arquivo em {profile_path} (a nuvem já sincronizou a pasta?)"
            )
        if profile.name != name:
            # A chave do cadastro manda: serviço e arquivos de trava usam `name`, e um
            # `nome` divergente faria `save` reescrever a pasta de outro perfil.
            raise _invalid(
                profile_path,
                f"o nome no arquivo é {profile.name!r}, mas o perfil está cadastrado "
                f"neste PC como {name!r}",
            )
        return profile

    def save(self, name: str, profile: Profile) -> None:
        if profile.name != name:
            raise InvalidDomainValueError(
                f"o perfil cadastrado como {name!r} não pode ser gravado como {profile.name!r}"
            )
        _write_json(self._folder_path(name) / _PROFILE_FILE, _profile_to_json(profile))

    def acquire_lock(self, name: str, machine: str, now: datetime, force: bool) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise InvalidDomainValueError(
                f"instante da trava deve ter fuso (tz-aware); recebido {now!r}"
            )
        lock_path = self._folder_path(name) / _LOCK_FILE
        current = _read_lock(lock_path)
        if current is not None and not force:
            other_machine, since = current
            if other_machine != machine and now - since <= LOCK_EXPIRY:
                raise ProfileLockedError(other_machine, since)
        _write_json(lock_path, {"pc": machine, "desde": now.isoformat()})

    def release_lock(self, name: str, machine: str) -> None:
        # Sem `_require_folder` e sem propagar erro de SO: com a nuvem fora do ar
        # ou segurando o arquivo, fechar o app tem que funcionar. Se a trava
        # sobrar, é a do próprio PC: ele a renova ao reabrir e ela expira em 12 h.
        lock_path = Path(self._find_entry(name).folder) / _LOCK_FILE
        try:
            current = _read_lock(lock_path)
            if current is not None and current[0] == machine:
                lock_path.unlink(missing_ok=True)
        except (ProfileFolderUnavailableError, OSError):
            return

    # --- cadastro da máquina ------------------------------------------------------------------

    def _read_entries(self) -> tuple[ProfileEntry, ...]:
        try:
            data = _read_json_object(self._config_path)
        except FileNotFoundError:
            return ()
        _require_schema_version(data, self._config_path)
        profiles = data.get("perfis")
        if not isinstance(profiles, list):
            raise _invalid(self._config_path, "campo 'perfis' ausente ou não é lista")
        entries: list[ProfileEntry] = []
        for item in profiles:
            name = item.get("nome") if isinstance(item, dict) else None
            folder = item.get("pasta") if isinstance(item, dict) else None
            if not (isinstance(name, str) and isinstance(folder, str)):
                raise _invalid(self._config_path, f"perfil sem 'nome' e 'pasta' em texto: {item!r}")
            entries.append(ProfileEntry(name, folder))
        return tuple(entries)

    def _write_entries(self, entries: tuple[ProfileEntry, ...]) -> None:
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(
            self._config_path,
            {
                "versao": _SCHEMA_VERSION,
                "perfis": [{"nome": e.name, "pasta": e.folder} for e in entries],
            },
        )

    def _find_entry(self, name: str) -> ProfileEntry:
        for entry in self._read_entries():
            if entry.name == name:
                return entry
        raise UnknownProfileError(f"perfil {name!r} não está cadastrado neste PC")

    def _folder_path(self, name: str) -> Path:
        return _require_folder(self._find_entry(name).folder)


def _require_free_name(entries: tuple[ProfileEntry, ...], name: str) -> None:
    if any(entry.name == name for entry in entries):
        raise DuplicateProfileError(f"já existe um perfil {name!r} neste PC")


def _require_folder(folder: str) -> Path:
    """A pasta como ``Path``, se existir; senão o erro com o caminho — sem criar nada."""
    path = Path(folder)
    if not path.is_dir():
        raise ProfileFolderUnavailableError(
            f"pasta do perfil indisponível: {folder} (nuvem desmontada ou pendrive fora?)"
        )
    return path


def _invalid(path: Path, reason: str) -> InvalidDomainValueError:
    return InvalidDomainValueError(f"arquivo {path} inválido: {reason}")


def _read_json_object(path: Path) -> dict[str, object]:
    """Objeto JSON do arquivo; ``FileNotFoundError`` sobe para o chamador decidir."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as erro:  # JSONDecodeError e UnicodeDecodeError
        raise _invalid(path, f"JSON ilegível ({erro})") from erro
    if not isinstance(data, dict):
        raise _invalid(path, "esperava um objeto JSON")
    return data


def _require_schema_version(data: dict[str, object], path: Path) -> None:
    if data.get("versao") != _SCHEMA_VERSION:
        raise _invalid(
            path,
            f"versão do esquema {data.get('versao')!r} não suportada (esperada {_SCHEMA_VERSION})",
        )


def _write_json(path: Path, data: object) -> None:
    """Grava atomicamente; erro do SO (arquivo em uso, pasta sumida) vira erro de domínio."""
    try:
        write_json_atomic(path, data)
    except OSError as erro:
        raise ProfileFolderUnavailableError(f"não foi possível gravar {path}: {erro}") from erro


def _read_profile(path: Path) -> Profile | None:
    """Perfil do arquivo, ou ``None`` se ele não existe.

    Outro erro do SO (permissão, ``perfil.json`` que é diretório) vira
    ``ProfileFolderUnavailableError`` com o caminho — nunca ``OSError`` solto.
    """
    try:
        data = _read_json_object(path)
    except FileNotFoundError:
        return None
    except OSError as erro:
        raise ProfileFolderUnavailableError(f"não foi possível ler {path}: {erro}") from erro
    _require_schema_version(data, path)
    name, tickers, cdi = data.get("nome"), data.get("ativos"), data.get("cdi_anual")
    if not isinstance(name, str):
        raise _invalid(path, "campo 'nome' ausente ou não é texto")
    if not (isinstance(tickers, list) and all(isinstance(t, str) for t in tickers)):
        raise _invalid(path, "campo 'ativos' ausente ou não é lista de textos")
    if isinstance(cdi, bool) or not isinstance(cdi, int | float):
        raise _invalid(path, "campo 'cdi_anual' ausente ou não é número")
    try:
        # O arquivo pode ter sido editado à mão: a normalização é de quem monta o perfil.
        return Profile(name, tuple(normalize_ticker(t) for t in tickers), float(cdi))
    except InvalidDomainValueError as erro:
        raise _invalid(path, str(erro)) from erro


def _profile_to_json(profile: Profile) -> dict[str, object]:
    return {
        "versao": _SCHEMA_VERSION,
        "nome": profile.name,
        "ativos": list(profile.watchlist),
        "cdi_anual": profile.cdi_annual,
    }


def _read_lock(path: Path) -> tuple[str, datetime] | None:
    """PC e instante da trava, ou ``None`` se ausente ou ilegível.

    Trava ilegível (truncada por sincronização, editada à mão, sem fuso) vale
    como ausente: sem o nome do PC e o horário não há o que mostrar ao usuário,
    e a trava é só um aviso entre pessoas, não segurança. Erro do SO além de
    "não existe" (permissão, ``perfil.lock`` que é diretório) vira
    ``ProfileFolderUnavailableError`` com o caminho.
    """
    try:
        data = _read_json_object(path)
        machine, desde = data.get("pc"), data.get("desde")
        if not (isinstance(machine, str) and isinstance(desde, str)):
            return None
        since = datetime.fromisoformat(desde)
    except (FileNotFoundError, NotADirectoryError, InvalidDomainValueError, ValueError):
        return None
    except OSError as erro:
        raise ProfileFolderUnavailableError(f"não foi possível ler {path}: {erro}") from erro
    if since.tzinfo is None or since.utcoffset() is None:
        return None
    return machine, since

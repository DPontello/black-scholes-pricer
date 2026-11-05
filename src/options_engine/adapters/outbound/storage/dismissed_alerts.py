"""``JsonDismissedAlerts``: os alertas dispensados, em ``alertas.json`` na pasta do perfil.

Na pasta do perfil, e não na do PC, para o dispensado valer nos dois PCs. Arquivo ilegível é lido
como vazio (os alertas aparecem todos) e nunca sobrescrito, como as operações.
"""

import json
from pathlib import Path
from typing import Any, Final

from options_engine.adapters.outbound.storage.json_files import write_json_atomic
from options_engine.domain.model.errors import (
    ProfileFolderUnavailableError,
    UnreadableRecordError,
)

__all__ = ["JsonDismissedAlerts"]

_VERSAO: Final = 1
_ARQUIVO: Final = "alertas.json"


class JsonDismissedAlerts:
    def __init__(self, folder: Path) -> None:
        self._caminho = folder / _ARQUIVO

    def load(self) -> frozenset[str]:
        try:
            return _ler(self._caminho)
        except UnreadableRecordError:
            return frozenset()

    def save(self, keys: frozenset[str]) -> None:
        if not self._caminho.parent.is_dir():
            raise ProfileFolderUnavailableError(
                f"pasta do perfil fora do ar: {self._caminho.parent} (a nuvem está montada?)"
            )
        try:
            _ler(self._caminho)
        except UnreadableRecordError as erro:
            raise UnreadableRecordError(
                f"não regravo um arquivo ilegível, confira-o antes: {erro}"
            ) from erro
        write_json_atomic(self._caminho, {"versao": _VERSAO, "dispensados": sorted(keys)})


def _ler(caminho: Path) -> frozenset[str]:
    """Ausente é vazio; o resto que não for o formato esperado é ilegível."""
    try:
        dados: Any = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return frozenset()
    except (OSError, ValueError) as erro:
        raise UnreadableRecordError(f"{caminho}: JSON ilegível ({erro})") from erro
    if not isinstance(dados, dict) or dados.get("versao") != _VERSAO:
        raise UnreadableRecordError(f"{caminho}: formato ou versão desconhecidos")
    chaves = dados.get("dispensados")
    if not (isinstance(chaves, list) and all(isinstance(c, str) for c in chaves)):
        raise UnreadableRecordError(f"{caminho}: 'dispensados' não é lista de textos")
    return frozenset(chaves)

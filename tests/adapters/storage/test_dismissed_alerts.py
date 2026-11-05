"""``JsonDismissedAlerts``: ``alertas.json`` na pasta do perfil."""

import json
from pathlib import Path

import pytest

from options_engine.adapters.outbound.storage.dismissed_alerts import JsonDismissedAlerts
from options_engine.application.ports.outbound import DismissedAlertsRepository
from options_engine.domain.model.errors import (
    ProfileFolderUnavailableError,
    UnreadableRecordError,
)


def _caixa(tmp_path: Path) -> JsonDismissedAlerts:
    pasta = tmp_path / "perfil"
    pasta.mkdir(exist_ok=True)
    return JsonDismissedAlerts(pasta)


def test_cumpre_a_porta(tmp_path: Path) -> None:
    assert isinstance(_caixa(tmp_path), DismissedAlertsRepository)


def test_sem_arquivo_e_vazio(tmp_path: Path) -> None:
    assert _caixa(tmp_path).load() == frozenset()


def test_ida_e_volta_ordenada(tmp_path: Path) -> None:
    caixa = _caixa(tmp_path)
    caixa.save(frozenset({"stop:b:-", "alvo:a:-"}))
    assert caixa.load() == {"stop:b:-", "alvo:a:-"}
    gravado = json.loads((tmp_path / "perfil" / "alertas.json").read_text(encoding="utf-8"))
    assert gravado == {"versao": 1, "dispensados": ["alvo:a:-", "stop:b:-"]}


@pytest.mark.parametrize(
    "conteudo",
    [
        "{quebrado",
        "[]",
        '{"versao": 2, "dispensados": []}',
        '{"versao": 1, "dispensados": "stop:a:-"}',
        '{"versao": 1, "dispensados": [1]}',
    ],
)
def test_arquivo_ilegivel_nao_e_sobrescrito(tmp_path: Path, conteudo: str) -> None:
    caixa = _caixa(tmp_path)
    arquivo = tmp_path / "perfil" / "alertas.json"
    arquivo.write_text(conteudo, encoding="utf-8")
    assert caixa.load() == frozenset()
    with pytest.raises(UnreadableRecordError, match=r"alertas\.json"):
        caixa.save(frozenset({"stop:a:-"}))
    assert arquivo.read_text(encoding="utf-8") == conteudo


def test_pasta_do_perfil_fora_do_ar(tmp_path: Path) -> None:
    caixa = JsonDismissedAlerts(tmp_path / "nuvem_desmontada")
    assert caixa.load() == frozenset()
    with pytest.raises(ProfileFolderUnavailableError):
        caixa.save(frozenset({"stop:a:-"}))
    assert not (tmp_path / "nuvem_desmontada").exists()

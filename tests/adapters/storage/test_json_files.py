"""``write_json_atomic`` — gravação por arquivo temporário + ``os.replace``."""

import json
from pathlib import Path
from typing import NoReturn

import pytest

from options_engine.adapters.outbound.storage.json_files import write_json_atomic


def test_grava_o_json_e_nao_deixa_temporario(tmp_path: Path) -> None:
    destino = tmp_path / "dados.json"
    write_json_atomic(destino, {"versao": 1, "ativos": ["PETR4"]})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"versao": 1, "ativos": ["PETR4"]}
    assert not list(tmp_path.glob("*.tmp"))


def test_substitui_o_arquivo_existente(tmp_path: Path) -> None:
    destino = tmp_path / "dados.json"
    write_json_atomic(destino, {"valor": 1})
    write_json_atomic(destino, {"valor": 2})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"valor": 2}


def test_acentos_ficam_legiveis_no_arquivo(tmp_path: Path) -> None:
    destino = tmp_path / "dados.json"
    write_json_atomic(destino, {"nome": "Mãe"})
    assert "Mãe" in destino.read_text(encoding="utf-8")


def test_falha_na_serializacao_preserva_o_original_e_limpa_o_temporario(tmp_path: Path) -> None:
    destino = tmp_path / "dados.json"
    write_json_atomic(destino, {"valor": 1})
    with pytest.raises(TypeError):
        write_json_atomic(destino, {"valor": object()})
    assert json.loads(destino.read_text(encoding="utf-8")) == {"valor": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_nan_nao_vira_json_invalido(tmp_path: Path) -> None:
    destino = tmp_path / "dados.json"
    with pytest.raises(ValueError, match="JSON"):
        write_json_atomic(destino, {"valor": float("nan")})
    assert not destino.exists()
    assert not list(tmp_path.glob("*.tmp"))


def test_falha_ao_apagar_o_temporario_nao_esconde_o_erro_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destino = tmp_path / "dados.json"

    def replace(*_args: object, **_kwargs: object) -> NoReturn:
        raise PermissionError("replace: arquivo em uso")

    def unlink(*_args: object, **_kwargs: object) -> NoReturn:
        raise PermissionError("unlink: arquivo em uso")

    monkeypatch.setattr("options_engine.adapters.outbound.storage.json_files.os.replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(PermissionError, match="replace"):
        write_json_atomic(destino, {"valor": 1})

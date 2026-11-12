"""API da atualização automática: versão nova, início da atualização e estado, sem rede."""

import platform
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.versao import router_versao
from options_engine.adapters.outbound.atualizacao import (
    Atualizador,
    EstadoAtualizacao,
    VersaoNova,
    atualizador_do_app,
)
from options_engine.config import web_app
from options_engine.config.web_app import build_web_app

NOVA = VersaoNova(
    versao="0.9.0",
    novidades=("Montador simples", "Atualização automática"),
    tamanho=96_000_000,
    url="https://github.com/DPontello/black-scholes-pricer/releases/download/v0.9.0/Painel.exe",
    sha256="a" * 64,
)


class _AtualizadorFalso:
    def __init__(self, nova: VersaoNova | None = None) -> None:
        self.nova = nova
        self.estado_atual = EstadoAtualizacao("parado")
        self.iniciou = 0

    @property
    def atual(self) -> str:
        return "0.8.0"

    def conferir(self) -> VersaoNova | None:
        return self.nova

    def iniciar(self) -> EstadoAtualizacao:
        self.iniciou += 1
        self.estado_atual = EstadoAtualizacao("baixando", baixado=0, total=NOVA.tamanho)
        return self.estado_atual

    def estado(self) -> EstadoAtualizacao:
        return self.estado_atual


def _cliente(falso: _AtualizadorFalso) -> TestClient:
    return TestClient(create_app([router_versao(falso)]))


def test_sem_versao_nova_devolve_so_a_atual() -> None:
    resposta = _cliente(_AtualizadorFalso()).get("/api/versao")

    assert resposta.status_code == 200
    assert resposta.json() == {"atual": "0.8.0", "nova": None}


def test_com_versao_nova_devolve_versao_novidades_e_tamanho_sem_url() -> None:
    resposta = _cliente(_AtualizadorFalso(NOVA)).get("/api/versao")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "atual": "0.8.0",
        "nova": {
            "versao": "0.9.0",
            "novidades": ["Montador simples", "Atualização automática"],
            "tamanho": 96_000_000,
        },
    }
    assert "github.com" not in resposta.text
    assert "a" * 64 not in resposta.text


def test_atualizar_comeca_e_devolve_o_estado() -> None:
    falso = _AtualizadorFalso(NOVA)

    resposta = _cliente(falso).post("/api/versao/atualizar")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "fase": "baixando",
        "baixado": 0,
        "total": 96_000_000,
        "mensagem": "",
    }
    assert falso.iniciou == 1


def test_estado_da_atualizacao() -> None:
    falso = _AtualizadorFalso(NOVA)
    falso.estado_atual = EstadoAtualizacao("erro", mensagem="falhou o download")
    cliente = _cliente(falso)

    resposta = cliente.get("/api/versao/atualizar")

    assert resposta.status_code == 200
    assert resposta.json() == {
        "fase": "erro",
        "baixado": 0,
        "total": 0,
        "mensagem": "falhou o download",
    }
    assert falso.iniciou == 0


def test_web_app_monta_a_rota_de_versao_desligada_fora_do_windows_instalado(
    tmp_path: Path,
) -> None:
    web = build_web_app(config_dir=tmp_path, static_dir=None, bridge=False, machine_name="pc")

    resposta = TestClient(web).get("/api/versao")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nova"] is None
    assert isinstance(corpo["atual"], str)


def test_web_app_repassa_ao_ver_janela_para_a_saude(tmp_path: Path) -> None:
    avisos: list[str] = []
    web = build_web_app(
        config_dir=tmp_path,
        static_dir=None,
        bridge=False,
        machine_name="pc",
        ao_ver_janela=lambda: avisos.append("voltou"),
    )
    cliente = TestClient(web)

    cliente.get("/api/saude")
    assert avisos == []

    cliente.get("/api/saude", params={"janela": 1})
    assert avisos == ["voltou"]


def _ativo_do_atualizador(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, sistema: str, congelado: bool
) -> bool:
    """O ``ativo`` que o ``build_web_app`` pede ao ``atualizador_do_app``, sem sair para a rede."""
    pedidos: list[bool] = []

    def espiar(
        atual: str, *, ativo: bool, config_dir: Path, encerrar: Callable[[], None]
    ) -> Atualizador:
        pedidos.append(ativo)
        return atualizador_do_app(atual, ativo=False, config_dir=config_dir, encerrar=encerrar)

    monkeypatch.setattr(web_app, "atualizador_do_app", espiar)
    monkeypatch.setattr(platform, "system", lambda: sistema)
    build_web_app(
        config_dir=tmp_path,
        static_dir=None,
        bridge=False,
        machine_name="pc",
        frozen_dir=tmp_path if congelado else None,
    )
    (ativo,) = pedidos
    return ativo


@pytest.mark.parametrize(
    ("sistema", "congelado", "esperado"),
    [
        pytest.param("Windows", True, True, id="windows-instalado"),
        pytest.param("Windows", False, False, id="windows-da-pasta-do-codigo"),
        pytest.param("Linux", True, False, id="linux-congelado"),
        pytest.param("Linux", False, False, id="linux-da-pasta-do-codigo"),
    ],
)
def test_atualizador_so_fica_ativo_no_windows_instalado(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sistema: str,
    congelado: bool,
    esperado: bool,
) -> None:
    ativo = _ativo_do_atualizador(monkeypatch, tmp_path, sistema=sistema, congelado=congelado)

    assert ativo is esperado

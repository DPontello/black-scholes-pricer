"""App web base — saúde, mapeamento de erros de domínio e SPA."""

import importlib.metadata
from pathlib import Path

from fastapi import APIRouter
from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.domain.model.errors import InvalidDomainValueError, UnknownSymbolError


def test_saude_responde_ok_com_a_versao_do_pacote() -> None:
    resposta = TestClient(create_app([])).get("/api/saude")
    assert resposta.status_code == 200
    assert resposta.json() == {
        "status": "ok",
        "versao": importlib.metadata.version("options-engine"),
    }


def test_erro_de_dominio_vira_422_e_simbolo_desconhecido_404() -> None:
    router = APIRouter()

    @router.get("/api/teste/{caso}")
    def rota(caso: str) -> None:
        if caso == "desconhecido":
            raise UnknownSymbolError("XXXX99")
        raise InvalidDomainValueError("valor ruim")

    cliente = TestClient(create_app([router]))
    r = cliente.get("/api/teste/desconhecido")
    assert (r.status_code, r.json()) == (404, {"erro": "UnknownSymbolError", "mensagem": "XXXX99"})
    r = cliente.get("/api/teste/outro")
    assert (r.status_code, r.json()["erro"]) == (422, "InvalidDomainValueError")


def test_spa_devolve_index_fora_da_api_e_404_json_dentro(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=raiz></div>", encoding="utf-8")
    cliente = TestClient(create_app([], static_dir=tmp_path))
    assert cliente.get("/mercado").text == "<div id=raiz></div>"
    assert cliente.get("/api/inexistente").status_code == 404


def test_spa_serve_arquivo_existente_e_nao_escapa_do_diretorio(tmp_path: Path) -> None:
    estatico = tmp_path / "estatico"
    (estatico / "assets").mkdir(parents=True)
    (estatico / "index.html").write_text("<div id=raiz></div>", encoding="utf-8")
    (estatico / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "segredo.txt").write_text("segredo", encoding="utf-8")
    cliente = TestClient(create_app([], static_dir=estatico))
    assert cliente.get("/assets/app.js").text == "console.log(1)"
    fuga = cliente.get("/..%2Fsegredo.txt")
    assert fuga.text == "<div id=raiz></div>"


def test_rota_inexistente_da_api_devolve_404_json_mesmo_com_spa(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=raiz></div>", encoding="utf-8")
    r = TestClient(create_app([], static_dir=tmp_path)).get("/api/inexistente")
    assert (r.status_code, r.headers["content-type"]) == (404, "application/json")


def test_caminho_invalido_cai_no_index_e_nunca_em_500(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=raiz></div>", encoding="utf-8")
    r = TestClient(create_app([], static_dir=tmp_path)).get("/%00")
    assert (r.status_code, r.text) == (200, "<div id=raiz></div>")


def test_docs_da_api_ficam_sob_api_e_nao_sombreiam_a_spa(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<div id=raiz></div>", encoding="utf-8")
    cliente = TestClient(create_app([], static_dir=tmp_path))
    for caminho in ("/docs", "/redoc", "/openapi.json"):
        assert cliente.get(caminho).text == "<div id=raiz></div>"
    r = cliente.get("/api/openapi.json")
    assert (r.status_code, r.headers["content-type"]) == (200, "application/json")
    assert "/api/saude" in r.json()["paths"]

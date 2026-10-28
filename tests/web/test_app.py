"""App web base — saúde, mapeamento de erros de domínio e SPA."""

import importlib.metadata
from pathlib import Path

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

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
    assert r.json() == {"erro": "NaoEncontrado", "mensagem": "Recurso não encontrado."}


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


class _CorpoDeTeste(BaseModel):
    nome: str
    ativos: list[str] = []
    cdi: float = 0.0

    @field_validator("nome")
    @classmethod
    def _sem_vazio(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("nome vazio")
        return valor


def _cliente_de_validacao() -> TestClient:
    router = APIRouter()

    @router.post("/api/teste/corpo")
    def corpo(dados: _CorpoDeTeste) -> dict[str, str]:
        return {"nome": dados.nome}

    @router.get("/api/teste/consulta")
    def consulta(limite: int) -> dict[str, int]:
        return {"limite": limite}

    return TestClient(create_app([router]))


def test_validacao_de_campo_obrigatorio_vira_422_em_portugues() -> None:
    r = _cliente_de_validacao().post("/api/teste/corpo", json={})
    assert r.status_code == 422
    corpo = r.json()
    assert (corpo["erro"], corpo["mensagem"]) == ("RequisicaoInvalida", "campo 'nome' obrigatório")
    assert corpo["detalhes"][0]["type"] == "missing"
    assert corpo["detalhes"][0]["loc"] == ["body", "nome"]


def test_validacao_resume_todos_os_campos_com_problema() -> None:
    r = _cliente_de_validacao().post(
        "/api/teste/corpo", json={"nome": 3, "ativos": "PETR4", "cdi": "abc"}
    )
    assert r.status_code == 422
    assert r.json()["mensagem"] == (
        "campo 'nome' deve ser texto; campo 'ativos' deve ser uma lista; "
        "campo 'cdi' deve ser um número"
    )


def test_validacao_aponta_o_indice_do_item_invalido_da_lista() -> None:
    r = _cliente_de_validacao().post("/api/teste/corpo", json={"nome": "x", "ativos": ["A", 7]})
    assert (r.status_code, r.json()["mensagem"]) == (422, "campo 'ativos[1]' deve ser texto")


def test_validacao_de_parametro_de_consulta_nomeia_o_parametro() -> None:
    cliente = _cliente_de_validacao()
    r = cliente.get("/api/teste/consulta")
    assert (r.status_code, r.json()["mensagem"]) == (422, "campo 'limite' obrigatório")
    r = cliente.get("/api/teste/consulta", params={"limite": "muitos"})
    assert (r.status_code, r.json()["mensagem"]) == (422, "campo 'limite' deve ser um número")


def test_validacao_sem_json_valido_ou_sem_objeto_fala_do_corpo() -> None:
    cliente = _cliente_de_validacao()
    r = cliente.post(
        "/api/teste/corpo", content="{nome:", headers={"content-type": "application/json"}
    )
    assert (r.status_code, r.json()["erro"]) == (422, "RequisicaoInvalida")
    assert r.json()["mensagem"] == "corpo da requisição não é um JSON válido"
    r = cliente.post("/api/teste/corpo", json=["nome"])
    assert r.json()["mensagem"] == "corpo da requisição deve ser um objeto JSON"
    r = cliente.post("/api/teste/corpo")
    assert r.json()["mensagem"] == "corpo da requisição obrigatório"


def test_validacao_com_validador_proprio_mantem_detalhes_serializaveis() -> None:
    # O ``ctx`` do pydantic carrega a exceção do validador; sem tratamento o JSON quebra.
    r = _cliente_de_validacao().post("/api/teste/corpo", json={"nome": "  "})
    assert r.status_code == 422
    corpo = r.json()
    assert corpo["mensagem"] == "campo 'nome' inválido"
    assert corpo["detalhes"][0]["type"] == "value_error"


@pytest.mark.parametrize(
    ("metodo", "caminho", "status", "erro", "mensagem"),
    [
        ("get", "/api/nao-existe", 404, "NaoEncontrado", "Recurso não encontrado."),
        ("post", "/api/saude", 405, "MetodoNaoPermitido", "Método não permitido neste endereço."),
    ],
)
def test_erro_http_do_starlette_usa_o_formato_unico_e_mantem_o_status(
    metodo: str, caminho: str, status: int, erro: str, mensagem: str
) -> None:
    r = getattr(TestClient(create_app([])), metodo)(caminho)
    assert r.status_code == status
    assert r.json() == {"erro": erro, "mensagem": mensagem}


def test_405_mantem_o_cabecalho_allow() -> None:
    r = TestClient(create_app([])).post("/api/saude")
    assert r.headers["allow"] == "GET"


def test_outros_erros_http_viram_erro_http_com_o_status_original() -> None:
    router = APIRouter()

    @router.get("/api/teste/proibido")
    def proibido() -> None:
        raise HTTPException(status_code=403, detail="forbidden")

    r = TestClient(create_app([router])).get("/api/teste/proibido")
    assert r.status_code == 403
    assert r.json() == {"erro": "ErroHttp", "mensagem": "Erro HTTP 403."}


def test_spa_sem_index_devolve_404_no_formato_unico(tmp_path: Path) -> None:
    r = TestClient(create_app([], static_dir=tmp_path)).get("/mercado")
    assert (r.status_code, r.json()["erro"]) == (404, "NaoEncontrado")

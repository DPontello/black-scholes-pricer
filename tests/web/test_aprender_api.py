"""API da aba Aprender: os exemplos das 18 operações, sem perfil aberto."""

from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.aprender import router_aprender


def _cliente() -> TestClient:
    return TestClient(create_app([router_aprender()]))


def test_exemplos_sem_perfil_aberto_trazem_as_18_operacoes() -> None:
    resposta = _cliente().get("/api/aprender/exemplos")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) == 18
    assert {i["familia"] for i in corpo} == {"renda", "direcionais", "volatilidade", "protecao"}


def test_venda_coberta_com_os_numeros_do_exemplo() -> None:
    corpo = _cliente().get("/api/aprender/exemplos").json()
    item = next(i for i in corpo if i["chave"] == "venda_coberta")

    assert item["nome"] == "venda coberta"
    assert item["spot"] == 50.0
    assert item["pernas"] == [
        {"tipo": "call", "lado": "venda", "strike": 52.0, "premio": 1.14, "quantidade": 100}
    ]
    assert item["acoes"] == 100
    assert item["premio_liquido"] == 114.0
    assert item["cenarios"] == [
        {"preco": 45.0, "resultado": -386.0},
        {"preco": 50.0, "resultado": 114.0},
        {"preco": 55.0, "resultado": 314.0},
    ]
    assert len(item["empates"]) == 1 and abs(item["empates"][0] - 48.86) < 1e-9
    assert (item["ganho_maximo"], item["perda_maxima"]) == (314.0, 4886.0)
    assert len(item["curva"]) == 81
    assert item["curva"][0][0] == 30.0 and item["curva"][-1][0] == 70.0


def test_straddle_vendido_nao_tem_limite_de_perda() -> None:
    corpo = _cliente().get("/api/aprender/exemplos").json()
    item = next(i for i in corpo if i["chave"] == "straddle_vendido")

    assert item["perda_maxima"] is None
    assert item["acoes"] == 0
    assert item["ganho_maximo"] is not None

"""API do montador e das simulações: serviço real, mercado falso e perfil em pasta temporária."""

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.builder import router_montador
from options_engine.adapters.inbound.web.profiles import router_perfis
from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.storage.simulations import JsonSimulationRepository
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.application.use_cases.simulations import SimulationService
from options_engine.application.use_cases.strategy_builder import StrategyBuilderService
from tests.application._fakes import FakeProfileRepository
from tests.application._mercado_falso import CALENDARIO, MercadoFalso
from tests.income._builders import make_cost_schedule

AGORA = datetime(2026, 11, 4, 14, 0, tzinfo=UTC)
TRAVA = {
    "ativo": "petr4",
    "pernas": [
        {"ticker": "PETRK300", "lado": "compra", "quantidade": 100},
        {"ticker": "PETRK320", "lado": "venda", "quantidade": 100},
    ],
    "modelo": "trava_alta_call",
}


def _cliente(pasta: Path | None) -> TestClient:
    perfis = ProfileService(FakeProfileRepository(), FixedClock(AGORA), "PC-TESTE")
    if pasta is not None:
        perfis.create("Hugo", str(pasta))
        perfis.open("Hugo")
    montador = StrategyBuilderService(
        MercadoFalso(),
        CALENDARIO,
        B3_UTC_OFFSET,
        schedules=[make_cost_schedule()],
        lots={"PETRK300": 100, "PETRK320": 100}.get,
    )
    simulacoes = SimulationService(
        lambda: JsonSimulationRepository(perfis.active_folder()),
        FixedClock(AGORA),
        lambda: uuid.uuid4().hex,
    )
    return TestClient(create_app([router_perfis(perfis), router_montador(montador, simulacoes)]))


def test_modelos_tem_as_quatro_familias_e_a_forma_de_cada_um() -> None:
    modelos = _cliente(None).get("/api/montador/modelos").json()
    assert len(modelos) == 18
    assert {m["familia"] for m in modelos} == {"renda", "direcionais", "volatilidade", "protecao"}
    coberta = next(m for m in modelos if m["chave"] == "venda_coberta")
    assert coberta == {
        "chave": "venda_coberta",
        "familia": "renda",
        "nome": "venda coberta",
        "pernas": [{"tipo": "call", "lado": "venda", "proporcao": 1, "passo": 1}],
        "acao": "compra",
    }


def test_analise_traz_pernas_vencimento_hoje_e_avisos() -> None:
    resposta = _cliente(None).post("/api/montador/analise", json=TRAVA)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["nome"], corpo["ativo"], corpo["vencimento"], corpo["fonte"]) == (
        "trava de alta com call",
        "PETR4",
        "2026-11-19",
        "ao_vivo",
    )
    assert [(p["ticker"], p["lado"], p["origem"], p["lote"]) for p in corpo["pernas"]] == [
        ("PETRK300", "compra", "executavel", 100),
        ("PETRK320", "venda", "executavel", 100),
    ]
    vencimento = corpo["no_vencimento"]
    assert vencimento["caixa"] < 0 and vencimento["ganho_max"] > 0
    assert 0 < vencimento["probabilidade"] < 1
    assert set(corpo["hoje"]["gregas"]) == {"delta", "gamma", "theta_dia_util", "vega_ponto", "rho"}
    assert len(corpo["hoje"]["grade"]["valores"]) == 7
    assert corpo["avisos"] == [] and corpo["hoje_indisponivel"] is None
    assert {"spot", "payoff", "resultado", "liquido"} == set(corpo["curva"][0])


def test_pedido_invalido_e_serie_fora_da_cadeia() -> None:
    cliente = _cliente(None)
    zero = {**TRAVA, "pernas": [{"ticker": "PETRK300", "lado": "compra", "quantidade": 0}]}
    resposta = cliente.post("/api/montador/analise", json=zero)
    assert (resposta.status_code, resposta.json()["erro"]) == (422, "RequisicaoInvalida")
    fora = {"ativo": "PETR4", "pernas": [{"ticker": "PETRK999", "lado": "compra", "quantidade": 1}]}
    resposta = cliente.post("/api/montador/analise", json=fora)
    assert (resposta.status_code, resposta.json()["erro"]) == (422, "UnderlyingUnavailableError")
    resposta = cliente.post("/api/montador/analise", json={**TRAVA, "ativo": "XPTO3"})
    assert resposta.status_code == 404


def test_simulacoes_sem_perfil_aberto_sao_404() -> None:
    resposta = _cliente(None).get("/api/simulacoes")
    assert (resposta.status_code, resposta.json()["erro"]) == (404, "NoActiveProfileError")


def test_simulacao_salva_listada_aberta_e_apagada(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    criada = cliente.post("/api/simulacoes", json={**TRAVA, "nome": "trava de novembro"})
    assert criada.status_code == 201
    simulacao = criada.json()
    assert simulacao["nome"] == "trava de novembro"
    assert simulacao["pedido"]["ativo"] == "PETR4"
    assert simulacao["pedido"]["modelo"] == "trava_alta_call"
    lista = cliente.get("/api/simulacoes").json()
    assert [s["id"] for s in lista["simulacoes"]] == [simulacao["id"]] and lista["ilegiveis"] == []
    assert cliente.get(f"/api/simulacoes/{simulacao['id']}").json() == simulacao
    assert cliente.delete(f"/api/simulacoes/{simulacao['id']}").status_code == 204
    apagada = cliente.get(f"/api/simulacoes/{simulacao['id']}")
    assert (apagada.status_code, apagada.json()["erro"]) == (404, "UnknownRecordError")


def test_simulacao_ilegivel_aparece_na_lista(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    (tmp_path / "simulacoes").mkdir()
    (tmp_path / "simulacoes" / "quebrada.json").write_text("{", encoding="utf-8")
    lista = cliente.get("/api/simulacoes").json()
    (ilegivel,) = lista["ilegiveis"]
    assert ilegivel["arquivo"].endswith("quebrada.json") and "JSON" in ilegivel["motivo"]


def test_perfil_com_pasta_vazia_e_recusado() -> None:
    resposta = _cliente(None).post("/api/perfis", json={"nome": "Teste", "pasta": ""})
    assert (resposta.status_code, resposta.json()["erro"]) == (422, "InvalidDomainValueError")

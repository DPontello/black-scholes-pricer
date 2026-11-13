"""API dos alertas: carteira, alertas e rolagem reais na pasta do perfil, mercado falso."""

import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import approx

from options_engine.adapters.inbound.web.alerts import alertas_out, router_alertas
from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.portfolio import router_carteira
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.storage.dismissed_alerts import JsonDismissedAlerts
from options_engine.adapters.outbound.storage.operations import JsonOperationRepository
from options_engine.application.ports.alerts import AlertsView
from options_engine.application.ports.inbound import BuilderLegInput, BuilderRequest
from options_engine.application.use_cases.alerts import AlertService
from options_engine.application.use_cases.portfolio import PortfolioService
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.application.use_cases.roll import RollService
from options_engine.domain.alerts.model import Alert, AlertKind
from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from tests.application._fakes import FakeProfileRepository
from tests.application._mercado_falso import CALENDARIO, MercadoFalso, cadeia, serie
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import NOVEMBRO, put

B3 = timezone(timedelta(hours=-3))
DIA_17 = datetime(2026, 11, 17, 14, 0, tzinfo=B3)  # dois dias úteis até 19/11
DEZEMBRO = date(2026, 12, 17)
PUT = put(28.0)
PUT_VENDIDA: dict[str, object] = {
    "ativo": "PETR4",
    "nome": "put coberta",
    "data": "2026-11-04",
    "modelo": "put_coberta",
    "pernas": [
        {"ticker": "PETRW280", "lado": "venda", "execucoes": [{"quantidade": 100, "preco": 0.5}]}
    ],
}


def _termos(ticker: str, _ativo: str) -> OptionTerms | str:
    return PUT.terms if ticker == "PETRW280" else f"{ticker}: série desconhecida no cadastro"


def _mercado() -> MercadoFalso:
    return MercadoFalso(
        chains={
            "PETR4": cadeia(
                (
                    serie("PETRW280", 28.0, OptionType.PUT),
                    serie("PETRX280", 28.0, OptionType.PUT, vencimento=DEZEMBRO),
                )
            )
        },
        quotes={
            "PETR4": UnderlyingQuote(
                "PETR4", 28.3, None, None, None, 0, 0.0, DIA_17, DataSource.AO_VIVO
            )
        },
        option_quotes={
            "PETRW280": OptionQuote(
                OptionContract("PETRW280", PUT.terms), 0.30, 0.35, None, 0, 0.0, DIA_17
            )
        },
    )


def _sugerir(ativo: str, modelo: str, vencimento: date) -> BuilderRequest:
    assert vencimento == DEZEMBRO
    return BuilderRequest(ativo, (BuilderLegInput("PETRX280", Side.SELL, 100),), None, modelo)


def _cliente(pasta: Path | None) -> TestClient:
    relogio = FixedClock(DIA_17)
    perfis = ProfileService(FakeProfileRepository(), relogio, "PC-TESTE")
    if pasta is not None:
        perfis.create("Hugo", str(pasta))
        perfis.open("Hugo")
    mercado = _mercado()
    carteira = PortfolioService(
        lambda: JsonOperationRepository(perfis.active_folder()),
        relogio,
        [make_cost_schedule()],
        lambda: uuid.uuid4().hex,
        B3,
        market=mercado,
        calendar=CALENDARIO,
    )
    alertas = AlertService(
        lambda: JsonDismissedAlerts(perfis.active_folder()),
        lambda: perfis.active().alert_settings,
        relogio,
        B3,
        market=mercado,
        calendar=CALENDARIO,
    )
    rolagem = RollService(carteira.open_operations, _sugerir, relogio, B3, market=mercado)

    def sem_fechamento(_ativo: str, _dia: date) -> float | None:
        return None

    rotas = [
        router_carteira(carteira, closes=sem_fechamento, terms=_termos),
        router_alertas(alertas, rolagem, carteira, closes=sem_fechamento),
    ]
    return TestClient(create_app(rotas))


def _com_put_vendida(tmp_path: Path) -> tuple[TestClient, str]:
    cliente = _cliente(tmp_path)
    resposta = cliente.post("/api/carteira/operacoes", json=PUT_VENDIDA)
    assert resposta.status_code == 201, resposta.json()
    return cliente, str(resposta.json()["id"])


def test_lista_com_risco_de_exercicio_e_vencimento(tmp_path: Path) -> None:
    cliente, operacao = _com_put_vendida(tmp_path)
    corpo = cliente.get("/api/alertas").json()
    assert (corpo["fonte"], corpo["dispensados"]) == ("ao_vivo", 0)
    risco, vencimento = corpo["alertas"]
    assert risco == {
        "chave": f"risco_de_exercicio:{operacao}:0",
        "tipo": "risco_de_exercicio",
        "operacao": operacao,
        "nome": "put coberta",
        "ativo": "PETR4",
        "perna": 0,
        "ticker": "PETRW280",
        "vencimento": NOVEMBRO.isoformat(),
        "dias_uteis": 2,
        "dentro_do_dinheiro": False,
        "total": None,
        "limite": None,
        "pode_rolar": True,
        "estimado": False,
    }
    assert (vencimento["tipo"], vencimento["dentro_do_dinheiro"]) == ("vencimento_proximo", None)


def test_stop_estimado_e_stop_sem_preco_saem_rotulados() -> None:
    estimado = Alert(
        "stop:op1:-",
        AlertKind.STOP,
        "op1",
        "trava",
        "PETR4",
        total=-60.0,
        limit=50.0,
        estimated=True,
    )
    sem_preco = Alert(
        "stop_sem_preco:op2:-", AlertKind.STOP_UNPRICED, "op2", "put", "PETR4", limit=50.0
    )
    corpo = alertas_out(AlertsView((estimado, sem_preco), 0, DataSource.AO_VIVO)).model_dump()
    primeiro, segundo = corpo["alertas"]
    assert (primeiro["tipo"], primeiro["total"], primeiro["estimado"]) == ("stop", -60.0, True)
    assert (segundo["tipo"], segundo["limite"], segundo["estimado"]) == (
        "stop_sem_preco",
        50.0,
        False,
    )


def test_dispensar_e_restaurar(tmp_path: Path) -> None:
    cliente, operacao = _com_put_vendida(tmp_path)
    chave = f"risco_de_exercicio:{operacao}:0"
    assert cliente.post(f"/api/alertas/{chave}/dispensar").status_code == 204
    corpo = cliente.get("/api/alertas").json()
    assert ([a["tipo"] for a in corpo["alertas"]], corpo["dispensados"]) == (
        ["vencimento_proximo"],
        1,
    )
    assert (tmp_path / "alertas.json").exists()

    assert cliente.post("/api/alertas/restaurar").status_code == 204
    assert len(cliente.get("/api/alertas").json()["alertas"]) == 2


def test_alvo_pela_api_da_carteira_vira_alerta(tmp_path: Path) -> None:
    cliente, operacao = _com_put_vendida(tmp_path)
    # Recomprar a 0,35 com a venda a 0,50: +15 bruto, menos os custos da tabela.
    cliente.put(f"/api/carteira/operacoes/{operacao}/limites", json={"alvo": 1.0})
    tipos = [a["tipo"] for a in cliente.get("/api/alertas").json()["alertas"]]
    assert tipos == ["risco_de_exercicio", "vencimento_proximo", "alvo"]


def test_rolagem_com_o_pedido_e_o_caixa(tmp_path: Path) -> None:
    cliente, operacao = _com_put_vendida(tmp_path)
    corpo = cliente.get(f"/api/alertas/rolagem/{operacao}").json()
    assert corpo["pedido"] == {
        "ativo": "PETR4",
        "pernas": [{"ticker": "PETRX280", "lado": "venda", "quantidade": 100, "preco": None}],
        "acao": None,
        "modelo": "put_coberta",
    }
    assert (corpo["vencimento_atual"], corpo["vencimento_novo"]) == (
        NOVEMBRO.isoformat(),
        DEZEMBRO.isoformat(),
    )
    assert corpo["caixa_de_zerar"] == approx(-35.0)
    assert (corpo["nome"], corpo["fonte"]) == ("put coberta", "ao_vivo")


def test_rolagem_de_operacao_desconhecida_404(tmp_path: Path) -> None:
    resposta = _cliente(tmp_path).get("/api/alertas/rolagem/naoexiste123")
    assert resposta.status_code == 404


def test_sem_perfil_aberto_404() -> None:
    resposta = _cliente(None).get("/api/alertas")
    assert (resposta.status_code, resposta.json()["erro"]) == (404, "NoActiveProfileError")

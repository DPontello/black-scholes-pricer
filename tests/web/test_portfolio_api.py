"""API da carteira: serviço e repositório reais na pasta temporária do perfil, mercado falso."""

import uuid
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from pytest import approx

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.portfolio import router_carteira
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.storage.operations import JsonOperationRepository
from options_engine.application.use_cases.portfolio import PortfolioService
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.enums import Side
from options_engine.domain.portfolio.model import Close, Exercise, Expired, Open
from tests.application._fakes import FakeProfileRepository
from tests.application._mercado_falso import CALENDARIO, INSTANTE, MercadoFalso
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import NOVEMBRO, call, operacao, put

B3 = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 4, 14, 0, tzinfo=B3)
TERMOS = {r.symbol: r.terms for r in (call(30.0), call(32.0), put(28.0))}


def _termos(ticker: str, _ativo: str) -> OptionTerms | str:
    return TERMOS.get(ticker, f"{ticker}: série desconhecida no cadastro")


def _cliente(
    pasta: Path | None,
    *,
    agora: datetime = AGORA,
    mercado: MercadoFalso | None = None,
    fechamentos: dict[tuple[str, date], float] | None = None,
) -> TestClient:
    relogio = FixedClock(agora)
    perfis = ProfileService(FakeProfileRepository(), relogio, "PC-TESTE")
    if pasta is not None:
        perfis.create("Hugo", str(pasta))
        perfis.open("Hugo")
    carteira = PortfolioService(
        lambda: JsonOperationRepository(perfis.active_folder()),
        relogio,
        [make_cost_schedule()],
        lambda: uuid.uuid4().hex,
        B3,
        market=MercadoFalso() if mercado is None else mercado,
        calendar=CALENDARIO,
    )
    fechou = fechamentos or {}
    rotas = router_carteira(carteira, closes=lambda s, d: fechou.get((s, d)), terms=_termos)
    return TestClient(create_app([rotas]))


def _execucao(quantidade: int, preco: float) -> dict[str, object]:
    return {"quantidade": quantidade, "preco": preco}


def _perna(ticker: str, lado: str, quantidade: int, preco: float) -> dict[str, object]:
    return {"ticker": ticker, "lado": lado, "execucoes": [_execucao(quantidade, preco)]}


TRAVA: dict[str, object] = {
    "ativo": "petr4",
    "nome": "trava de alta",
    "data": "2026-11-04",
    "pernas": [_perna("petrk300", "compra", 100, 1.20), _perna("PETRK320", "venda", 100, 0.60)],
}
COBERTA_DA_CARTEIRA: dict[str, object] = {
    "ativo": "PETR4",
    "nome": "coberta",
    "data": "2026-11-04",
    "pernas": [_perna("PETRK320", "venda", 100, 1.00)],
    "acao": {"lado": "compra", "origem": "carteira"},
}


def _cotacao(ticker: str, bid: float, ask: float) -> OptionQuote:
    return OptionQuote(OptionContract(ticker, TERMOS[ticker]), bid, ask, None, 0, 0.0, INSTANTE)


def _registrar(cliente: TestClient, corpo: Mapping[str, object]) -> str:
    resposta = cliente.post("/api/carteira/operacoes", json=corpo)
    assert resposta.status_code == 201, resposta.json()
    return str(resposta.json()["id"])


def test_registra_e_mostra_a_carteira_a_mercado(tmp_path: Path) -> None:
    mercado = MercadoFalso(
        option_quotes={
            "PETRK300": _cotacao("PETRK300", 1.50, 1.60),
            "PETRK320": _cotacao("PETRK320", 0.40, 0.45),
        }
    )
    cliente = _cliente(tmp_path, mercado=mercado)
    trava = _registrar(cliente, TRAVA)
    assert len(list((tmp_path / "operacoes").iterdir())) == 1

    carteira = cliente.get("/api/carteira").json()
    assert (carteira["fonte"], carteira["avisos"], carteira["ilegiveis"]) == ("ao_vivo", [], [])
    (operacao,) = carteira["operacoes"]
    assert (operacao["id"], operacao["nome"], operacao["ativo"]) == (
        trava,
        "trava de alta",
        "PETR4",
    )
    comprada, vendida = operacao["pernas"]
    assert comprada == {
        "indice": 0,
        "ticker": "PETRK300",
        "tipo": "call",
        "strike": 30.0,
        "vencimento": "2026-11-19",
        "estilo": comprada["estilo"],
        "origem": None,
        "lado": "compra",
        "quantidade": 100,
        "preco_medio": 1.20,
        "realizado": 0.0,
        "marca": {
            "preco": 1.50,
            "nao_realizado": comprada["marca"]["nao_realizado"],
            "teorico": None,
            "motivo": None,
        },
    }
    assert abs(comprada["marca"]["nao_realizado"] - 30.0) < 1e-9
    assert vendida["marca"]["preco"] == 0.45
    assert abs(operacao["nao_realizado"] - 45.0) < 1e-9
    assert operacao["eventos"][0] == {
        "tipo": "abertura",
        "perna": 0,
        "data": "2026-11-04",
        "lado": "compra",
        "quantidade": 100,
        "preco": 1.20,
        "custos": None,
        "custo_medio": None,
        "para": None,
    }
    assert [(t["ticker"], t["lado"], t["quantidade"]) for t in carteira["totais"]] == [
        ("PETRK300", "compra", 100),
        ("PETRK320", "venda", 100),
    ]


def test_encerrar_parcial_e_depois_o_resto_leva_ao_historico(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    trava = _registrar(cliente, TRAVA)
    url = f"/api/carteira/operacoes/{trava}/encerrar"
    for perna, quantidade, preco in ((0, 40, 1.50), (0, 60, 1.50), (1, 100, 0.40)):
        corpo = {"perna": perna, "quantidade": quantidade, "preco": preco, "data": "2026-11-05"}
        resposta = cliente.post(url, json={**corpo, "custos": 0.0})
        assert (resposta.status_code, resposta.json()) == (200, {"id": trava})
    assert cliente.get("/api/carteira").json()["operacoes"] == []
    (encerrada,) = cliente.get("/api/carteira/historico").json()
    assert encerrada["id"] == trava and encerrada["nao_realizado"] is None
    assert [p["marca"] for p in encerrada["pernas"]] == [None, None]


def test_coberta_da_carteira_atribuida_tira_as_acoes_a_mao(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    acoes = {"ativo": "petr4", "quantidade": 100, "preco_medio": 28.0, "data": "2026-11-03"}
    resposta = cliente.post("/api/carteira/acoes", json=acoes)
    assert resposta.status_code == 201
    a_mao = resposta.json()["id"]
    coberta = _registrar(cliente, COBERTA_DA_CARTEIRA)
    atribuicao = {"perna": 0, "quantidade": 100, "data": NOVEMBRO.isoformat()}
    resposta = cliente.post(f"/api/carteira/operacoes/{coberta}/atribuir", json=atribuicao)
    assert resposta.status_code == 200

    historico = {o["id"]: o for o in cliente.get("/api/carteira/historico").json()}
    assert set(historico) == {a_mao, coberta}
    venda = historico[coberta]["eventos"][-1]
    assert (venda["tipo"], venda["preco"], venda["custo_medio"]) == ("encerramento", 33.0, 28.0)
    saida = historico[a_mao]["eventos"][-1]
    assert (saida["tipo"], saida["quantidade"], saida["para"]) == ("transferencia", 100, coberta)


def test_erros_de_regra_saem_em_422_com_o_formato_unico(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    sem_acoes = cliente.post("/api/carteira/operacoes", json=COBERTA_DA_CARTEIRA)
    assert sem_acoes.status_code == 422
    assert sem_acoes.json() == {
        "erro": "InvalidDomainValueError",
        "mensagem": "PETR4: 0 ações livres na carteira; a operação cobre 100",
    }
    fora = {**TRAVA, "pernas": [_perna("PETRZ999", "compra", 100, 1.0)]}
    resposta = cliente.post("/api/carteira/operacoes", json=fora)
    assert (resposta.status_code, resposta.json()["mensagem"]) == (
        422,
        "PETRZ999: série desconhecida no cadastro",
    )
    trava = _registrar(cliente, TRAVA)
    exercicio = {"perna": 1, "quantidade": 100, "data": "2026-11-19"}
    resposta = cliente.post(f"/api/carteira/operacoes/{trava}/exercer", json=exercicio)
    assert resposta.status_code == 422 and "comprada" in resposta.json()["mensagem"]
    demais = {"perna": 0, "quantidade": 200, "preco": 1.0, "data": "2026-11-05"}
    resposta = cliente.post(f"/api/carteira/operacoes/{trava}/encerrar", json=demais)
    assert resposta.status_code == 422 and "em aberto" in resposta.json()["mensagem"]


def test_operacao_desconhecida_e_sem_perfil_sao_404(tmp_path: Path) -> None:
    corpo = {"perna": 0, "quantidade": 100, "preco": 1.0, "data": "2026-11-05"}
    resposta = _cliente(tmp_path).post("/api/carteira/operacoes/abcdefgh123/encerrar", json=corpo)
    assert (resposta.status_code, resposta.json()["erro"]) == (404, "UnknownRecordError")
    resposta = _cliente(None).get("/api/carteira")
    assert (resposta.status_code, resposta.json()["erro"]) == (404, "NoActiveProfileError")


def test_requisicao_invalida_e_recusada_antes_do_servico(tmp_path: Path) -> None:
    cliente = _cliente(tmp_path)
    sem_execucao = {**TRAVA, "pernas": [{"ticker": "PETRK300", "lado": "compra", "execucoes": []}]}
    for url, corpo in (
        ("/api/carteira/operacoes", sem_execucao),
        ("/api/carteira/acoes", {"ativo": "PETR4", "quantidade": 0, "preco_medio": 28.0}),
    ):
        resposta = cliente.post(url, json=corpo)
        assert (resposta.status_code, resposta.json()["erro"]) == (422, "RequisicaoInvalida")
    assert not (tmp_path / "operacoes").exists()


def test_abrir_a_carteira_roda_o_vencimento_com_o_fechamento_importado(tmp_path: Path) -> None:
    strangle = {
        **TRAVA,
        "nome": "strangle",
        "pernas": [_perna("PETRK320", "venda", 100, 1.0), _perna("PETRW280", "venda", 100, 0.5)],
    }
    _registrar(_cliente(tmp_path), strangle)
    depois = datetime(2026, 11, 20, 10, 0, tzinfo=B3)
    cliente = _cliente(tmp_path, agora=depois, fechamentos={("PETR4", NOVEMBRO): 33.0})
    carteira = cliente.get("/api/carteira").json()
    (operacao,) = carteira["operacoes"]
    assert carteira["avisos"] == [
        {
            "operacao": operacao["id"],
            "perna": 0,
            "ticker": "PETRK320",
            "vencimento": "2026-11-19",
            "situacao": "registrar_exercicio",
        }
    ]
    assert operacao["eventos"][-1] == {
        "tipo": "po",
        "perna": 1,
        "data": "2026-11-19",
        "lado": None,
        "quantidade": None,
        "preco": None,
        "custos": None,
        "custo_medio": None,
        "para": None,
    }


def test_arquivo_ilegivel_aparece_na_carteira(tmp_path: Path) -> None:
    (tmp_path / "operacoes").mkdir()
    (tmp_path / "operacoes" / "2026-11-04_PETR4_aaaaaaaa.json").write_text("{", encoding="utf-8")
    (ilegivel,) = _cliente(tmp_path).get("/api/carteira").json()["ilegiveis"]
    assert ilegivel["arquivo"].endswith("aaaaaaaa.json") and "JSON" in ilegivel["motivo"]


def test_ir_mensal_mais_recente_primeiro(tmp_path: Path) -> None:
    venda_de_put = operacao(
        [put(28.0)],
        [
            Open(0, date(2026, 11, 3), Side.SELL, 200, 0.80, 2.00),
            Close(0, date(2026, 11, 12), 100, 0.20, 1.00),
            Expired(0, NOVEMBRO),
        ],
        id_="venda-de-put-1",
        nome="venda de put",
    )
    JsonOperationRepository(tmp_path).save(venda_de_put)
    resposta = _cliente(tmp_path).get("/api/carteira/ir-mensal")
    assert resposta.status_code == 200, resposta.json()
    corpo = resposta.json()
    assert [m["mes"] for m in corpo] == ["2026-11"]
    mes = corpo[0]
    assert mes["ir_do_mes"] == approx(20.55)
    assert mes["pagar_ate"] == "2026-12-30"
    assert mes["pecas"][1] == {
        "data": "2026-11-19",
        "ticker": "PETRW280",
        "categoria": "comum",
        "tipo": "po",
        "resultado": approx(79.0),
        "operacoes": ["venda de put"],
    }
    assert mes["exercicios"] == []


def test_ir_mensal_com_dois_meses_lista_o_mais_recente_primeiro(tmp_path: Path) -> None:
    outubro = date(2026, 10, 5)
    JsonOperationRepository(tmp_path).save(
        operacao(
            [call(30.0)],
            [Open(0, outubro, Side.SELL, 100, 1.00, 0.0), Close(0, outubro, 100, 0.40, 0.0)],
            id_="day-trade-1",
            nome="day trade de outubro",
        )
    )
    JsonOperationRepository(tmp_path).save(
        operacao(
            [put(28.0)],
            [Open(0, date(2026, 11, 3), Side.SELL, 100, 0.80, 0.0), Expired(0, NOVEMBRO)],
            id_="venda-de-put-1",
            nome="venda de put",
        )
    )
    JsonOperationRepository(tmp_path).save(
        operacao(
            [call(32.0)],
            [Open(0, date(2026, 11, 3), Side.BUY, 100, 0.40, 0.0), Exercise(0, NOVEMBRO, 100, 0.0)],
            id_="call-exercida-1",
            nome="call exercida",
        )
    )
    corpo = _cliente(tmp_path).get("/api/carteira/ir-mensal").json()
    assert [m["mes"] for m in corpo] == ["2026-11", "2026-10"]
    assert corpo[0]["exercicios"] == [
        {"data": "2026-11-19", "ticker": "PETRK320", "operacao": "call exercida"}
    ]
    assert corpo[1]["ir_do_mes"] == approx(12.0)
    assert corpo[1]["pagar_ate"] == "2026-11-30"


def test_ir_mensal_sem_perfil() -> None:
    resposta = _cliente(None).get("/api/carteira/ir-mensal")
    assert (resposta.status_code, resposta.json()["erro"]) == (404, "NoActiveProfileError")

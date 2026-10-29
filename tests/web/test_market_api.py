"""API de mercado e WebSocket ao vivo (Task 13) — serviço de mercado falso, perfis em memória."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from options_engine.adapters.inbound.web.app import create_app
from options_engine.adapters.inbound.web.market import router_mercado
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.inbound import (
    DEFAULT_CHAIN_EXPIRIES,
    ChainView,
    ExpiryBlock,
    MarketStatus,
    SeriesRow,
    WatchRow,
)
from options_engine.application.ports.outbound import CadastroFreshness
from options_engine.application.use_cases.profiles import ProfileService
from options_engine.domain.model.chain import RejectedSeries
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import UnderlyingUnavailableError, UnknownSymbolError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from tests.application._fakes import FakeProfileRepository

AGORA = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
NOVEMBRO = date(2026, 11, 19)

CHAVES_COTACAO = {
    "ativo",
    "ultimo",
    "compra",
    "venda",
    "fechamento_anterior",
    "variacao_pct",
    "negocios",
    "volume",
    "hora",
    "fonte",
    "motivo",
}
CHAVES_SERIE = {
    "ticker",
    "tipo",
    "strike",
    "estilo",
    "compra",
    "venda",
    "ultimo",
    "negocios",
    "volume",
    "iv",
    "delta",
}


def _cotacao(ultimo: float = 30.6) -> UnderlyingQuote:
    return UnderlyingQuote(
        symbol="PETR4",
        last=ultimo,
        bid=30.59,
        ask=30.61,
        previous_close=30.0,
        trades=1500,
        volume=4.5e7,
        timestamp=AGORA,
        source=DataSource.AO_VIVO,
    )


def _cadeia(vencimentos: int) -> ChainView:
    linha = SeriesRow(
        symbol="PETRK300",
        option_type=OptionType.CALL,
        strike=30.0,
        exercise_style=ExerciseStyle.AMERICAN,
        bid=1.20,
        ask=None,
        last=1.21,
        trades=40,
        volume=4840.0,
        implied_vol=None,
        delta=0.55,
    )
    return ChainView(
        symbol="PETR4",
        spot=30.6,
        source=DataSource.AO_VIVO,
        timestamp=AGORA,
        expiries=tuple(ExpiryBlock(NOVEMBRO, 16, (linha,)) for _ in range(vencimentos)),
        rejected=(RejectedSeries("PETRK999", "sem estilo de exercício no cadastro"),),
    )


@dataclass
class _MercadoFalso:
    """``MarketViewUseCase`` em memória; ``ultimo`` muda a cotação de PETR4 entre consultas."""

    ultimo: float = 30.6
    seguindo: list[tuple[tuple[str, ...], str | None]] = field(default_factory=list)
    cadeias: list[tuple[str, int]] = field(default_factory=list)

    def follow(self, watchlist: Sequence[str], chain_symbol: str | None) -> None:
        self.seguindo.append((tuple(watchlist), chain_symbol))

    def quotes(self, watchlist: Sequence[str]) -> tuple[WatchRow, ...]:
        return tuple(
            WatchRow(s, _cotacao(self.ultimo), None)
            if s == "PETR4"
            else WatchRow(s, None, "aguardando dados")
            for s in watchlist
        )

    def chain(self, symbol: str, expiries: int = DEFAULT_CHAIN_EXPIRIES) -> ChainView:
        self.cadeias.append((symbol, expiries))
        if symbol == "VALE3":
            raise UnderlyingUnavailableError("VALE3: aguardando dados do Tryd")
        if symbol != "PETR4":
            raise UnknownSymbolError(f"subjacente desconhecido: {symbol!r}")
        return _cadeia(expiries)

    def status(self) -> MarketStatus:
        return MarketStatus(
            source=DataSource.AO_VIVO,
            cadastro=CadastroFreshness(date(2026, 10, 23), 3, False),
            cadastro_reason=None,
            cotahist_range=(date(2026, 1, 2), date(2026, 10, 23)),
        )


def _cliente(
    mercado: _MercadoFalso, *, com_perfil: bool = True, intervalo: float = 0.05
) -> TestClient:
    perfis = ProfileService(FakeProfileRepository(), FixedClock(AGORA), "PC-TESTE")
    if com_perfil:
        perfis.create("Hugo", "/pastas/hugo")
        perfis.open("Hugo")
    app = create_app([router_mercado(mercado, perfis, interval_s=intervalo)])
    return TestClient(app)


# --- REST ----------------------------------------------------------------------------------------


def test_status_traz_a_fonte_o_cadastro_e_a_faixa_dos_cotahist() -> None:
    assert _cliente(_MercadoFalso()).get("/api/mercado/status").json() == {
        "fonte": "ao_vivo",
        "cadastro": {"data": "2026-10-23", "dias_uteis": 3, "velho": False},
        "cadastro_motivo": None,
        "cotahist": {"de": "2026-01-02", "ate": "2026-10-23"},
    }


def test_cotacoes_sem_perfil_aberto_e_404() -> None:
    resposta = _cliente(_MercadoFalso(), com_perfil=False).get("/api/mercado/cotacoes")
    assert resposta.status_code == 404
    assert resposta.json()["erro"] == "NoActiveProfileError"


def test_cotacoes_do_perfil_com_numeros_crus_fonte_e_motivo() -> None:
    linhas = _cliente(_MercadoFalso()).get("/api/mercado/cotacoes").json()
    assert [linha["ativo"] for linha in linhas] == ["PETR4", "VALE3"]  # a lista padrão do perfil
    assert all(set(linha) == CHAVES_COTACAO for linha in linhas)
    petr4, vale3 = linhas
    assert (petr4["ultimo"], petr4["compra"], petr4["venda"]) == (30.6, 30.59, 30.61)
    assert petr4["variacao_pct"] == pytest.approx(0.02)  # decimal, nunca pontos percentuais
    assert (petr4["fonte"], petr4["motivo"], petr4["hora"]) == (
        "ao_vivo",
        None,
        AGORA.isoformat(),
    )
    assert (vale3["ultimo"], vale3["fonte"], vale3["motivo"]) == (None, None, "aguardando dados")


def test_cadeia_com_vencimentos_series_e_rejeitadas() -> None:
    mercado = _MercadoFalso()
    corpo = _cliente(mercado).get("/api/mercado/cadeia/petr4?vencimentos=3").json()
    assert mercado.cadeias == [("PETR4", 3)]  # ticker normalizado
    assert (corpo["ativo"], corpo["spot"], corpo["fonte"]) == ("PETR4", 30.6, "ao_vivo")
    assert len(corpo["vencimentos"]) == 3
    vencimento = corpo["vencimentos"][0]
    assert (vencimento["data"], vencimento["dias_uteis"]) == ("2026-11-19", 16)
    (serie,) = vencimento["series"]
    assert set(serie) == CHAVES_SERIE
    assert (serie["tipo"], serie["estilo"], serie["venda"], serie["iv"]) == (
        "call",
        "american",
        None,
        None,
    )
    assert corpo["rejeitadas"] == [
        {"ticker": "PETRK999", "motivo": "sem estilo de exercício no cadastro"}
    ]


def test_cadeia_de_ativo_desconhecido_e_404_e_indisponivel_e_422() -> None:
    cliente = _cliente(_MercadoFalso())
    assert cliente.get("/api/mercado/cadeia/PETR44").status_code == 404
    indisponivel = cliente.get("/api/mercado/cadeia/VALE3")
    assert indisponivel.status_code == 422
    assert indisponivel.json()["mensagem"] == "VALE3: aguardando dados do Tryd"


def test_cadeia_com_vencimentos_fora_da_faixa_e_requisicao_invalida() -> None:
    resposta = _cliente(_MercadoFalso()).get("/api/mercado/cadeia/PETR4?vencimentos=0")
    assert (resposta.status_code, resposta.json()["erro"]) == (422, "RequisicaoInvalida")


# --- WebSocket -----------------------------------------------------------------------------------


def test_ao_conectar_manda_status_e_depois_cotacoes_e_assina_a_lista() -> None:
    mercado = _MercadoFalso()
    with _cliente(mercado).websocket_connect("/api/ao-vivo") as ws:
        status = ws.receive_json()
        cotacoes = ws.receive_json()
    assert status["tipo"] == "status" and status["fonte"] == "ao_vivo"
    assert cotacoes["tipo"] == "cotacoes" and cotacoes["motivo"] is None
    assert [linha["ativo"] for linha in cotacoes["dados"]] == ["PETR4", "VALE3"]
    assert mercado.seguindo[0] == (("PETR4", "VALE3"), None)


def test_pedido_de_cadeia_manda_a_cadeia_e_assina_o_ativo() -> None:
    mercado = _MercadoFalso()
    with _cliente(mercado).websocket_connect("/api/ao-vivo") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"tipo": "cadeia", "ativo": "PETR4", "vencimentos": 2})
        cadeia = ws.receive_json()
        ws.send_json({"tipo": "cadeia", "ativo": None})
        ws.send_json({"tipo": "cadeia", "ativo": "PETR4"})
        reaberta = ws.receive_json()
    assert cadeia["tipo"] == "cadeia" and cadeia["dados"]["ativo"] == "PETR4"
    assert len(cadeia["dados"]["vencimentos"]) == 2
    assert reaberta["tipo"] == "cadeia"  # reaberta sai inteira, mesmo sem mudança
    assert (("PETR4", "VALE3"), "PETR4") in mercado.seguindo
    assert (("PETR4", "VALE3"), None) in mercado.seguindo[1:]


def test_so_reenvia_o_que_mudou() -> None:
    mercado = _MercadoFalso()
    with _cliente(mercado, intervalo=0.02).websocket_connect("/api/ao-vivo") as ws:
        ws.receive_json()
        ws.receive_json()
        mercado.ultimo = 30.75  # negócio novo: só as cotações mudam
        mudou = ws.receive_json()
    assert mudou["tipo"] == "cotacoes"
    assert mudou["dados"][0]["ultimo"] == 30.75


def test_cadeia_que_nao_sai_manda_o_motivo_no_lugar() -> None:
    with _cliente(_MercadoFalso()).websocket_connect("/api/ao-vivo") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_json({"tipo": "cadeia", "ativo": "VALE3"})
        erro = ws.receive_json()
    assert erro == {
        "tipo": "cadeia",
        "ativo": "VALE3",
        "erro": "UnderlyingUnavailableError",
        "mensagem": "VALE3: aguardando dados do Tryd",
    }


@pytest.mark.parametrize(
    "mensagem",
    [
        '{"tipo": "cadeia", "ativo": "PETR4", "vencimentos": 0}',
        '{"tipo": "outro", "ativo": null}',
        "{",
    ],
)
def test_mensagem_invalida_do_cliente_vira_erro_e_a_conexao_segue(mensagem: str) -> None:
    with _cliente(_MercadoFalso()).websocket_connect("/api/ao-vivo") as ws:
        ws.receive_json()
        ws.receive_json()
        ws.send_text(mensagem)
        erro = ws.receive_json()
        ws.send_json({"tipo": "cadeia", "ativo": "PETR4"})
        cadeia = ws.receive_json()
    assert (erro["tipo"], erro["erro"]) == ("erro", "RequisicaoInvalida")
    assert cadeia["tipo"] == "cadeia"


def test_sem_perfil_aberto_as_cotacoes_vem_vazias_com_o_motivo() -> None:
    with _cliente(_MercadoFalso(), com_perfil=False).websocket_connect("/api/ao-vivo") as ws:
        ws.receive_json()
        cotacoes = ws.receive_json()
    assert cotacoes["dados"] == []
    assert "perfil" in cotacoes["motivo"]

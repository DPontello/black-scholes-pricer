"""``FallbackMarket`` — o ao vivo enquanto a ponte responde, o fim de dia quando ela cai."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.adapters.outbound.b3files.end_of_day import EndOfDayMarket
from options_engine.adapters.outbound.cotahist import CotahistOptionChainAdapter
from options_engine.adapters.outbound.fallback_market import FallbackMarket
from options_engine.adapters.outbound.tryd.board import LiveBoard
from options_engine.adapters.outbound.tryd.client import BridgeHealth, TrydBridgeClient
from options_engine.adapters.outbound.tryd.feed import TrydMarketFeed
from options_engine.application.ports.outbound import (
    LiveFeedPort,
    MarketPort,
    OptionChainPort,
    QuoteBoardPort,
)
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.errors import UnderlyingUnavailableError, UnknownSymbolError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_ponte.protocolo import Status, Valor
from tests.adapters._mercado import (
    CDI,
    FIXTURE,
    Montagem,
    alimentar,
    biblioteca,
    montar,
    relogio,
)
from tests.adapters.tryd._ponte_falsa import PonteFalsa, entregar, esperar, porta_sem_ninguem
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME, REFERENCE_SESSION

# Preço do quadro que não existe no fim de dia (o fechamento de PETR4 em 23/10 é 30,00).
_ULT_VIVO = 31.5


def _montar(tmp_path: Path, saude: BridgeHealth) -> tuple[FallbackMarket, Montagem]:
    # Cadastro cru da fixture: a cadeia de fim de dia é a do adapter COTAHIST.
    m = montar(tmp_path, lib=biblioteca(tmp_path / "mercado"), saude=saude)
    fim_de_dia = EndOfDayMarket(m.biblioteca, lambda: m.cdi[0])
    m.feed.watch(["PETR4", "VALE3"], ["PETR4", "VALE3"])
    alimentar(m.board, "PETR4", ULT=_ULT_VIVO, OCP=31.25, OVD=31.75)
    return FallbackMarket(m.feed, fim_de_dia), m


def _cotacao(mercado: FallbackMarket, simbolo: str) -> UnderlyingQuote:
    resultado = mercado.get_quotes([simbolo])[simbolo]
    assert isinstance(resultado, UnderlyingQuote), resultado
    return resultado


def test_satisfaz_os_ports_de_mercado(tmp_path: Path) -> None:
    mercado, _ = _montar(tmp_path, BridgeHealth.CONECTADA)
    for port in (QuoteBoardPort, LiveFeedPort, OptionChainPort, MarketPort):
        assert isinstance(mercado, port), port


def test_ponte_desconectada_cai_para_o_fim_de_dia_rotulado(tmp_path: Path) -> None:
    mercado, _ = _montar(tmp_path, BridgeHealth.DESCONECTADA)
    cotacao = _cotacao(mercado, "PETR4")
    assert cotacao.source is DataSource.FIM_DE_DIA
    assert cotacao.last == 30.0  # o fechamento de 23/10, não o que sobrou no quadro
    assert mercado.health() is DataSource.FIM_DE_DIA

    esperado = CotahistOptionChainAdapter(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
        risk_free_rate=RiskFreeRate(CDI, Compounding.BUSINESS_DAILY_252),
    )
    assert mercado.get_chain("PETR4") == esperado.get_chain("PETR4")


@pytest.mark.parametrize(
    ("saude", "rotulo"),
    [(BridgeHealth.CONECTADA, DataSource.AO_VIVO), (BridgeHealth.ATRASADA, DataSource.ATRASADO)],
)
def test_ponte_viva_serve_o_ao_vivo_com_o_rotulo_da_saude(
    tmp_path: Path, saude: BridgeHealth, rotulo: DataSource
) -> None:
    mercado, _ = _montar(tmp_path, saude)
    cotacao = _cotacao(mercado, "PETR4")
    assert (cotacao.source, cotacao.last) == (rotulo, _ULT_VIVO)
    assert mercado.health() is rotulo
    assert mercado.get_chain("PETR4").underlying.spot == _ULT_VIVO


def test_a_troca_de_fonte_acompanha_a_saude_a_cada_consulta(tmp_path: Path) -> None:
    mercado, m = _montar(tmp_path, BridgeHealth.CONECTADA)
    assert _cotacao(mercado, "PETR4").source is DataSource.AO_VIVO
    m.cliente.saude = BridgeHealth.DESCONECTADA
    assert _cotacao(mercado, "PETR4").source is DataSource.FIM_DE_DIA
    m.cliente.saude = BridgeHealth.ATRASADA
    assert _cotacao(mercado, "PETR4").source is DataSource.ATRASADO


@pytest.mark.parametrize("saude", [BridgeHealth.CONECTADA, BridgeHealth.DESCONECTADA])
def test_ticker_digitado_errado_vira_motivo_nas_duas_fontes(
    tmp_path: Path, saude: BridgeHealth
) -> None:
    mercado, _ = _montar(tmp_path, saude)
    assert mercado.get_quotes(["PETR44"])["PETR44"] == "ativo desconhecido"
    with pytest.raises(UnknownSymbolError):
        mercado.get_chain("PETR44")


def test_ao_vivo_sem_dado_do_ativo_nao_cai_para_o_fim_de_dia_por_conta_propria(
    tmp_path: Path,
) -> None:
    mercado, _ = _montar(tmp_path, BridgeHealth.CONECTADA)
    # VALE3 foi assinada, mas o Tryd ainda não entregou nada: o painel espera, não mistura fontes.
    assert mercado.get_quotes(["VALE3"])["VALE3"] == "aguardando dados"
    with pytest.raises(UnderlyingUnavailableError, match="aguardando dados"):
        mercado.get_chain("VALE3")


def test_watch_vai_sempre_para_a_fonte_ao_vivo_mesmo_desconectada(tmp_path: Path) -> None:
    mercado, m = _montar(tmp_path, BridgeHealth.DESCONECTADA)
    antes = len(m.cliente.assinaturas)
    mercado.watch(["VALE3"], [])
    assert len(m.cliente.assinaturas) == antes + 1
    assert {t for t, _ in m.cliente.topicos} == {"VALE3"}


def test_sem_arquivos_da_b3_e_ponte_desconectada_o_motivo_chega_por_simbolo(
    tmp_path: Path,
) -> None:
    lib = biblioteca(tmp_path / "vazia", com_cotahist=False, com_cadastro=False)
    m = montar(tmp_path, lib=lib, saude=BridgeHealth.DESCONECTADA)
    mercado = FallbackMarket(m.feed, EndOfDayMarket(lib, lambda: CDI))
    assert mercado.get_quotes(["PETR4"]) == {"PETR4": "sem Cadastro de Instrumentos importado"}
    with pytest.raises(UnderlyingUnavailableError, match="sem Cadastro de Instrumentos"):
        mercado.get_chain("PETR4")


# --- com o cliente REAL da ponte (sem Tryd: ponte falsa em TCP local ou nenhuma) --------------


class _Real:
    """Mercado montado sobre um ``TrydBridgeClient`` de verdade; encerra tudo no fim do teste."""

    def __init__(self, raiz: Path) -> None:
        self._raiz = raiz
        self._clientes: list[TrydBridgeClient] = []
        self._pontes: list[PonteFalsa] = []
        self.tempo = [0.0]

    def ponte(self) -> PonteFalsa:
        ponte = PonteFalsa()
        self._pontes.append(ponte)
        return ponte

    def montar(self, porta: int) -> tuple[FallbackMarket, TrydBridgeClient, LiveBoard]:
        """Cliente real na ``porta`` (relógio em ``tempo``), com a fixture crua na biblioteca."""
        lib = biblioteca(self._raiz / "mercado")
        board = LiveBoard()
        cliente = TrydBridgeClient(
            board, "127.0.0.1", porta, lambda: self.tempo[0], reconnect_interval_s=0.05
        )
        self._clientes.append(cliente)
        feed = TrydMarketFeed(
            cliente,
            board,
            lib,
            StaticHolidayCalendar.from_packaged_data(),
            relogio(),
            lambda: CDI,
        )
        return FallbackMarket(feed, EndOfDayMarket(lib, lambda: CDI)), cliente, board

    def encerrar(self) -> None:
        for cliente in self._clientes:
            cliente.stop()
        for ponte in self._pontes:
            ponte.fechar()


@pytest.fixture
def real(tmp_path: Path) -> Iterator[_Real]:
    ambiente = _Real(tmp_path)
    yield ambiente
    ambiente.encerrar()


def _cadeia_do_adapter(simbolo: str) -> OptionChain:
    return CotahistOptionChainAdapter(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
        risk_free_rate=RiskFreeRate(CDI, Compounding.BUSINESS_DAILY_252),
    ).get_chain(simbolo)


def test_ponte_que_nunca_sobe_serve_o_fim_de_dia_rotulado(real: _Real) -> None:
    mercado, cliente, _ = real.montar(porta_sem_ninguem())  # ninguém escuta nessa porta
    mercado.watch(["PETR4"], ["PETR4"])
    cliente.start()
    assert mercado.health() is DataSource.FIM_DE_DIA
    cotacao = _cotacao(mercado, "PETR4")
    assert (cotacao.source, cotacao.last) == (DataSource.FIM_DE_DIA, 30.0)
    assert mercado.get_chain("PETR4") == _cadeia_do_adapter("PETR4")


def test_ponte_de_pe_com_o_tryd_fechado_recua_para_o_fim_de_dia_apos_30_s(real: _Real) -> None:
    ponte = real.ponte()
    ponte.valores = {("PETR4", "ULT"): Valor("PETR4", "ULT", "float", _ULT_VIVO, "2026-10-28")}
    mercado, cliente, board = real.montar(ponte.porta)
    mercado.watch(["PETR4"], [])
    cliente.start()
    esperar(lambda: ponte.conexoes() == 1)
    ponte.enviar(Status("conectado", None, 1))
    # A cotação do fim de dia também é UnderlyingQuote: esperar pela FONTE, senão o teste
    # segue antes de o Status chegar e lê o fim de dia (corrida que aparece sob carga).
    esperar(
        lambda: (
            getattr(mercado.get_quotes(["PETR4"])["PETR4"], "source", None) is DataSource.AO_VIVO
        )
    )
    ao_vivo = _cotacao(mercado, "PETR4")
    assert (ao_vivo.source, ao_vivo.last) == (DataSource.AO_VIVO, _ULT_VIVO)

    # O Tryd fecha; a ponte segue de pé e repete "perdido" de tempos em tempos.
    perdido = Status("perdido", "Heartbeat do servidor RTD falhou", 1)
    entregar(ponte, board, real.tempo, 100.0, perdido)
    assert mercado.health() is DataSource.ATRASADO
    for instante in (110.0, 120.0, 129.0):
        entregar(ponte, board, real.tempo, instante, perdido)
        atrasada = _cotacao(mercado, "PETR4")
        assert (atrasada.source, atrasada.last) == (DataSource.ATRASADO, _ULT_VIVO)
    real.tempo[0] = 129.9
    assert mercado.health() is DataSource.ATRASADO

    real.tempo[0] = 130.1  # 30,1 s sem o Tryd, com a ponte ainda falando (última mensagem: 129)
    assert mercado.health() is DataSource.FIM_DE_DIA
    recuo = _cotacao(mercado, "PETR4")
    assert (recuo.source, recuo.last) == (DataSource.FIM_DE_DIA, 30.0)  # não o 31,5 do quadro
    assert mercado.get_chain("PETR4") == _cadeia_do_adapter("PETR4")
    entregar(ponte, board, real.tempo, 131.0, Status("conectado", None, 1))
    assert mercado.health() is DataSource.AO_VIVO  # o Tryd voltou: volta ao vivo


def test_tryd_conectado_sem_preco_nenhum_recua_para_o_fim_de_dia(tmp_path: Path) -> None:
    # Fora do pregão o Tryd conecta, mas manda ULT, OCP e OVD vazios.
    m = montar(tmp_path, lib=biblioteca(tmp_path / "mercado"), saude=BridgeHealth.CONECTADA)
    mercado = FallbackMarket(m.feed, EndOfDayMarket(m.biblioteca, lambda: m.cdi[0]))
    mercado.watch(["PETR4", "VALE3"], ["PETR4"])
    alimentar(m.board, "PETR4", ULT="", OCP="", OVD="", VOL=1.2e9)
    assert mercado.health() is DataSource.AO_VIVO  # VALE3 ainda não carregou
    alimentar(m.board, "VALE3", ULT="", OCP="", OVD="")
    assert mercado.health() is DataSource.FIM_DE_DIA
    assert _cotacao(mercado, "PETR4").source is DataSource.FIM_DE_DIA
    assert mercado.get_chain("PETR4").underlying.spot == 30.0
    alimentar(m.board, "VALE3", OVD=61.2)
    assert mercado.health() is DataSource.AO_VIVO

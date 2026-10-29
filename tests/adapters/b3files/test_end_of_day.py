"""``EndOfDayMarket`` — cotações e cadeia do último pregão da biblioteca, sempre `fim_de_dia`."""

from datetime import date, datetime
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.b3files.end_of_day import EndOfDayMarket
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.cotahist import CotahistOptionChainAdapter
from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_SPOT,
    CotahistRecord,
    parse_cotahist,
)
from options_engine.application.ports.outbound import (
    LiveFeedPort,
    MarketPort,
    OptionChainPort,
    QuoteBoardPort,
)
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.errors import UnderlyingUnavailableError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from tests.adapters._mercado import FIXTURE, biblioteca, relogio
from tests.adapters.cotahist._layout import arquivo, registro
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME, REFERENCE_SESSION

_SEM_CADASTRO = "sem Cadastro de Instrumentos importado"
_SEM_COTAHIST = "sem COTAHIST importado"
_CDI = 0.15
_FIM_DO_PREGAO = datetime(2026, 10, 23, 18, 0, tzinfo=B3_UTC_OFFSET)


def _mercado(tmp_path: Path, cdi: float = _CDI) -> EndOfDayMarket:
    return EndOfDayMarket(biblioteca(tmp_path / "mercado"), lambda: cdi)


def _a_vista(simbolo: str) -> list[CotahistRecord]:
    """Registros à vista do ticker na fixture, do pregão mais antigo ao mais novo."""
    registros = parse_cotahist(FIXTURE / COTAHIST_NAME)
    return sorted(
        (r for r in registros if r.symbol == simbolo and r.market == MARKET_SPOT),
        key=lambda r: r.session,
    )


def _cotacao(mercado: EndOfDayMarket, simbolo: str) -> UnderlyingQuote:
    resultado = mercado.get_quotes([simbolo])[simbolo]
    assert isinstance(resultado, UnderlyingQuote), resultado
    return resultado


def _cotahist_de_um_pregao(pregao: date, *linhas: str) -> bytes:
    return arquivo(list(linhas), geracao=pregao, ano=pregao.year).encode("cp1252")


def test_satisfaz_os_ports_de_mercado(tmp_path: Path) -> None:
    mercado = _mercado(tmp_path)
    for port in (QuoteBoardPort, LiveFeedPort, OptionChainPort, MarketPort):
        assert isinstance(mercado, port), port


def test_cotacao_de_fim_de_dia_vem_rotulada_e_com_o_fechamento_anterior(tmp_path: Path) -> None:
    anterior, ultimo = _a_vista("PETR4")[-2:]
    cotacao = _cotacao(_mercado(tmp_path), "PETR4")
    assert cotacao.source is DataSource.FIM_DE_DIA
    assert cotacao.symbol == "PETR4"
    assert (cotacao.last, cotacao.bid, cotacao.ask) == (
        ultimo.last,
        ultimo.best_bid,
        ultimo.best_ask,
    )
    assert cotacao.previous_close == anterior.last
    assert (cotacao.trades, cotacao.volume) == (ultimo.trades, ultimo.volume)
    assert cotacao.timestamp == _FIM_DO_PREGAO
    assert ultimo.session == REFERENCE_SESSION


def test_ativo_sem_ofertas_no_pregao_tem_os_lados_ausentes_e_nunca_zero(tmp_path: Path) -> None:
    cotacao = _cotacao(_mercado(tmp_path), "VALE3")
    assert cotacao.bid is None
    assert cotacao.ask is None
    assert cotacao.last == _a_vista("VALE3")[-1].last


def test_historico_curto_nao_tira_a_cotacao_so_a_cadeia(tmp_path: Path) -> None:
    mercado = _mercado(tmp_path)
    cotacao = _cotacao(mercado, "ITUB4")
    assert cotacao.previous_close == _a_vista("ITUB4")[-2].last
    with pytest.raises(UnderlyingUnavailableError, match="histórico insuficiente"):
        mercado.get_chain("ITUB4")


def test_ticker_digitado_errado_vira_motivo(tmp_path: Path) -> None:
    resultado = _mercado(tmp_path).get_quotes(["PETR44", "PETR4"])
    assert resultado["PETR44"] == "ativo desconhecido"
    assert isinstance(resultado["PETR4"], UnderlyingQuote)


def test_conhecido_sem_registro_no_pregao_vira_motivo_com_a_data(tmp_path: Path) -> None:
    motivo = _mercado(tmp_path).get_quotes(["BBAS3"])["BBAS3"]
    assert motivo == f"sem fechamento no pregão de {REFERENCE_SESSION.isoformat()}"


def test_a_cadeia_e_a_do_adapter_cotahist_do_mesmo_pregao(tmp_path: Path) -> None:
    esperado = CotahistOptionChainAdapter(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
        risk_free_rate=RiskFreeRate(_CDI, Compounding.BUSINESS_DAILY_252),
    )
    mercado = _mercado(tmp_path)
    for simbolo in ("PETR4", "VALE3"):
        assert mercado.get_chain(simbolo) == esperado.get_chain(simbolo)


def test_o_cdi_do_perfil_vale_na_hora_da_consulta(tmp_path: Path) -> None:
    cdi = [0.15]
    mercado = EndOfDayMarket(biblioteca(tmp_path / "mercado"), lambda: cdi[0])
    assert mercado.get_chain("PETR4").underlying.risk_free_rate.rate == 0.15
    cdi[0] = 0.10
    taxa = mercado.get_chain("PETR4").underlying.risk_free_rate
    assert (taxa.rate, taxa.compounding) == (0.10, Compounding.BUSINESS_DAILY_252)


def test_watch_nao_faz_nada_e_a_saude_e_sempre_fim_de_dia(tmp_path: Path) -> None:
    mercado = _mercado(tmp_path)
    assert mercado.health() is DataSource.FIM_DE_DIA
    mercado.watch(["PETR4"], ["PETR4"])
    assert mercado.health() is DataSource.FIM_DE_DIA


def test_o_cache_do_pregao_fica_na_raiz_da_biblioteca(tmp_path: Path) -> None:
    mercado = _mercado(tmp_path)
    mercado.get_quotes(["PETR4"])
    assert (tmp_path / "mercado" / "cache.sqlite").is_file()


@pytest.mark.parametrize("com_cotahist", [False, True])
def test_sem_cadastro_o_motivo_e_por_simbolo_e_a_cadeia_e_indisponivel(
    tmp_path: Path, com_cotahist: bool
) -> None:
    lib = biblioteca(tmp_path / "mercado", com_cotahist=com_cotahist, com_cadastro=False)
    mercado = EndOfDayMarket(lib, lambda: _CDI)
    assert mercado.get_quotes(["PETR4", "XXXX99"]) == {
        "PETR4": _SEM_CADASTRO,
        "XXXX99": _SEM_CADASTRO,
    }
    with pytest.raises(UnderlyingUnavailableError, match=_SEM_CADASTRO):
        mercado.get_chain("PETR4")


def test_sem_cotahist_o_fim_de_dia_diz_por_que_e_ainda_reconhece_o_ticker(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado", com_cotahist=False)
    mercado = EndOfDayMarket(lib, lambda: _CDI)
    assert mercado.get_quotes(["PETR4", "XXXX99"]) == {
        "PETR4": _SEM_COTAHIST,
        "XXXX99": "ativo desconhecido",
    }
    with pytest.raises(UnderlyingUnavailableError, match=_SEM_COTAHIST):
        mercado.get_chain("PETR4")


def test_arquivo_ilegivel_na_biblioteca_vira_motivo_e_nao_excecao(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado")
    cotahist = next(f for f in lib.files() if f.name == COTAHIST_NAME)
    cotahist.path.write_bytes(b"lixo que nao e COTAHIST\n")  # estraga depois da importação
    mercado = EndOfDayMarket(lib, lambda: _CDI)
    motivo = mercado.get_quotes(["PETR4"])["PETR4"]
    assert isinstance(motivo, str)
    assert "ilegíveis" in motivo
    with pytest.raises(UnderlyingUnavailableError, match="ilegíveis"):
        mercado.get_chain("PETR4")


def test_recarrega_quando_a_biblioteca_muda(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado")
    mercado = EndOfDayMarket(lib, lambda: _CDI)
    assert _cotacao(mercado, "PETR4").last == _a_vista("PETR4")[-1].last
    assert mercado.get_chain("PETR4").quotes  # monta (e guarda) o adapter do pregão de 23/10
    segunda = date(2026, 10, 26)
    lib.import_file(
        "COTAHIST_D26102026.TXT",
        _cotahist_de_um_pregao(
            segunda,
            registro(
                pregao=segunda,
                simbolo="PETR4",
                mercado=10,
                nome="PETR4",
                especificacao="PN      N2",
                ultimo=31.25,
                oferta_compra=31.0,
                oferta_venda=31.5,
                negocios=7,
                volume=1000.0,
            ),
        ),
    )
    nova = _cotacao(mercado, "PETR4")
    assert (nova.last, nova.bid, nova.ask) == (31.25, 31.0, 31.5)
    assert nova.previous_close == _a_vista("PETR4")[-1].last  # o pregão de 23/10 virou o anterior
    assert nova.timestamp == datetime(2026, 10, 26, 18, 0, tzinfo=B3_UTC_OFFSET)
    assert mercado.get_quotes(["VALE3"])["VALE3"] == "sem fechamento no pregão de 2026-10-26"
    chain = mercado.get_chain("PETR4")  # a cadeia também vem do pregão novo, sem séries nele
    assert (chain.underlying.spot, chain.underlying.timestamp) == (31.25, nova.timestamp)
    assert chain.quotes == ()


def test_cadastro_novo_na_biblioteca_passa_a_valer(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado", com_cadastro=False)
    mercado = EndOfDayMarket(lib, lambda: _CDI)
    assert mercado.get_quotes(["PETR4"])["PETR4"] == _SEM_CADASTRO
    lib.import_file(INSTRUMENTS_NAME, (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    assert isinstance(mercado.get_quotes(["PETR4"])["PETR4"], UnderlyingQuote)


def _spot(simbolo: str, ultimo: float, compra: float = 0.0, venda: float = 0.0) -> str:
    return registro(
        pregao=date(2026, 10, 23),
        simbolo=simbolo,
        mercado=10,
        nome=simbolo,
        especificacao="ON",
        ultimo=ultimo,
        oferta_compra=compra,
        oferta_venda=venda,
        negocios=1,
    )


def _mercado_com_pregao_curioso(tmp_path: Path) -> EndOfDayMarket:
    """Um pregão só: book cruzado, fechamento zero e ticker com registros divergentes."""
    cotahist = _cotahist_de_um_pregao(
        date(2026, 10, 23),
        _spot("PETR4", 30.5, compra=31.0, venda=30.0),
        _spot("VALE3", 0.0),
        _spot("ITUB4", 20.0),
        _spot("ITUB4", 21.0),
    )
    lib = B3FileLibrary(tmp_path / "mercado", relogio())
    lib.import_file("COTAHIST_D23102026.TXT", cotahist)
    lib.import_file(INSTRUMENTS_NAME, (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    return EndOfDayMarket(lib, lambda: _CDI)


def test_book_cruzado_na_fonte_deixa_os_lados_ausentes_mas_mantem_o_ultimo(
    tmp_path: Path,
) -> None:
    cotacao = _cotacao(_mercado_com_pregao_curioso(tmp_path), "PETR4")
    assert (cotacao.last, cotacao.bid, cotacao.ask) == (30.5, None, None)
    assert cotacao.previous_close is None  # um pregão só: não há fechamento anterior


def test_fechamento_zero_e_registros_divergentes_viram_motivo(tmp_path: Path) -> None:
    resultado = _mercado_com_pregao_curioso(tmp_path).get_quotes(["VALE3", "ITUB4"])
    assert resultado["VALE3"] == "sem fechamento no pregão de 2026-10-23"
    assert resultado["ITUB4"] == "registros divergentes do ativo no pregão de 2026-10-23"

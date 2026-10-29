"""``TrydMarketFeed`` — assinatura, cotações e cadeia ao vivo sobre quadro e cliente falsos."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.cotahist import CotahistOptionChainAdapter
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo, load_instruments
from options_engine.adapters.outbound.tryd.client import BridgeHealth
from options_engine.adapters.outbound.tryd.settings import (
    CAMPOS_ATIVO,
    CAMPOS_OPCAO,
)
from options_engine.application.ports.outbound import (
    LiveFeedPort,
    MarketPort,
    OptionChainPort,
    QuoteBoardPort,
)
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import UnderlyingUnavailableError, UnknownSymbolError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_ponte.protocolo import Valor
from tests.adapters._mercado import (
    AGORA,
    CDI,
    FIXTURE,
    SERIES_DE_PETR3,
    Montagem,
    alimentar,
    biblioteca,
    cadastro_com_objetos,
    cadastro_sem_objetos,
    montar,
)
from tests.data.cotahist.build_fixture import (
    COTAHIST_NAME,
    DEZEMBRO,
    INSTRUMENTS_NAME,
    NOVEMBRO,
    REFERENCE_SESSION,
)

_SEM_ARQUIVOS = "sem arquivos da B3 importados"
_INICIAL = "2026-10-28T12:00:00-03:00"
Topico = tuple[str, str]


@pytest.fixture(scope="module")
def instrumentos(tmp_path_factory: pytest.TempPathFactory) -> dict[str, InstrumentInfo]:
    caminho = tmp_path_factory.mktemp("cadastro") / INSTRUMENTS_NAME
    caminho.write_bytes(cadastro_com_objetos())
    return load_instruments(caminho)


def _series(topicos: frozenset[Topico], *ativos: str) -> set[str]:
    return {ticker for ticker, _ in topicos} - set(ativos)


def _campos_de(topicos: frozenset[Topico], ticker: str) -> set[str]:
    return {campo for t, campo in topicos if t == ticker}


def _assinar_com_spot(m: Montagem, ticker: str, spot: float) -> frozenset[Topico]:
    """Assina, entrega o ``ULT`` e assina de novo: a faixa de strikes passa a seguir o spot vivo."""
    m.feed.watch([ticker], [])
    alimentar(m.board, ticker, ULT=spot)
    m.feed.watch([ticker], [ticker])
    return m.cliente.topicos


def _distancia(instrumentos: dict[str, InstrumentInfo], serie: str, spot: float) -> float:
    strike = instrumentos[serie].strike
    assert strike is not None
    return abs(strike - spot) / spot


# --- forma ------------------------------------------------------------------------------------


def test_satisfaz_os_ports_de_mercado(tmp_path: Path) -> None:
    feed = montar(tmp_path).feed
    for port in (QuoteBoardPort, LiveFeedPort, OptionChainPort, MarketPort):
        assert isinstance(feed, port), port


@pytest.mark.parametrize(
    ("saude", "rotulo"),
    [
        (BridgeHealth.CONECTADA, DataSource.AO_VIVO),
        (BridgeHealth.ATRASADA, DataSource.ATRASADO),
        (BridgeHealth.DESCONECTADA, DataSource.FIM_DE_DIA),
    ],
)
def test_saude_da_ponte_vira_o_rotulo_da_fonte(
    tmp_path: Path, saude: BridgeHealth, rotulo: DataSource
) -> None:
    assert montar(tmp_path, saude=saude).feed.health() is rotulo


# --- watch ------------------------------------------------------------------------------------


def test_watch_assina_dois_vencimentos_na_faixa_e_respeita_o_limite(
    tmp_path: Path, instrumentos: dict[str, InstrumentInfo]
) -> None:
    spot = 27.0
    m = montar(tmp_path)
    topicos = _assinar_com_spot(m, "PETR4", spot)

    assert {c for c in _campos_de(topicos, "PETR4")} == set(CAMPOS_ATIVO)
    esperadas = {
        simbolo
        for simbolo, info in instrumentos.items()
        if simbolo.startswith("PETR")
        and simbolo not in SERIES_DE_PETR3
        and info.option_type is not None
        and info.expiry in (NOVEMBRO, DEZEMBRO)
        and info.strike is not None
        and 0.8 * spot <= info.strike <= 1.2 * spot
    }
    assert len(esperadas) > 20
    assert _series(topicos, "PETR4") == esperadas
    assert {t for t in topicos if t[0] != "PETR4"} == {
        (s, c) for s in esperadas for c in CAMPOS_OPCAO
    }
    # Fora do pacote: janeiro (3º vencimento), a série vencida em 16/10 e as de PETR3.
    assert not {"PETRA300", "PETRJ300", *SERIES_DE_PETR3} & _series(topicos, "PETR4")

    # Com o limite reduzido, o ativo fica e saem os strikes mais longe do spot.
    pequeno = montar(tmp_path / "pequeno", topic_limit=len(CAMPOS_ATIVO) + 5 * len(CAMPOS_OPCAO))
    reduzidos = _assinar_com_spot(pequeno, "PETR4", spot)
    escolhidas = _series(reduzidos, "PETR4")
    assert {c for c in _campos_de(reduzidos, "PETR4")} == set(CAMPOS_ATIVO)
    assert len(escolhidas) == 5
    assert escolhidas <= esperadas
    mais_longe = max(_distancia(instrumentos, s, spot) for s in escolhidas)
    assert all(_distancia(instrumentos, s, spot) >= mais_longe for s in esperadas - escolhidas)


def test_watch_sem_spot_ao_vivo_usa_o_ultimo_fechamento_da_biblioteca(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], ["PETR4"])  # nada chegou do Tryd ainda; o fechamento de 23/10 é 30,00
    assert "PETRK330" in _series(m.cliente.topicos, "PETR4")  # strike 33: dentro de 24 a 36
    _assinar_com_spot(m, "PETR4", 27.0)  # o spot vivo manda: faixa de 21,6 a 32,4
    assert "PETRK330" not in _series(m.cliente.topicos, "PETR4")
    assert "PETRK320" in _series(m.cliente.topicos, "PETR4")


def test_watch_sem_nenhum_spot_assina_todas_as_series_dos_vencimentos(tmp_path: Path) -> None:
    extra = cadastro_com_objetos().decode("utf-8-sig").rstrip("\r\n") + (
        "\r\nNEWC3;NEWC;;;;;"
        f"\r\nNEWCK100;NEWC;{NOVEMBRO.isoformat()};10.00;EURO;CALL;NEWC3"
        f"\r\nNEWCK900;NEWC;{NOVEMBRO.isoformat()};90.00;EURO;CALL;NEWC3\r\n"
    )
    m = montar(tmp_path, cadastro=extra.encode("utf-8-sig"))
    m.feed.watch(["NEWC3"], ["NEWC3"])  # NEWC3 só existe no cadastro: nenhum spot, nem o vivo
    assert _series(m.cliente.topicos, "NEWC3") == {"NEWCK100", "NEWCK900"}
    alimentar(m.board, "NEWC3", ULT=10.5)
    m.feed.watch(["NEWC3"], ["NEWC3"])
    assert _series(m.cliente.topicos, "NEWC3") == {"NEWCK100"}


def test_watch_nao_assina_serie_cujo_ativo_objeto_e_ambiguo(tmp_path: Path) -> None:
    # Cadastro sintético cru: sem ativo-objeto, e PETR3 e PETR4 dividem a raiz PETR. Só a série
    # com UndrlygTckrSymb1 (PETRK305) é de PETR4 sem dúvida; as outras não se atribuem a ninguém.
    m = montar(tmp_path, lib=biblioteca(tmp_path / "cru"))
    m.feed.watch(["PETR4"], ["PETR4"])
    assert _series(m.cliente.topicos, "PETR4") == {"PETRK305"}
    m.feed.watch(["VALE3"], ["VALE3"])  # raiz sem concorrência: o cadastro cru basta
    assert len(_series(m.cliente.topicos, "VALE3")) == 10


def test_serie_sem_ativo_objeto_e_so_do_unico_ativo_da_raiz_nos_cotahist(tmp_path: Path) -> None:
    # VALE5 só existe no cadastro: as séries de VALE sem ativo-objeto são de VALE3.
    linhas = (FIXTURE / INSTRUMENTS_NAME).read_bytes().decode("utf-8-sig").splitlines()
    linhas.insert(linhas.index("VALE3;VALE;;;;;") + 1, "VALE5;VALE;;;;;")
    com_vale5 = "\n".join(linhas) + "\n"
    m = montar(tmp_path, lib=biblioteca(tmp_path / "cru", cadastro=com_vale5.encode("utf-8-sig")))
    m.feed.watch(["VALE5"], ["VALE5"])
    assert _series(m.cliente.topicos, "VALE5") == set()
    m.feed.watch(["VALE3"], ["VALE3"])
    assert len(_series(m.cliente.topicos, "VALE3")) == 10


def test_watch_inclui_o_ativo_dos_simbolos_de_cadeia(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], ["VALE3"])
    assert _campos_de(m.cliente.topicos, "VALE3") == set(CAMPOS_ATIVO)
    assert _campos_de(m.cliente.topicos, "PETR4") == set(CAMPOS_ATIVO)


def test_watch_sem_cadeia_assina_so_os_ativos(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4", "VALE3"], [])
    assert m.cliente.topicos == {(t, c) for t in ("PETR4", "VALE3") for c in CAMPOS_ATIVO}


def test_watch_vazio_cancela_a_assinatura(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], ["PETR4"])
    m.feed.watch([], [])
    assert m.cliente.topicos == frozenset()


def test_watch_com_limite_menor_que_os_ativos_corta_nos_primeiros_ativos(tmp_path: Path) -> None:
    m = montar(tmp_path, topic_limit=len(CAMPOS_ATIVO) + 3)
    m.feed.watch(["PETR4", "VALE3"], ["PETR4"])
    assert m.cliente.topicos == {("PETR4", c) for c in CAMPOS_ATIVO}


def test_watch_sem_biblioteca_assina_so_os_ativos(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "vazia", com_cotahist=False, com_cadastro=False)
    m = montar(tmp_path, lib=lib)
    m.feed.watch(["PETR4"], ["PETR4"])
    assert m.cliente.topicos == {("PETR4", c) for c in CAMPOS_ATIVO}


def test_watch_repetido_com_a_mesma_lista_nao_perde_o_que_o_quadro_ja_tem(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    alimentar(m.board, "PETR4", ULT=30.0, OCP=29.5, OVD=30.5)
    m.feed.watch(["PETR4"], [])
    assert isinstance(m.feed.get_quotes(["PETR4"])["PETR4"], UnderlyingQuote)


# --- cotações ---------------------------------------------------------------------------------


def test_cotacao_ao_vivo_leva_o_rotulo_da_saude_da_ponte(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    alimentar(m.board, "PETR4", ULT=30.25, OCP=30.0, OVD=30.5, FEC=29.5, NEG=120, VOL=4000.5)
    cotacao = m.feed.get_quotes(["PETR4"])["PETR4"]
    assert isinstance(cotacao, UnderlyingQuote)
    assert cotacao.source is DataSource.AO_VIVO
    assert (cotacao.last, cotacao.bid, cotacao.ask, cotacao.previous_close) == (
        30.25,
        30.0,
        30.5,
        29.5,
    )
    assert (cotacao.trades, cotacao.volume) == (120, 4000.5)
    m.cliente.saude = BridgeHealth.ATRASADA
    atrasada = m.feed.get_quotes(["PETR4"])["PETR4"]
    assert isinstance(atrasada, UnderlyingQuote)
    assert atrasada.source is DataSource.ATRASADO


def test_ponte_desconectada_nao_entrega_o_que_sobrou_no_quadro(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    alimentar(m.board, "PETR4", ULT=30.25, OCP=30.0, OVD=30.5)
    m.cliente.saude = BridgeHealth.DESCONECTADA
    assert m.feed.get_quotes(["PETR4"]) == {"PETR4": "aguardando dados"}


def test_ticker_digitado_errado_vira_motivo(tmp_path: Path) -> None:
    m = montar(tmp_path)
    resultado = m.feed.get_quotes(["PETR44", "BBAS3", "PETR4"])
    assert resultado["PETR44"] == "ativo desconhecido"
    assert resultado["BBAS3"] == "aguardando dados"  # conhecido (cadastro e COTAHIST), sem carga
    assert resultado["PETR4"] == "aguardando dados"


def test_zero_inicial_do_rtd_nao_vira_cotacao(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    for campo in ("ULT", "OCP", "OVD"):
        m.board.apply(Valor("PETR4", campo, "float", 0.0, _INICIAL, True))
    assert m.feed.get_quotes(["PETR4"])["PETR4"] == "aguardando dados"


def test_lado_ausente_e_none_nunca_zero(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    alimentar(m.board, "PETR4", ULT=30.25, OCP=0.0, OVD=0.0, FEC=0.0)
    cotacao = m.feed.get_quotes(["PETR4"])["PETR4"]
    assert isinstance(cotacao, UnderlyingQuote)
    assert (cotacao.bid, cotacao.ask, cotacao.previous_close) == (None, None, None)
    assert cotacao.last == 30.25


def test_hora_do_tryd_vira_o_timestamp_e_sem_ela_vale_o_relogio_no_fuso_de_valoracao(
    tmp_path: Path,
) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4", "VALE3"], [])
    alimentar(m.board, "PETR4", ULT=30.25, HOR="11:59:30", DAT="28/10/2026")
    alimentar(m.board, "VALE3", ULT=60.5)
    resultado = m.feed.get_quotes(["PETR4", "VALE3"])
    petr4, vale3 = resultado["PETR4"], resultado["VALE3"]
    assert isinstance(petr4, UnderlyingQuote)
    assert isinstance(vale3, UnderlyingQuote)
    assert petr4.timestamp == datetime(2026, 10, 28, 11, 59, 30, tzinfo=B3_UTC_OFFSET)
    assert vale3.timestamp == AGORA
    assert vale3.timestamp.utcoffset() == timedelta(hours=-3)


def test_biblioteca_vazia_nao_permite_chamar_ninguem_de_desconhecido(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado", com_cotahist=False, com_cadastro=False)
    m = montar(tmp_path, lib=lib)
    m.feed.watch(["PETR4"], [])
    assert m.feed.get_quotes(["PETR44"]) == {"PETR44": "aguardando dados"}
    alimentar(m.board, "PETR4", ULT=30.25)
    assert isinstance(m.feed.get_quotes(["PETR4"])["PETR4"], UnderlyingQuote)
    # Importar os arquivos passa a distinguir o ticker errado.
    lib.import_file(COTAHIST_NAME, (FIXTURE / COTAHIST_NAME).read_bytes())
    lib.import_file(INSTRUMENTS_NAME, (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    assert m.feed.get_quotes(["PETR44"]) == {"PETR44": "ativo desconhecido"}


# --- cadeia -----------------------------------------------------------------------------------


def _montar_cadeia_ao_vivo(tmp_path: Path) -> Montagem:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], ["PETR4"])
    alimentar(m.board, "PETR4", ULT=30.0, OCP=29.5, OVD=30.5, FEC=29.5, NEG=900, VOL=9000.0)
    hora = {"HOR": "11:59:00", "DAT": "28/10/2026"}
    alimentar(m.board, "PETRK300", ULT=1.5, OCP=1.25, OVD=1.75, NEG=10, VOL=2500.0, **hora)
    alimentar(m.board, "PETRK280", ULT=2.5, OCP=2.25, OVD=0.0, NEG=4, VOL=300.0, **hora)
    alimentar(m.board, "PETRW300", ULT=0.0, OCP=0.0, OVD=0.0, NEG=0, VOL=0.0, **hora)
    alimentar(m.board, "PETRK285", ULT=1.0, OCP=1.0, OVD=0.5, **hora)  # book cruzado no Tryd
    return m


def test_cadeia_ao_vivo_usa_o_quadro_e_rejeita_serie_sem_estilo(tmp_path: Path) -> None:
    chain = _montar_cadeia_ao_vivo(tmp_path).feed.get_chain("PETR4")

    por_simbolo = {q.contract.symbol: q for q in chain.quotes}
    assert sorted(por_simbolo) == ["PETRK280", "PETRK300", "PETRW300"]  # PETRW270 nem chegou
    completa = por_simbolo["PETRK300"]
    assert (completa.bid, completa.ask, completa.last) == (1.25, 1.75, 1.5)
    assert (completa.trades, completa.volume) == (10, 2500.0)
    assert completa.timestamp == datetime(2026, 10, 28, 11, 59, tzinfo=B3_UTC_OFFSET)
    so_bid = por_simbolo["PETRK280"]
    assert (so_bid.bid, so_bid.ask, so_bid.last) == (2.25, None, 2.5)
    vazia = por_simbolo["PETRW300"]
    assert (vazia.bid, vazia.ask, vazia.last) == (None, None, None)

    motivos = {r.symbol: r.reason for r in chain.rejected_series}
    assert motivos["PETRK340"] == "sem estilo de exercício no cadastro"
    assert motivos["PETRK285"] == "book cruzado na fonte (Tryd)"
    assert set(motivos) == {"PETRK340", "PETRK285"}


def test_termos_da_serie_vem_do_cadastro(tmp_path: Path) -> None:
    chain = _montar_cadeia_ao_vivo(tmp_path).feed.get_chain("PETR4")
    termos = {q.contract.symbol: q.contract.terms for q in chain.quotes}
    assert (termos["PETRK300"].exercise_style, termos["PETRK280"].exercise_style) == (
        ExerciseStyle.EUROPEAN,
        ExerciseStyle.AMERICAN,
    )
    put = termos["PETRW300"]
    assert (put.underlying, put.option_type, put.strike, put.expiry) == (
        "PETR4",
        OptionType.PUT,
        30.0,
        NOVEMBRO,
    )


def test_cadeia_ordena_por_vencimento_tipo_strike_e_ticker(tmp_path: Path) -> None:
    chain = _montar_cadeia_ao_vivo(tmp_path).feed.get_chain("PETR4")
    assert [q.contract.symbol for q in chain.quotes] == ["PETRK280", "PETRK300", "PETRW300"]
    assert [r.symbol for r in chain.rejected_series] == ["PETRK285", "PETRK340"]


def test_snapshot_do_ativo_usa_ult_e_o_book_do_tryd(tmp_path: Path) -> None:
    chain = _montar_cadeia_ao_vivo(tmp_path).feed.get_chain("PETR4")
    snapshot = chain.underlying
    assert (snapshot.underlying_symbol, snapshot.spot) == ("PETR4", 30.0)
    assert (snapshot.bid, snapshot.mid, snapshot.ask) == (29.5, 30.0, 30.5)
    assert chain.underlying_book_available is True
    assert snapshot.timestamp == AGORA


@pytest.mark.parametrize("campos", [{"ULT": 30.0}, {"ULT": 30.0, "OCP": 29.5, "OVD": 0.0}])
def test_ativo_sem_os_dois_lados_usa_o_spot_nos_tres_e_marca_book_indisponivel(
    tmp_path: Path, campos: dict[str, float]
) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], ["PETR4"])
    alimentar(m.board, "PETR4", **campos)
    chain = m.feed.get_chain("PETR4")
    assert (chain.underlying.bid, chain.underlying.mid, chain.underlying.ask) == (30.0, 30.0, 30.0)
    assert chain.underlying.spot == 30.0
    assert chain.underlying_book_available is False


def test_vol_realizada_vem_dos_closes_do_cotahist_da_biblioteca(tmp_path: Path) -> None:
    esperado = CotahistOptionChainAdapter(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
        risk_free_rate=RiskFreeRate(CDI, Compounding.BUSINESS_DAILY_252),
    )
    chain = _montar_cadeia_ao_vivo(tmp_path).feed.get_chain("PETR4")
    assert chain.underlying.volatility == esperado.get_chain("PETR4").underlying.volatility


def test_vol_sem_historico_suficiente_vira_indisponivel_com_o_motivo(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["ITUB4"], ["ITUB4"])
    alimentar(m.board, "ITUB4", ULT=35.0, OCP=34.5, OVD=35.5)
    with pytest.raises(UnderlyingUnavailableError, match="histórico insuficiente"):
        m.feed.get_chain("ITUB4")


def test_taxa_e_o_cdi_do_perfil_na_hora_da_consulta(tmp_path: Path) -> None:
    m = _montar_cadeia_ao_vivo(tmp_path)
    assert m.feed.get_chain("PETR4").underlying.risk_free_rate == RiskFreeRate(
        0.15, Compounding.BUSINESS_DAILY_252
    )
    m.cdi[0] = 0.105
    assert m.feed.get_chain("PETR4").underlying.risk_free_rate == RiskFreeRate(
        0.105, Compounding.BUSINESS_DAILY_252
    )


def test_cadeia_sem_cotacao_do_ativo_e_indisponivel_e_nao_inventa_spot(tmp_path: Path) -> None:
    m = montar(tmp_path)
    with pytest.raises(UnderlyingUnavailableError, match="aguardando dados"):
        m.feed.get_chain("PETR4")
    m.feed.watch(["PETR4"], ["PETR4"])
    alimentar(m.board, "PETR4", ULT=0.0, OCP=29.5, OVD=30.5)  # só o book: sem spot (ULT é o spot)
    with pytest.raises(UnderlyingUnavailableError, match="sem último preço"):
        m.feed.get_chain("PETR4")


def test_cadeia_com_ponte_desconectada_e_indisponivel_e_nao_mostra_dado_parado(
    tmp_path: Path,
) -> None:
    m = _montar_cadeia_ao_vivo(tmp_path)
    m.cliente.saude = BridgeHealth.DESCONECTADA
    with pytest.raises(UnderlyingUnavailableError, match="desconectada"):
        m.feed.get_chain("PETR4")


def test_cadeia_de_ticker_fora_do_cadastro_e_dos_cotahist_e_desconhecida(tmp_path: Path) -> None:
    with pytest.raises(UnknownSymbolError):
        montar(tmp_path).feed.get_chain("XXXX99")


def test_cadeia_sem_arquivos_da_b3_e_indisponivel(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado", com_cotahist=False, com_cadastro=False)
    with pytest.raises(UnderlyingUnavailableError, match=_SEM_ARQUIVOS):
        montar(tmp_path, lib=lib).feed.get_chain("PETR4")


def test_serie_de_vinculo_ambiguo_sai_rejeitada_e_nao_cotada(tmp_path: Path) -> None:
    m = montar(tmp_path, lib=biblioteca(tmp_path / "cru"))
    m.feed.watch(["PETR4"], ["PETR4"])
    alimentar(m.board, "PETR4", ULT=30.0, OCP=29.5, OVD=30.5)
    alimentar(m.board, "PETRK312", ULT=1.0, OCP=0.9, OVD=1.1)  # é de PETR3, mas ninguém disse
    chain = m.feed.get_chain("PETR4")
    assert [q.contract.symbol for q in chain.quotes] == []
    motivos = {r.symbol: r.reason for r in chain.rejected_series}
    assert "ambíguo" in motivos["PETRK312"]
    assert "PETR3" in motivos["PETRK312"]
    assert motivos["PETRK340"] == "sem estilo de exercício no cadastro"


def test_cadeia_com_todas_as_series_ambiguas_traz_todas_em_rejeitadas_e_nenhuma_cotada(
    tmp_path: Path,
) -> None:
    # Nenhuma série declara o ativo-objeto e PETR3/PETR4 dividem a raiz: os vencimentos saem das
    # séries candidatas (ambíguas inclusive) e elas aparecem com motivo, nunca em silêncio.
    m = montar(tmp_path, cadastro=cadastro_sem_objetos())
    m.feed.watch(["PETR4"], ["PETR4"])
    assert _series(m.cliente.topicos, "PETR4") == set()  # ambígua não se assina
    alimentar(m.board, "PETR4", ULT=30.0, OCP=29.5, OVD=30.5)
    for serie in ("PETRK300", "PETRK312"):  # mesmo com valor no quadro: de quem é?
        alimentar(m.board, serie, ULT=1.0, OCP=0.9, OVD=1.1)
    chain = m.feed.get_chain("PETR4")
    assert chain.quotes == ()
    motivos = {r.symbol: r.reason for r in chain.rejected_series}
    assert {"PETRK300", "PETRW300", "PETRK312", "PETRL300"} <= set(motivos)  # Nov e Dez
    assert "ambíguo" in motivos["PETRK300"]
    assert "PETR3" in motivos["PETRK300"]
    assert "PETRA300" not in motivos  # janeiro é o 3º vencimento
    assert motivos["PETRK340"] == "sem estilo de exercício no cadastro"
    assert all("ambíguo" in r or "estilo" in r for r in motivos.values())


def test_cadeia_acompanha_o_spot_vivo_na_faixa_de_strikes(tmp_path: Path) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], ["PETR4"])
    alimentar(m.board, "PETR4", ULT=27.0, OCP=26.5, OVD=27.5)
    alimentar(m.board, "PETRK330", ULT=1.0, OCP=0.9, OVD=1.1)  # strike 33: fora de 21,6 a 32,4
    alimentar(m.board, "PETRK320", ULT=1.0, OCP=0.9, OVD=1.1)  # strike 32: dentro
    chain = m.feed.get_chain("PETR4")
    assert [q.contract.symbol for q in chain.quotes] == ["PETRK320"]


# --- quadro depois de reconectar --------------------------------------------------------------


def test_recarrega_a_biblioteca_quando_ela_muda(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado", com_cotahist=False, com_cadastro=False)
    m = montar(tmp_path, lib=lib)
    m.feed.watch(["PETR4"], ["PETR4"])
    assert _series(m.cliente.topicos, "PETR4") == set()
    lib.import_file(COTAHIST_NAME, (FIXTURE / COTAHIST_NAME).read_bytes())
    lib.import_file(INSTRUMENTS_NAME, cadastro_com_objetos())
    m.feed.watch(["PETR4"], ["PETR4"])
    assert len(_series(m.cliente.topicos, "PETR4")) > 20


# --- avisos limitados --------------------------------------------------------------------------

_LOG_DO_FEED = "options_engine.adapters.outbound.tryd.feed"


def _avisos(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]


def _consultar(m: Montagem, vezes: int = 5) -> None:
    for _ in range(vezes):
        m.feed.get_quotes(["PETR4"])


def test_book_cruzado_repetido_pelo_polling_loga_uma_vez_por_minuto(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    alimentar(m.board, "PETR4", ULT=30.0, OCP=31.0, OVD=30.0)
    with caplog.at_level(logging.WARNING, logger=_LOG_DO_FEED):
        _consultar(m)
        assert len([a for a in _avisos(caplog) if "book cruzado" in a]) == 1
        m.tempo[0] = 59.9
        _consultar(m)
        assert len(_avisos(caplog)) == 1
        m.tempo[0] = 60.0
        _consultar(m)
        assert len(_avisos(caplog)) == 2
    assert all("PETR4" in a for a in _avisos(caplog))
    # A cotação segue retida: o limite é do log, não do dado.
    assert m.feed.get_quotes(["PETR4"])["PETR4"] == "aguardando dados"


def test_cada_ativo_e_motivo_tem_o_seu_aviso(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4", "VALE3"], [])
    alimentar(m.board, "PETR4", ULT=30.0, OCP=31.0, OVD=30.0)  # book cruzado
    alimentar(m.board, "VALE3", ULT=60.0, OCP=59.5, OVD="abc")  # campo ilegível
    with caplog.at_level(logging.WARNING, logger=_LOG_DO_FEED):
        for _ in range(3):
            m.feed.get_quotes(["PETR4", "VALE3"])
        avisos = _avisos(caplog)
    assert len(avisos) == 2
    assert any("PETR4" in a and "book cruzado" in a for a in avisos)
    assert any("VALE3" in a and "OVD" in a for a in avisos)


def test_valor_que_muda_a_cada_tick_nao_escapa_do_limite(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = montar(tmp_path)
    m.feed.watch(["PETR4"], [])
    with caplog.at_level(logging.WARNING, logger=_LOG_DO_FEED):
        for centavos in range(10):
            alimentar(m.board, "PETR4", ULT=30.0, OCP=31.0 + centavos / 4, OVD=30.0)
            m.feed.get_quotes(["PETR4"])
    assert len(_avisos(caplog)) == 1


# --- vários fios ---------------------------------------------------------------------------------


def test_consultas_e_assinaturas_de_varias_threads_nao_se_atropelam(tmp_path: Path) -> None:
    m = _montar_cadeia_ao_vivo(tmp_path)
    operacoes: list[Callable[[], object]] = [
        lambda: m.feed.watch(["PETR4", "VALE3"], ["PETR4"]),
        lambda: m.feed.get_quotes(["PETR4", "VALE3", "PETR44"]),
        lambda: m.feed.get_chain("PETR4"),
        m.feed.health,
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futuros = [pool.submit(operacoes[i % len(operacoes)]) for i in range(200)]
        for futuro in futuros:
            futuro.result()  # propaga qualquer exceção
    assert isinstance(m.feed.get_quotes(["PETR4"])["PETR4"], UnderlyingQuote)

"""Tradução dos valores crus do Tryd para o domínio: o zero do RTD não vira preço."""

import logging
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta, timezone

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.tryd.board import RawValue
from options_engine.adapters.outbound.tryd.translation import (
    parse_tryd_timestamp,
    to_option_quote,
    to_underlying_quote,
)
from options_engine.domain.model.chain import OptionQuote, RejectedSeries
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from tests.domain._builders import make_contract

FALLBACK = datetime(2026, 10, 28, 15, 0, 0, tzinfo=UTC)
HORA_TRYD = datetime(2026, 10, 28, 12, 2, 31, tzinfo=B3_UTC_OFFSET)


def f(valor: float, *, inicial: bool = False) -> RawValue:
    return RawValue("float", valor, 0.0, inicial)


def texto(valor: str) -> RawValue:
    return RawValue("str", valor, 0.0)


def inteiro(valor: int) -> RawValue:
    return RawValue("int", valor, 0.0)


def nada() -> RawValue:
    return RawValue("none", None, 0.0)


def campos_opcao(**sobrescritos: RawValue) -> dict[str, RawValue]:
    base = {
        "ULT": f(4.40),
        "OCP": f(4.42),
        "OVD": f(4.47),
        "NEG": inteiro(18502),
        "VOL": f(679557741.0),
        "HOR": texto("12:02:31"),
        "DAT": texto("28/10/2026"),
    }
    base.update(sobrescritos)
    return base


def campos_ativo(**sobrescritos: RawValue) -> dict[str, RawValue]:
    base = campos_opcao(ULT=f(52.51), OCP=f(52.50), OVD=f(52.52))
    base["FEC"] = f(51.80)
    base.update(sobrescritos)
    return base


def opcao(
    valores: Mapping[str, RawValue], *, carregado: bool = True
) -> OptionQuote | RejectedSeries | None:
    return to_option_quote(make_contract("PETRK500"), valores, carregado, FALLBACK)


def ativo(valores: Mapping[str, RawValue], *, carregado: bool = True) -> UnderlyingQuote | None:
    return to_underlying_quote("PETR4", valores, carregado, DataSource.AO_VIVO, FALLBACK)


def opcao_cotada(valores: Mapping[str, RawValue]) -> OptionQuote:
    cotacao = opcao(valores)
    assert isinstance(cotacao, OptionQuote)
    return cotacao


def opcao_rejeitada(valores: Mapping[str, RawValue]) -> RejectedSeries:
    resultado = opcao(valores)
    assert isinstance(resultado, RejectedSeries)
    return resultado


def ativo_cotado(valores: Mapping[str, RawValue]) -> UnderlyingQuote:
    cotacao = ativo(valores)
    assert cotacao is not None
    return cotacao


# --- parse_tryd_timestamp ---------------------------------------------------------------------


def test_timestamp_da_data_e_hora_do_tryd_no_fuso_da_b3() -> None:
    assert parse_tryd_timestamp("28/10/2026", "12:02:31", B3_UTC_OFFSET) == HORA_TRYD
    assert parse_tryd_timestamp("28/10/2026", "12:02:31", B3_UTC_OFFSET) == datetime(
        2026, 10, 28, 15, 2, 31, tzinfo=UTC
    )


def test_timestamp_usa_o_fuso_recebido() -> None:
    fuso = timezone(timedelta(hours=1))
    assert parse_tryd_timestamp("01/02/2026", "03:04:05", fuso) == datetime(
        2026, 2, 1, 3, 4, 5, tzinfo=fuso
    )


def test_timestamp_tolera_espacos_e_fim_de_linha_do_dde() -> None:
    assert parse_tryd_timestamp(" 28/10/2026\r\n", "12:02:31\r\n", B3_UTC_OFFSET) == HORA_TRYD


@pytest.mark.parametrize(
    ("data", "hora"),
    [
        (None, "12:02:31"),
        ("28/10/2026", None),
        (None, None),
        ("", "12:02:31"),
        ("28/10/2026", ""),
        ("28-10-2026", "12:02:31"),  # separador errado
        ("2026-10-28", "12:02:31"),  # ISO não é o formato do Tryd
        ("8/10/2026", "12:02:31"),  # sem zero à esquerda: fora do formato estrito
        ("28/10/26", "12:02:31"),
        ("31/02/2026", "12:02:31"),  # data que não existe
        ("28/13/2026", "12:02:31"),
        ("28/10/2026", "12:02"),  # sem segundos
        ("28/10/2026", "24:00:00"),
        ("28/10/2026", "12:60:00"),
        ("28/10/2026", "12:02:61"),
        ("28/10/2026", "12:02:31x"),
        ("28/10/2026 12:02:31", "12:02:31"),
        ("\uff12\uff18/10/2026", "12:02:31"),  # dígitos fullwidth não são dígitos do Tryd
        ("28/10/2026", "\uff11\uff12:02:31"),
        ("00/00/0000", "00:00:00"),
    ],
)
def test_timestamp_ilegivel_ou_ausente_e_none(data: str | None, hora: str | None) -> None:
    assert parse_tryd_timestamp(data, hora, B3_UTC_OFFSET) is None


# --- zero do RTD: o maior risco do projeto ----------------------------------------------------


def test_ativo_com_zeros_do_rtd_e_ativo_nao_carregado_nao_tem_cotacao() -> None:
    zeros = {c: f(0.0, inicial=True) for c in ("ULT", "OCP", "OVD", "NEG", "VOL", "FEC")}
    assert ativo(zeros, carregado=False) is None


def test_opcao_com_zeros_do_rtd_e_opcao_nao_carregada_nao_tem_cotacao() -> None:
    zeros = {c: f(0.0, inicial=True) for c in ("ULT", "OCP", "OVD", "NEG", "VOL")}
    assert opcao(zeros, carregado=False) is None


def test_nao_carregado_vale_mesmo_com_numeros_que_parecem_reais() -> None:
    assert ativo(campos_ativo(), carregado=False) is None
    assert opcao(campos_opcao(), carregado=False) is None


def test_nao_carregado_vem_antes_de_qualquer_leitura_de_campo() -> None:
    assert ativo(campos_ativo(NEG=texto("abc")), carregado=False) is None
    assert opcao(campos_opcao(OVD=texto("abc")), carregado=False) is None


def test_opcao_carregada_com_oferta_de_compra_zero_tem_bid_ausente_e_ask_presente() -> None:
    cotacao = opcao_cotada(campos_opcao(OCP=f(0.0)))
    assert cotacao.bid is None
    assert cotacao.ask == 4.47


def test_opcao_carregada_com_oferta_de_venda_zero_tem_ask_ausente_e_bid_presente() -> None:
    cotacao = opcao_cotada(campos_opcao(OVD=f(0.0)))
    assert cotacao.bid == 4.42
    assert cotacao.ask is None


def test_opcao_carregada_com_tudo_zero_tem_book_vazio_e_nenhum_preco() -> None:
    zeros = {c: f(0.0) for c in ("ULT", "OCP", "OVD", "NEG", "VOL")}
    cotacao = opcao_cotada(zeros)
    assert (cotacao.bid, cotacao.ask, cotacao.last) == (None, None, None)
    assert (cotacao.trades, cotacao.volume) == (0, 0.0)
    assert cotacao.is_theoretical_eligible


def test_zero_inicial_de_campo_com_ativo_carregado_por_tempo_vale_como_lado_ausente() -> None:
    """Carregado por tempo, o zero ainda inicial é o que veio: lado ausente, nunca preço 0."""
    valores = campos_opcao(OCP=f(0.0, inicial=True), ULT=f(0.0, inicial=True))
    cotacao = opcao_cotada(valores)
    assert cotacao.bid is None
    assert cotacao.last is None
    assert cotacao.ask == 4.47


def test_valor_inicial_diferente_de_zero_vale_como_veio() -> None:
    cotacao = opcao_cotada(campos_opcao(OCP=f(4.42, inicial=True)))
    assert cotacao.bid == 4.42


def test_ativo_carregado_com_zeros_nao_tem_preco_nenhum() -> None:
    zeros = {c: f(0.0) for c in ("ULT", "OCP", "OVD", "NEG", "VOL", "FEC")}
    cotacao = ativo_cotado(zeros)
    assert (cotacao.last, cotacao.bid, cotacao.ask, cotacao.previous_close) == (
        None,
        None,
        None,
        None,
    )
    assert (cotacao.trades, cotacao.volume) == (0, 0.0)


@pytest.mark.parametrize("zero", [f(0.0), inteiro(0), texto("0"), texto("0,00"), texto(""), nada()])
def test_toda_forma_de_zero_ou_vazio_vira_lado_ausente(zero: RawValue) -> None:
    cotacao = opcao_cotada(campos_opcao(OCP=zero, OVD=zero, ULT=zero))
    assert (cotacao.bid, cotacao.ask, cotacao.last) == (None, None, None)
    assert ativo_cotado(campos_ativo(OCP=zero, OVD=zero, ULT=zero, FEC=zero)).bid is None


def test_campo_ausente_do_mapa_e_lado_ausente() -> None:
    valores = campos_opcao()
    del valores["OCP"]
    del valores["ULT"]
    cotacao = opcao_cotada(valores)
    assert (cotacao.bid, cotacao.last) == (None, None)
    assert cotacao.ask == 4.47


def test_mapa_vazio_nao_e_cotacao_mesmo_carregado_por_tempo() -> None:
    """Nada chegou da ponte: não há observação, e inventar ``trades=0`` com a hora de agora
    faria a série parecer "sem negócio" (elegível ao teórico) sem ninguém ter dito isso."""
    assert opcao({}) is None
    assert ativo({}) is None


# --- números: float, int, texto pt-BR estrito -------------------------------------------------


def test_preco_float_do_rtd_passa_como_veio() -> None:
    cotacao = opcao_cotada(campos_opcao(OCP=f(61.870000000000005), OVD=f(62.0)))
    assert cotacao.bid == 61.870000000000005


def test_preco_int_positivo_vira_float() -> None:
    cotacao = opcao_cotada(campos_opcao(OCP=inteiro(4), OVD=inteiro(5)))
    assert (cotacao.bid, cotacao.ask) == (4.0, 5.0)
    assert isinstance(cotacao.bid, float)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("52,51", 52.51),
        ("1.234,5", 1234.5),
        ("1.234.567,89", 1234567.89),
        ("0,05", 0.05),
        ("52.51", 52.51),
        ("52", 52.0),
        ("  52,51\r\n", 52.51),
    ],
)
def test_texto_numerico_no_formato_estrito_vira_numero(entrada: str, esperado: float) -> None:
    assert opcao_cotada(campos_opcao(OCP=texto(entrada), OVD=f(1e9))).bid == esperado
    assert ativo_cotado(campos_ativo(ULT=texto(entrada), OCP=f(1.0), OVD=f(99.0))).last == esperado


@pytest.mark.parametrize(
    "entrada",
    [
        "abc",
        "52,5,1",
        "1.23,4",
        "1,234.5",
        "1e3",
        "-4,2",
        "+4,2",
        ",5",
        "5,",
        "4 2",
        "R$ 4,2",
        "-",
        "NaN",
        "inf",
    ],
)
def test_texto_fora_do_formato_estrito_e_ilegivel(entrada: str) -> None:
    rejeitada = opcao_rejeitada(campos_opcao(OVD=texto(entrada)))
    assert rejeitada.symbol == "PETRK500"
    assert rejeitada.reason == f"valor ilegível no campo OVD: {entrada!r}"


@pytest.mark.parametrize("ilegivel", [f(float("nan")), f(float("inf")), f(-4.2), inteiro(-1)])
def test_numero_nao_finito_ou_negativo_e_ilegivel_na_opcao(ilegivel: RawValue) -> None:
    rejeitada = opcao_rejeitada(campos_opcao(ULT=ilegivel))
    assert rejeitada.reason.startswith("valor ilegível no campo ULT: ")


def test_valor_de_tipo_outro_e_ilegivel_mesmo_que_o_texto_pareca_numero() -> None:
    rejeitada = opcao_rejeitada(campos_opcao(OCP=RawValue("outro", "4.42", 0.0)))
    assert rejeitada.reason == "valor ilegível no campo OCP: '4.42'"


def test_int_gigante_demais_para_float_e_ilegivel_sem_estourar() -> None:
    rejeitada = opcao_rejeitada(campos_opcao(OCP=inteiro(10**400)))
    assert rejeitada.reason.startswith("valor ilegível no campo OCP: ")


def test_texto_gigante_que_estoura_o_float_e_ilegivel() -> None:
    rejeitada = opcao_rejeitada(campos_opcao(OCP=texto("9" * 400)))
    assert rejeitada.reason.startswith("valor ilegível no campo OCP: ")


def test_opcao_motivo_nomeia_o_primeiro_campo_ilegivel_na_ordem_do_tryd() -> None:
    rejeitada = opcao_rejeitada(campos_opcao(OVD=texto("abc"), OCP=texto("xyz")))
    assert rejeitada.reason == "valor ilegível no campo OCP: 'xyz'"


def test_texto_ilegivel_no_ativo_deixa_so_o_campo_ausente_e_registra(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        cotacao = ativo_cotado(campos_ativo(OVD=texto("abc")))
    assert cotacao.ask is None
    assert cotacao.bid == 52.50
    assert cotacao.last == 52.51
    assert any("OVD" in r.getMessage() and "'abc'" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("ilegivel", [f(float("nan")), f(-1.0), RawValue("outro", "x", 0.0)])
def test_numero_ilegivel_no_ativo_deixa_so_o_campo_ausente(ilegivel: RawValue) -> None:
    cotacao = ativo_cotado(campos_ativo(FEC=ilegivel))
    assert cotacao.previous_close is None
    assert cotacao.last == 52.51


# --- NEG e VOL --------------------------------------------------------------------------------


def test_negocios_int_do_rtd() -> None:
    assert opcao_cotada(campos_opcao(NEG=inteiro(18502))).trades == 18502
    assert ativo_cotado(campos_ativo(NEG=inteiro(18502))).trades == 18502


@pytest.mark.parametrize("neg", [f(35.0), texto("35"), texto("35,0"), texto("1.035,0")])
def test_negocios_float_inteiro_ou_texto_inteiro_vira_int(neg: RawValue) -> None:
    esperado = 1035 if neg.value == "1.035,0" else 35
    cotacao = opcao_cotada(campos_opcao(NEG=neg))
    assert cotacao.trades == esperado
    assert isinstance(cotacao.trades, int)


def test_negocios_em_texto_de_ponto_com_decimais_nao_e_inteiro_e_rejeita_a_serie() -> None:
    """ "1.234" é decimal no formato de ponto (1,234), não milhar: nunca vira 1234 em silêncio."""
    rejeitada = opcao_rejeitada(campos_opcao(NEG=texto("1.234")))
    assert rejeitada.reason == "valor ilegível no campo NEG: '1.234'"


@pytest.mark.parametrize("neg", [f(35.5), f(-1.0), inteiro(-3), f(float("inf")), texto("abc")])
def test_negocios_ilegivel_rejeita_a_serie(neg: RawValue) -> None:
    rejeitada = opcao_rejeitada(campos_opcao(NEG=neg))
    assert rejeitada.reason == f"valor ilegível no campo NEG: {neg.value!r}"


@pytest.mark.parametrize("neg", [nada(), texto(""), f(0.0), inteiro(0)])
def test_negocios_ausente_ou_zero_vale_zero(neg: RawValue) -> None:
    assert opcao_cotada(campos_opcao(NEG=neg)).trades == 0
    assert ativo_cotado(campos_ativo(NEG=neg)).trades == 0


def test_negocios_ausente_do_mapa_vale_zero() -> None:
    valores = campos_opcao()
    del valores["NEG"]
    assert opcao_cotada(valores).trades == 0


def test_volume_financeiro_float_do_rtd() -> None:
    assert opcao_cotada(campos_opcao(VOL=f(679557741.0))).volume == 679557741.0
    assert ativo_cotado(campos_ativo(VOL=f(679557741.0))).volume == 679557741.0


def test_volume_zero_negativo_vira_zero_positivo() -> None:
    volume = opcao_cotada(campos_opcao(VOL=f(-0.0))).volume
    assert volume == 0.0
    assert math.copysign(1.0, volume) == 1.0


def test_volume_texto_pt_br() -> None:
    assert opcao_cotada(campos_opcao(VOL=texto("1.234.567,5"))).volume == 1234567.5


@pytest.mark.parametrize("vol", [nada(), texto(""), f(0.0), inteiro(0)])
def test_volume_ausente_ou_zero_vale_zero(vol: RawValue) -> None:
    assert opcao_cotada(campos_opcao(VOL=vol)).volume == 0.0
    assert ativo_cotado(campos_ativo(VOL=vol)).volume == 0.0


@pytest.mark.parametrize("vol", [f(-1.0), f(float("nan")), f(float("inf")), texto("abc")])
def test_volume_ilegivel_rejeita_a_serie(vol: RawValue) -> None:
    rejeitada = opcao_rejeitada(campos_opcao(VOL=vol))
    assert rejeitada.reason.startswith("valor ilegível no campo VOL: ")


@pytest.mark.parametrize(
    ("campo", "ilegivel"),
    [
        ("NEG", f(35.5)),
        ("NEG", f(-1.0)),
        ("NEG", texto("abc")),
        ("VOL", f(-1.0)),
        ("VOL", f(float("nan"))),
        ("VOL", texto("abc")),
    ],
)
def test_negocios_ou_volume_ilegivel_no_ativo_tira_a_cotacao_e_registra(
    campo: str, ilegivel: RawValue, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        assert ativo(campos_ativo(**{campo: ilegivel})) is None
    assert any(campo in r.getMessage() and "PETR4" in r.getMessage() for r in caplog.records)


# --- book cruzado -----------------------------------------------------------------------------


def test_opcao_com_book_cruzado_na_fonte_e_serie_rejeitada() -> None:
    rejeitada = opcao_rejeitada(campos_opcao(OCP=f(4.47), OVD=f(4.42)))
    assert rejeitada == RejectedSeries("PETRK500", "book cruzado na fonte (Tryd)")


def test_opcao_com_book_travado_e_cotacao_valida() -> None:
    cotacao = opcao_cotada(campos_opcao(OCP=f(4.42), OVD=f(4.42)))
    assert (cotacao.bid, cotacao.ask) == (4.42, 4.42)


def test_book_cruzado_so_vale_com_os_dois_lados_presentes() -> None:
    assert opcao_cotada(campos_opcao(OCP=f(9.0), OVD=f(0.0))).bid == 9.0
    assert opcao_cotada(campos_opcao(OCP=f(0.0), OVD=f(1.0))).ask == 1.0


def test_ativo_com_book_cruzado_na_fonte_nao_tem_cotacao(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        assert ativo(campos_ativo(OCP=f(52.60), OVD=f(52.52))) is None
    assert any("book cruzado" in r.getMessage() for r in caplog.records)


# --- montagem da cotação ----------------------------------------------------------------------


def test_opcao_montada_com_todos_os_campos() -> None:
    contrato = make_contract("PETRK500")
    cotacao = to_option_quote(contrato, campos_opcao(), True, FALLBACK)
    assert cotacao == OptionQuote(
        contract=contrato,
        bid=4.42,
        ask=4.47,
        last=4.40,
        trades=18502,
        volume=679557741.0,
        timestamp=HORA_TRYD,
    )


def test_ativo_montado_com_todos_os_campos() -> None:
    cotacao = to_underlying_quote("PETR4", campos_ativo(), True, DataSource.ATRASADO, FALLBACK)
    assert cotacao == UnderlyingQuote(
        symbol="PETR4",
        last=52.51,
        bid=52.50,
        ask=52.52,
        previous_close=51.80,
        trades=18502,
        volume=679557741.0,
        timestamp=HORA_TRYD,
        source=DataSource.ATRASADO,
    )


def test_fechamento_anterior_zero_do_ativo_e_ausente() -> None:
    assert ativo_cotado(campos_ativo(FEC=f(0.0))).previous_close is None


# --- horário ----------------------------------------------------------------------------------


def test_timestamp_vem_de_dat_e_hor_no_fuso_da_b3() -> None:
    assert opcao_cotada(campos_opcao()).timestamp == HORA_TRYD
    assert ativo_cotado(campos_ativo()).timestamp == HORA_TRYD


@pytest.mark.parametrize("ausente", ["HOR", "DAT"])
def test_sem_hor_ou_dat_usa_o_horario_de_fallback(ausente: str) -> None:
    valores = campos_opcao()
    del valores[ausente]
    assert opcao_cotada(valores).timestamp == FALLBACK
    valores_ativo = campos_ativo()
    del valores_ativo[ausente]
    assert ativo_cotado(valores_ativo).timestamp == FALLBACK


@pytest.mark.parametrize(
    "hora",
    [nada(), texto(""), texto("abc"), f(0.0, inicial=True), f(0.5), RawValue("outro", "x", 0.0)],
)
def test_hor_ilegivel_ou_que_nao_e_texto_usa_o_horario_de_fallback(hora: RawValue) -> None:
    assert opcao_cotada(campos_opcao(HOR=hora)).timestamp == FALLBACK
    assert ativo_cotado(campos_ativo(HOR=hora)).timestamp == FALLBACK


def test_ativo_carrega_a_fonte_que_o_chamador_informa() -> None:
    for fonte in DataSource:
        cotacao = to_underlying_quote("PETR4", campos_ativo(), True, fonte, FALLBACK)
        assert cotacao is not None
        assert cotacao.source is fonte
        assert cotacao.symbol == "PETR4"


# --- dado da fonte nunca derruba o VO ---------------------------------------------------------

LIXOS = [
    f(float("nan")),
    f(float("inf")),
    f(float("-inf")),
    f(-1.0),
    f(-0.0),
    f(1e308),
    f(5e-324),
    inteiro(-1),
    inteiro(10**400),
    texto("abc"),
    texto("1e999"),
    texto("9" * 400),
    texto("\x00"),
    RawValue("outro", "<obj>", 0.0),
    RawValue("float", "não é float", 0.0),
    RawValue("none", 3.0, 0.0),
    RawValue("int", True, 0.0),  # bool não é número do Tryd
    nada(),
]


@pytest.mark.parametrize("campo", ["ULT", "OCP", "OVD", "NEG", "VOL", "FEC", "HOR", "DAT"])
@pytest.mark.parametrize("lixo", LIXOS)
def test_lixo_em_qualquer_campo_nunca_derruba_o_vo(campo: str, lixo: RawValue) -> None:
    resultado_opcao = opcao(campos_opcao(**{campo: lixo}))
    assert resultado_opcao is None or isinstance(resultado_opcao, OptionQuote | RejectedSeries)
    resultado_ativo = ativo(campos_ativo(**{campo: lixo}))
    assert resultado_ativo is None or isinstance(resultado_ativo, UnderlyingQuote)

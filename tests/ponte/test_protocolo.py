"""Protocolo da ponte — JSON por linha, ida e volta de todas as mensagens."""

import json
import math
from decimal import Decimal

import pytest

from options_ponte.protocolo import (
    CAMPOS_ATIVO,
    CAMPOS_OPCAO,
    CLSID,
    LIMITE_TOPICOS,
    PORTA_PONTE,
    PROGID,
    Assinar,
    Cancelar,
    Encerrar,
    ErroDeProtocolo,
    Mensagem,
    Ping,
    Pong,
    Status,
    Valor,
    classificar_valor,
    codificar,
    decodificar,
    topico_rtd,
)

INSTANTE = "2026-10-28T12:03:00-03:00"

# (mensagem, valor da chave "tipo" na linha)
MENSAGENS: list[tuple[Mensagem, str]] = [
    (Valor("PETR4", "ULT", "float", 38.42, INSTANTE), "valor"),
    (Valor("PETR4", "NEG", "int", 1250, INSTANTE), "valor"),
    (Valor("PETR4", "HOR", "str", "12:02:31", INSTANTE), "valor"),
    (Valor("PETR4", "DAT", "str", "28/10/2026", INSTANTE), "valor"),
    (Valor("PETRK500", "OCP", "none", None, INSTANTE), "valor"),
    (Valor("PETRK500", "OVD", "outro", "Decimal('1.5')", INSTANTE), "valor"),
    (Valor("PETRK500", "OCP", "float", 0.0, INSTANTE, inicial=True), "valor"),
    (Valor("PETRK500", "OCP", "float", 4.42, INSTANTE, inicial=False), "valor"),
    (Status("iniciando", None, 0), "status"),
    (Status("conectado", None, 12), "status"),
    (Status("perdido", "Heartbeat do servidor RTD falhou", 12), "status"),
    (Assinar((("PETR4", "ULT"), ("VALE3", "OCP"))), "assinar"),
    (Assinar(()), "assinar"),
    (Cancelar((("PETR4", "ULT"),)), "cancelar"),
    (Ping(), "ping"),
    (Pong(), "pong"),
    (Encerrar(), "encerrar"),
]
IDS = [f"{tipo}-{i}" for i, (_, tipo) in enumerate(MENSAGENS)]


def test_constantes_do_servidor_rtd_do_tryd() -> None:
    assert PROGID == "RTDTrading.RtdServer"
    assert CLSID == "{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}"


def test_topico_rtd_acrescenta_o_sufixo_de_book_ao_ticker() -> None:
    assert topico_rtd("PETRK500", "ULT") == ("PETRK500_B_0", "ULT")


@pytest.mark.parametrize(("mensagem", "tipo"), MENSAGENS, ids=IDS)
def test_ida_e_volta_preserva_a_mensagem(mensagem: Mensagem, tipo: str) -> None:
    assert decodificar(codificar(mensagem)) == mensagem


@pytest.mark.parametrize(("mensagem", "tipo"), MENSAGENS, ids=IDS)
def test_codificar_gera_uma_linha_json_utf8_com_a_chave_tipo(mensagem: Mensagem, tipo: str) -> None:
    linha = codificar(mensagem)
    assert linha.endswith(b"\n")
    assert linha.count(b"\n") == 1
    assert json.loads(linha.decode("utf-8"))["tipo"] == tipo


def test_codificar_mantem_acentos_em_utf8_e_decodificar_devolve_o_texto() -> None:
    mensagem = Status("perdido", "limite de tópicos excedido", 3)
    linha = codificar(mensagem)
    assert "tópicos".encode() in linha
    assert decodificar(linha) == mensagem


def test_decodificar_aceita_a_linha_com_ou_sem_terminador() -> None:
    assert decodificar(b'{"tipo":"ping"}') == Ping()
    assert decodificar(b'{"tipo":"ping"}\n') == Ping()
    assert decodificar(b'{"tipo":"ping"}\r\n') == Ping()


def test_decodificar_devolve_topicos_como_tuplas() -> None:
    mensagem = decodificar(b'{"tipo":"assinar","topicos":[["PETR4","ULT"]]}')
    assert mensagem == Assinar((("PETR4", "ULT"),))
    assert isinstance(mensagem, Assinar)
    assert isinstance(mensagem.topicos, tuple)
    assert isinstance(mensagem.topicos[0], tuple)


def test_valor_nasce_nao_inicial() -> None:
    assert Valor("PETR4", "ULT", "float", 38.42, INSTANTE).inicial is False


def test_inicial_so_vai_na_linha_quando_verdadeiro() -> None:
    comum = json.loads(codificar(Valor("PETR4", "ULT", "float", 38.42, INSTANTE)))
    inicial = json.loads(codificar(Valor("PETR4", "ULT", "float", 0.0, INSTANTE, inicial=True)))
    assert "inicial" not in comum
    assert inicial["inicial"] is True


def test_decodificar_valor_sem_a_chave_inicial_devolve_nao_inicial() -> None:
    linha = (
        b'{"tipo":"valor","ticker":"PETR4","campo":"ULT","tipo_valor":"float",'
        b'"valor":38.42,"instante":"x"}'
    )
    volta = decodificar(linha)
    assert volta == Valor("PETR4", "ULT", "float", 38.42, "x")
    assert isinstance(volta, Valor)
    assert volta.inicial is False


def test_decodificar_aceita_inicial_falso_explicito() -> None:
    linha = (
        b'{"tipo":"valor","ticker":"PETR4","campo":"ULT","tipo_valor":"float",'
        b'"valor":38.42,"instante":"x","inicial":false}'
    )
    assert decodificar(linha) == Valor("PETR4", "ULT", "float", 38.42, "x", inicial=False)


@pytest.mark.parametrize("inicial", ["1", "0", '"sim"', '"true"', "null", "[true]"])
def test_decodificar_recusa_inicial_que_nao_e_booleano(inicial: str) -> None:
    linha = (
        b'{"tipo":"valor","ticker":"PETR4","campo":"ULT","tipo_valor":"float",'
        b'"valor":38.42,"instante":"x","inicial":' + inicial.encode() + b"}"
    )
    with pytest.raises(ErroDeProtocolo, match="inicial"):
        decodificar(linha)


def test_valor_nao_finito_sobrevive_a_ida_e_volta() -> None:
    # Python fala com Python nos dois lados; o NaN do RTD chega ao app, que decide o que fazer.
    tipo, valor = classificar_valor(math.nan)
    assert tipo == "float"
    volta = decodificar(codificar(Valor("PETR4", "ULT", tipo, valor, INSTANTE)))
    assert isinstance(volta, Valor)
    assert isinstance(volta.valor, float)
    assert math.isnan(volta.valor)


@pytest.mark.parametrize(
    "linha",
    [
        b"{lixo",
        b"",
        b"\n",
        b"\xff\xfe",
        b"[1, 2]",
        b'"ping"',
        b"{}",
        b'{"tipo":"desconhecido"}',
        b'{"tipo":7}',
        b'{"tipo":"valor"}',
        b'{"tipo":"valor","ticker":"PETR4","campo":"ULT","tipo_valor":"float",'
        b'"valor":true,"instante":"x"}',
        b'{"tipo":"valor","ticker":"PETR4","campo":"ULT","tipo_valor":"float",'
        b'"valor":[1],"instante":"x"}',
        b'{"tipo":"valor","ticker":1,"campo":"ULT","tipo_valor":"float","valor":1.0,"instante":"x"}',
        b'{"tipo":"status","tryd":"morto","motivo":null,"topicos":0}',
        b'{"tipo":"status","tryd":"conectado","motivo":3,"topicos":0}',
        b'{"tipo":"status","tryd":"conectado","motivo":null,"topicos":true}',
        b'{"tipo":"assinar"}',
        b'{"tipo":"assinar","topicos":"PETR4"}',
        b'{"tipo":"assinar","topicos":["PETR4"]}',
        b'{"tipo":"assinar","topicos":[["PETR4"]]}',
        b'{"tipo":"cancelar","topicos":[["PETR4",1]]}',
    ],
)
def test_decodificar_recusa_linha_invalida_com_erro_de_protocolo(linha: bytes) -> None:
    with pytest.raises(ErroDeProtocolo):
        decodificar(linha)


def test_erro_de_protocolo_e_um_value_error() -> None:
    assert issubclass(ErroDeProtocolo, ValueError)


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        (4.42, ("float", 4.42)),
        (1250, ("int", 1250)),
        ("12:02:31", ("str", "12:02:31")),
        (None, ("none", None)),
        (True, ("outro", "True")),
        (Decimal("1.5"), ("outro", "Decimal('1.5')")),
        (b"x", ("outro", "b'x'")),
        ("ação 😀", ("str", "ação 😀")),
        ("x\ud800y", ("outro", repr("x\ud800y"))),
        ((1, 2), ("outro", "(1, 2)")),
    ],
)
def test_classificar_valor(bruto: object, esperado: tuple[str, object]) -> None:
    assert classificar_valor(bruto) == esperado


def test_texto_que_nao_vira_utf8_sai_como_outro_e_cabe_na_linha() -> None:
    # BSTR quebrado vindo do RTD: surrogate solto não é UTF-8, e codificar() levantaria erro
    tipo, valor = classificar_valor("x\ud800y")
    assert tipo == "outro"
    assert isinstance(valor, str)
    volta = decodificar(codificar(Valor("PETR4", "HOR", tipo, valor, INSTANTE)))
    assert isinstance(volta, Valor)
    assert volta.valor == valor


def test_constantes_da_ponte_sao_a_fonte_unica_dos_padroes() -> None:
    assert (PORTA_PONTE, LIMITE_TOPICOS) == (8766, 600)
    assert CAMPOS_ATIVO == ("ULT", "OCP", "OVD", "NEG", "VOL", "FEC", "HOR", "DAT")
    assert CAMPOS_OPCAO == ("ULT", "OCP", "OVD", "NEG", "VOL", "HOR", "DAT")

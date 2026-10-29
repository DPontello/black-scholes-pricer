"""``LiveBoard`` — guarda o valor cru que chega e decide quando o ativo já "carregou"."""

import threading

import pytest

from options_engine.adapters.outbound.tryd.board import LiveBoard, RawValue
from options_engine.adapters.outbound.tryd.settings import TEMPO_CARGA_S
from options_ponte.protocolo import Valor

AGORA = "2026-10-28T12:03:00-03:00"


def test_regra_de_carga_por_atualizacao_ou_tempo() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETRK500", "PETRW500"])
    t[0] = 1.0
    assert not quadro.is_loaded("PETRK500")
    quadro.apply(Valor("PETRK500", "OCP", "float", 4.42, AGORA))
    assert quadro.is_loaded("PETRK500")
    t[0] = 3.1
    assert quadro.is_loaded("PETRW500")  # sem atualização, mas passou TEMPO_CARGA_S


def test_carga_por_tempo_vale_a_partir_de_tempo_carga_s_exato() -> None:
    t = [10.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETR4"])
    t[0] = 10.0 + TEMPO_CARGA_S - 0.1
    assert not quadro.is_loaded("PETR4")
    t[0] = 10.0 + TEMPO_CARGA_S
    assert quadro.is_loaded("PETR4")


def test_ativo_que_ninguem_assinou_nao_esta_carregado() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    t[0] = 100.0
    assert not quadro.is_loaded("PETR4")
    assert quadro.values("PETR4") == {}


def test_assinar_de_novo_nao_reinicia_a_contagem_do_tempo() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETR4"])
    t[0] = 2.0
    quadro.mark_subscribed(["PETR4", "VALE3"])  # o PETR4 já estava na lista
    t[0] = 3.1
    assert quadro.is_loaded("PETR4")
    assert not quadro.is_loaded("VALE3")  # esse começou a contar em t = 2


def test_o_quadro_guarda_o_ultimo_valor_cru_com_tipo_e_instante_de_chegada() -> None:
    t = [5.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETRK500"])
    quadro.apply(Valor("PETRK500", "OCP", "float", 0.0, AGORA))  # zero do RTD: só guarda
    t[0] = 6.5
    quadro.apply(Valor("PETRK500", "OCP", "float", 4.42, AGORA))
    quadro.apply(Valor("PETRK500", "HOR", "str", "12:02:31", AGORA))
    quadro.apply(Valor("PETRK500", "NEG", "none", None, AGORA))
    assert quadro.values("PETRK500") == {
        "OCP": RawValue("float", 4.42, 6.5, False),
        "HOR": RawValue("str", "12:02:31", 6.5, False),
        "NEG": RawValue("none", None, 6.5, False),
    }


def test_values_devolve_copia_que_nao_muda_depois() -> None:
    quadro = LiveBoard(monotonic=lambda: 0.0)
    quadro.mark_subscribed(["PETR4"])
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    foto = quadro.values("PETR4")
    quadro.apply(Valor("PETR4", "ULT", "float", 38.5, AGORA))
    quadro.apply(Valor("PETR4", "OCP", "float", 38.4, AGORA))
    assert foto == {"ULT": RawValue("float", 38.4, 0.0, False)}


def test_valores_de_ativos_diferentes_nao_se_misturam() -> None:
    quadro = LiveBoard(monotonic=lambda: 0.0)
    quadro.mark_subscribed(["PETR4", "VALE3"])
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    quadro.apply(Valor("VALE3", "ULT", "float", 61.1, AGORA))
    assert quadro.values("PETR4")["ULT"].value == 38.4
    assert quadro.values("VALE3")["ULT"].value == 61.1


@pytest.mark.parametrize("inicial", [False, True])
def test_valor_de_ativo_que_ninguem_assinou_e_ignorado(inicial: bool) -> None:
    """A ponte difunde tópicos de outros clientes; o ativo esquecido também não recebe nada."""
    quadro = LiveBoard(monotonic=lambda: 100.0)
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA, inicial=inicial))
    assert quadro.values("PETR4") == {}
    assert not quadro.is_loaded("PETR4")


def test_valor_que_chega_depois_do_forget_e_ignorado() -> None:
    quadro = LiveBoard(monotonic=lambda: 0.0)
    quadro.mark_subscribed(["PETR4"])
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    quadro.forget(["PETR4"])
    quadro.apply(Valor("PETR4", "ULT", "float", 38.5, AGORA))  # em trânsito durante o Cancelar
    assert quadro.values("PETR4") == {}
    assert not quadro.is_loaded("PETR4")


def test_raw_value_diz_se_o_valor_ainda_e_o_inicial_do_connectdata_por_campo() -> None:
    t = [1.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETRK500"])
    quadro.apply(Valor("PETRK500", "OCP", "float", 0.0, AGORA, inicial=True))
    quadro.apply(Valor("PETRK500", "OVD", "float", 0.0, AGORA, inicial=True))
    t[0] = 2.0
    quadro.apply(Valor("PETRK500", "OVD", "float", 4.47, AGORA))  # só o OVD foi atualizado
    assert quadro.values("PETRK500") == {
        "OCP": RawValue("float", 0.0, 1.0, initial=True),
        "OVD": RawValue("float", 4.47, 2.0, initial=False),
    }


def test_raw_value_nasce_nao_inicial() -> None:
    assert RawValue("float", 1.0, 0.0).initial is False


def test_valor_inicial_do_connectdata_guarda_o_valor_mas_nao_carrega() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETRK500"])
    quadro.apply(Valor("PETRK500", "OCP", "float", 0.0, AGORA, inicial=True))  # o zero do RTD
    assert quadro.values("PETRK500") == {"OCP": RawValue("float", 0.0, 0.0, True)}  # quem quiser lê
    assert not quadro.is_loaded("PETRK500")


def test_valor_nao_inicial_carrega_mesmo_depois_de_um_inicial() -> None:
    quadro = LiveBoard(monotonic=lambda: 0.0)
    quadro.mark_subscribed(["PETRK500"])
    quadro.apply(Valor("PETRK500", "OCP", "float", 0.0, AGORA, inicial=True))
    assert not quadro.is_loaded("PETRK500")
    quadro.apply(Valor("PETRK500", "OVD", "float", 4.47, AGORA, inicial=False))
    assert quadro.is_loaded("PETRK500")  # chegou atualização de verdade, de qualquer campo


def test_so_valor_inicial_carrega_pelo_tempo() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETRK500"])
    quadro.apply(Valor("PETRK500", "OCP", "float", 0.0, AGORA, inicial=True))
    t[0] = TEMPO_CARGA_S - 0.1
    assert not quadro.is_loaded("PETRK500")
    t[0] = TEMPO_CARGA_S
    assert quadro.is_loaded("PETRK500")


def test_forget_volta_o_ativo_ao_estado_de_nunca_assinado() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETR4", "VALE3"])
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    quadro.apply(Valor("VALE3", "ULT", "float", 61.1, AGORA))
    assert quadro.is_loaded("PETR4")

    quadro.forget(["PETR4"])
    t[0] = 100.0  # nem o tempo carrega quem foi esquecido: a contagem também some
    assert quadro.values("PETR4") == {}
    assert not quadro.is_loaded("PETR4")
    assert quadro.values("VALE3")["ULT"].value == 61.1  # os outros ativos ficam como estavam
    assert quadro.is_loaded("VALE3")


def test_ativo_esquecido_e_assinado_de_novo_comeca_a_contar_do_zero() -> None:
    t = [0.0]
    quadro = LiveBoard(monotonic=lambda: t[0])
    quadro.mark_subscribed(["PETR4"])
    quadro.apply(Valor("PETR4", "ULT", "float", 38.4, AGORA))
    t[0] = 10.0
    quadro.forget(["PETR4"])
    quadro.mark_subscribed(["PETR4"])  # nova assinatura, em t = 10
    assert not quadro.is_loaded("PETR4")  # o Valor de antes não vale
    t[0] = 10.0 + TEMPO_CARGA_S - 0.1
    assert not quadro.is_loaded("PETR4")
    t[0] = 10.0 + TEMPO_CARGA_S
    assert quadro.is_loaded("PETR4")


def test_forget_de_ativo_desconhecido_nao_faz_nada() -> None:
    quadro = LiveBoard(monotonic=lambda: 0.0)
    quadro.forget(["PETR4"])
    assert quadro.values("PETR4") == {}


def test_varias_threads_aplicando_e_lendo_nao_perdem_valor() -> None:
    quadro = LiveBoard()
    erros: list[BaseException] = []

    def escrever(ticker: str) -> None:
        try:
            quadro.mark_subscribed([ticker])
            for i in range(300):
                quadro.apply(Valor(ticker, f"C{i % 5}", "int", i, AGORA))
                quadro.values(ticker)
                quadro.is_loaded(ticker)
        except BaseException as erro:  # o teste só quer saber se alguma thread falhou
            erros.append(erro)

    threads = [threading.Thread(target=escrever, args=(f"T{n}",)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert erros == []
    for n in range(8):
        assert {c: v.value for c, v in quadro.values(f"T{n}").items()} == {
            "C0": 295,
            "C1": 296,
            "C2": 297,
            "C3": 298,
            "C4": 299,
        }

"""Registro de tópicos da ponte — ids para o ConnectData, sem repetição e com limite."""

import pytest

from options_ponte.assinaturas import LimiteDeTopicos, RegistroDeTopicos


def test_adicionar_devolve_um_id_por_topico_novo() -> None:
    registro = RegistroDeTopicos(limite=10)
    novos = registro.adicionar([("PETR4", "ULT"), ("PETR4", "OCP")])
    assert [topico for _, topico in novos] == [("PETR4", "ULT"), ("PETR4", "OCP")]
    ids = [id_ for id_, _ in novos]
    assert len(set(ids)) == 2
    assert registro.total == 2
    for id_, topico in novos:
        assert registro.topico(id_) == topico


def test_topico_ja_assinado_e_ignorado() -> None:
    registro = RegistroDeTopicos(limite=10)
    registro.adicionar([("PETR4", "ULT")])
    novos = registro.adicionar([("PETR4", "ULT"), ("VALE3", "ULT")])
    assert [topico for _, topico in novos] == [("VALE3", "ULT")]
    assert registro.total == 2


def test_repeticao_dentro_do_mesmo_lote_conta_uma_vez() -> None:
    registro = RegistroDeTopicos(limite=10)
    novos = registro.adicionar([("PETR4", "ULT"), ("PETR4", "ULT")])
    assert len(novos) == 1
    assert registro.total == 1


def test_lote_acima_do_limite_nao_registra_nenhum_topico_do_lote() -> None:
    registro = RegistroDeTopicos(limite=3)
    registro.adicionar([("PETR4", "ULT")])
    with pytest.raises(LimiteDeTopicos, match="limite de tópicos"):
        registro.adicionar([("PETR4", "OCP"), ("PETR4", "OVD"), ("PETR4", "NEG")])
    assert registro.total == 1
    # nada do lote recusado ficou para trás: o espaço continua livre
    assert len(registro.adicionar([("PETR4", "OCP"), ("PETR4", "OVD")])) == 2


def test_lote_que_enche_exatamente_o_limite_passa() -> None:
    registro = RegistroDeTopicos(limite=2)
    assert len(registro.adicionar([("PETR4", "ULT"), ("PETR4", "OCP")])) == 2
    assert registro.total == 2


def test_reassinar_com_o_registro_cheio_nao_estoura_o_limite() -> None:
    registro = RegistroDeTopicos(limite=1)
    registro.adicionar([("PETR4", "ULT")])
    assert registro.adicionar([("PETR4", "ULT")]) == ()


def test_remover_devolve_os_ids_e_libera_espaco_no_limite() -> None:
    registro = RegistroDeTopicos(limite=2)
    (primeiro, _), (segundo, _) = registro.adicionar([("PETR4", "ULT"), ("PETR4", "OCP")])
    assert registro.remover([("PETR4", "OCP")]) == (segundo,)
    assert registro.total == 1
    assert registro.topico(segundo) is None
    assert registro.topico(primeiro) == ("PETR4", "ULT")
    assert len(registro.adicionar([("VALE3", "ULT")])) == 1


def test_remover_topico_nao_assinado_e_ignorado() -> None:
    registro = RegistroDeTopicos(limite=2)
    registro.adicionar([("PETR4", "ULT")])
    assert registro.remover([("VALE3", "ULT")]) == ()
    assert registro.total == 1


def test_id_de_topico_removido_nao_e_reaproveitado() -> None:
    registro = RegistroDeTopicos(limite=2)
    ((antigo, _),) = registro.adicionar([("PETR4", "ULT")])
    registro.remover([("PETR4", "ULT")])
    ((novo, _),) = registro.adicionar([("PETR4", "ULT")])
    assert novo != antigo


def test_topico_de_id_desconhecido_e_none() -> None:
    assert RegistroDeTopicos(limite=2).topico(99) is None


def test_assinados_lista_os_que_ficaram_com_os_ids_na_ordem_de_entrada() -> None:
    registro = RegistroDeTopicos(limite=10)
    registro.adicionar([("PETR4", "ULT"), ("PETR4", "OCP"), ("VALE3", "ULT")])
    registro.remover([("PETR4", "OCP")])
    assert registro.assinados() == ((1, ("PETR4", "ULT")), (3, ("VALE3", "ULT")))

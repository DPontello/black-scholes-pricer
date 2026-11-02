"""``JsonSimulationRepository``: um JSON por simulação em ``simulacoes/`` da pasta do perfil."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from options_engine.adapters.outbound.storage.simulations import JsonSimulationRepository
from options_engine.application.ports.inbound import (
    BuilderLegInput,
    BuilderRequest,
    BuilderStockInput,
)
from options_engine.application.ports.simulations import (
    SavedSimulation,
    SimulationRepository,
    UnreadableFile,
)
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import (
    ProfileFolderUnavailableError,
    UnknownRecordError,
    UnreadableRecordError,
)

COBERTA = SavedSimulation(
    "0123456789abcdef0123456789abcdef",
    "coberta de novembro",
    datetime(2026, 11, 4, 11, 0, tzinfo=UTC),
    BuilderRequest(
        "PETR4",
        (BuilderLegInput("PETRK320", Side.SELL, 100, 1.05),),
        BuilderStockInput(Side.BUY, 100, StockOrigin.CARTEIRA, 29.5),
        "venda_coberta",
    ),
)


def _repositorio(tmp_path: Path) -> JsonSimulationRepository:
    pasta = tmp_path / "perfil"
    pasta.mkdir()
    return JsonSimulationRepository(pasta)


def test_cumpre_o_protocol(tmp_path: Path) -> None:
    assert isinstance(_repositorio(tmp_path), SimulationRepository)


def test_ida_e_volta_com_o_arquivo_legivel(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.save(COBERTA)
    assert repositorio.load(COBERTA.id) == COBERTA
    assert repositorio.list() == (COBERTA,)
    gravado = json.loads(
        (tmp_path / "perfil" / "simulacoes" / f"{COBERTA.id}.json").read_text(encoding="utf-8")
    )
    assert gravado["versao"] == 1
    assert gravado["pernas"] == [
        {"ticker": "PETRK320", "lado": "venda", "quantidade": 100, "preco": 1.05}
    ]
    assert gravado["acao"] == {
        "lado": "compra",
        "quantidade": 100,
        "origem": "carteira",
        "preco": 29.5,
    }


def test_sem_pasta_de_simulacoes_a_lista_e_vazia(tmp_path: Path) -> None:
    assert _repositorio(tmp_path).list() == ()


@pytest.mark.parametrize(
    ("conteudo", "motivo"),
    [
        ('{"versao": 1, "id": "x"', "JSON"),
        ('{"versao": 2}', "versão 2"),
        ('{"versao": 1}', "campo"),
    ],
)
def test_arquivo_ilegivel_e_listado_e_preservado(
    tmp_path: Path, conteudo: str, motivo: str
) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.save(COBERTA)
    ruim = tmp_path / "perfil" / "simulacoes" / "ffffffffffffffffffffffffffffffff.json"
    ruim.write_text(conteudo, encoding="utf-8")
    itens = repositorio.list()
    assert COBERTA in itens
    (ilegivel,) = [i for i in itens if isinstance(i, UnreadableFile)]
    assert ilegivel.path == str(ruim) and motivo in ilegivel.reason
    with pytest.raises(UnreadableRecordError, match=motivo):
        repositorio.load("ffffffffffffffffffffffffffffffff")
    assert ruim.read_text(encoding="utf-8") == conteudo


def test_apaga_e_id_desconhecido_ou_invalido(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.save(COBERTA)
    repositorio.delete(COBERTA.id)
    assert repositorio.list() == ()
    for desconhecido in (COBERTA.id, "../perfil", "a/b"):
        with pytest.raises(UnknownRecordError):
            repositorio.load(desconhecido)
        with pytest.raises(UnknownRecordError):
            repositorio.delete(desconhecido)


def test_pasta_do_perfil_fora_do_ar_e_erro_claro(tmp_path: Path) -> None:
    repositorio = JsonSimulationRepository(tmp_path / "nuvem_desmontada")
    with pytest.raises(ProfileFolderUnavailableError, match="nuvem_desmontada"):
        repositorio.save(COBERTA)
    assert not (tmp_path / "nuvem_desmontada").exists()


def test_json_que_nao_e_objeto_e_ilegivel(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    (tmp_path / "perfil" / "simulacoes").mkdir()
    (tmp_path / "perfil" / "simulacoes" / "lista.json").write_text("[]", encoding="utf-8")
    (ilegivel,) = repositorio.list()
    assert isinstance(ilegivel, UnreadableFile) and "não é um objeto" in ilegivel.reason

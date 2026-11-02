"""``JsonOperationRepository``: ``operacoes/<data>_<ativo>_<id8>.json`` na pasta do perfil."""

import json
from pathlib import Path

import pytest

from options_engine.adapters.outbound.storage.operations import JsonOperationRepository
from options_engine.application.ports.outbound import UnreadableFile
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import (
    ProfileFolderUnavailableError,
    UnknownRecordError,
    UnreadableRecordError,
)
from options_engine.domain.portfolio.exercise import apply_exercise
from options_engine.domain.portfolio.model import Close, Expired, Open, Operation
from tests.portfolio._builders import D1, D2, D3, acao, call, operacao, put

ID = "0f1e2d3c4b5a69788796a5b4c3d2e1f0"


def _todos_os_eventos() -> Operation:
    coberta = operacao(
        [call(32.0), acao(StockOrigin.CARTEIRA), put(28.0)],
        [
            Open(0, D1, Side.SELL, 200, 1.05, costs=0.37),
            Close(0, D2, 100, 0.40),
            Open(2, D1, Side.BUY, 100, 0.50),
            Expired(2, D3),
        ],
        id_=ID,
        nome="coberta de novembro",
    )
    return apply_exercise(coberta, 0, 100, D3, portfolio_average=29.5)


def _repositorio(tmp_path: Path, nome: str = "perfil") -> JsonOperationRepository:
    pasta = tmp_path / nome
    pasta.mkdir()
    return JsonOperationRepository(pasta)


def test_ida_e_volta_com_todos_os_tipos_de_evento(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    operacao_ = _todos_os_eventos()
    repositorio.save(operacao_)
    assert repositorio.load(ID) == operacao_
    assert repositorio.list() == (operacao_,)


def test_arquivo_tem_data_ativo_e_id_no_nome_e_o_json_legivel(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    repositorio.save(_todos_os_eventos())
    (arquivo,) = (tmp_path / "perfil" / "operacoes").iterdir()
    assert arquivo.name == f"2026-11-04_PETR4_{ID[:8]}.json"
    gravado = json.loads(arquivo.read_text(encoding="utf-8"))
    assert gravado["versao"] == 1
    assert gravado["pernas"][0] == {
        "tipo": "opcao",
        "ticker": "PETRK320",
        "opcao": {
            "tipo": "call",
            "strike": 32.0,
            "vencimento": "2026-11-19",
            "estilo": "americana",
        },
    }
    assert gravado["pernas"][1] == {"tipo": "acao", "ticker": "PETR4", "origem": "carteira"}
    assert [e["tipo"] for e in gravado["eventos"]] == [
        "abertura",
        "encerramento",
        "abertura",
        "po",
        "atribuicao",
        "encerramento",
    ]
    assert gravado["eventos"][0] == {
        "tipo": "abertura",
        "perna": 0,
        "data": "2026-11-04",
        "lado": "venda",
        "quantidade": 200,
        "preco": 1.05,
        "custos": 0.37,
    }


def test_regravar_um_evento_novo_mantem_um_arquivo_so(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    base = operacao([call(32.0)], [Open(0, D1, Side.SELL, 100, 1.0)], id_=ID)
    repositorio.save(base)
    repositorio.save(base.with_events(Close(0, D2, 100, 0.3)))
    assert len(list((tmp_path / "perfil" / "operacoes").iterdir())) == 1
    assert len(repositorio.load(ID).events) == 2


@pytest.mark.parametrize(
    ("conteudo", "motivo"),
    [
        ('{"versao": 1, "id": ', "JSON"),
        ('{"versao": 2, "id": "x"}', "versão 2"),
        ('{"versao": 1, "id": "x"}', "campo"),
        ("[]", "não é um objeto"),
        (
            '{"versao": 1, "id": "x", "ativo": "PETR4", "nome": "x", "criada_em": "2026-11-04", '
            '"pernas": [{"tipo": "acao", "ticker": "PETR4", "origem": "compra"}], '
            '"eventos": [{"tipo": "po", "perna": 0, "data": "2026-11-04"}]}',
            "pó só em perna de opção",
        ),
    ],
)
def test_ilegivel_e_listado_preservado_e_nunca_sobrescrito(
    tmp_path: Path, conteudo: str, motivo: str
) -> None:
    repositorio = _repositorio(tmp_path)
    boa = _todos_os_eventos()
    repositorio.save(boa)
    ruim = tmp_path / "perfil" / "operacoes" / f"2026-11-04_PETR4_{'a' * 8}.json"
    ruim.write_text(conteudo, encoding="utf-8")
    itens = repositorio.list()
    assert boa in itens
    (ilegivel,) = [i for i in itens if isinstance(i, UnreadableFile)]
    assert ilegivel.path == str(ruim) and motivo in ilegivel.reason
    regravar = operacao([call(32.0)], [], id_="a" * 32)
    with pytest.raises(UnreadableRecordError, match="ilegível"):
        repositorio.save(regravar)
    assert ruim.read_text(encoding="utf-8") == conteudo


def test_id_desconhecido_ou_invalido(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    for desconhecido in (ID, "../x", "a*b", ""):
        with pytest.raises(UnknownRecordError):
            repositorio.load(desconhecido)


def test_dois_perfis_em_pastas_diferentes_nao_se_enxergam(tmp_path: Path) -> None:
    hugo, mae = _repositorio(tmp_path, "hugo"), _repositorio(tmp_path, "mae")
    hugo.save(_todos_os_eventos())
    assert mae.list() == ()
    with pytest.raises(UnknownRecordError):
        mae.load(ID)


def test_pasta_do_perfil_fora_do_ar(tmp_path: Path) -> None:
    repositorio = JsonOperationRepository(tmp_path / "nuvem_desmontada")
    assert repositorio.list() == ()
    with pytest.raises(ProfileFolderUnavailableError, match="nuvem_desmontada"):
        repositorio.save(_todos_os_eventos())
    assert not (tmp_path / "nuvem_desmontada").exists()


def test_ids_com_o_mesmo_comeco_sao_operacoes_diferentes(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    primeira = operacao([call(32.0)], [], id_="abcdefgh" + "1" * 24)
    segunda = Operation("abcdefgh" + "2" * 24, "PETR4", "outra", D2, (call(33.0),), ())
    repositorio.save(primeira)
    repositorio.save(segunda)
    assert repositorio.load(segunda.id) == segunda
    assert repositorio.load(primeira.id) == primeira


def test_id_invalido_nao_vira_nome_de_arquivo(tmp_path: Path) -> None:
    with pytest.raises(UnknownRecordError, match="inválido"):
        _repositorio(tmp_path).save(operacao([call(32.0)], [], id_="../fora"))


def test_evento_de_tipo_desconhecido_e_ilegivel(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    pasta = tmp_path / "perfil" / "operacoes"
    pasta.mkdir()
    (pasta / "2026-11-04_PETR4_bbbbbbbb.json").write_text(
        json.dumps(
            {
                "versao": 1,
                "id": "b" * 32,
                "ativo": "PETR4",
                "nome": "x",
                "criada_em": "2026-11-04",
                "pernas": [{"tipo": "acao", "ticker": "PETR4", "origem": "compra"}],
                "eventos": [{"tipo": "dividendo", "perna": 0, "data": "2026-11-04"}],
            }
        ),
        encoding="utf-8",
    )
    (ilegivel,) = repositorio.list()
    assert isinstance(ilegivel, UnreadableFile) and "dividendo" in ilegivel.reason


def test_ida_e_volta_de_call_comprada_exercida(tmp_path: Path) -> None:
    repositorio = _repositorio(tmp_path)
    comprada = operacao([call(30.0)], [Open(0, D1, Side.BUY, 100, 1.5)], id_="c" * 32)
    exercida = apply_exercise(comprada, 0, 100, D3, costs=1.2)
    repositorio.save(exercida)
    assert repositorio.load(exercida.id) == exercida

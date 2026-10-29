"""Biblioteca de arquivos da B3 — identifica pelo conteúdo, valida e não deixa lixo."""

import io
import json
import os
import random
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.adapters.outbound.b3files.library import (
    B3FileKind,
    B3FileLibrary,
    B3FileRejectedError,
    CadastroFreshness,
    cadastro_freshness,
)
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.domain.model.errors import InvalidDomainValueError
from tests.adapters.cotahist._layout import CRLF, arquivo, registro
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "cotahist"
_AGORA = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
_PREGAO = date(2026, 10, 23)
# Menor pregão da fixture (30 pregões úteis até 23/10, atravessando o feriado de 12/10).
_PRIMEIRO_PREGAO = date(2026, 9, 11)


def _zip(nome: str, conteudo: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(nome, conteudo)
    return buffer.getvalue()


def _arquivos(raiz: Path) -> list[Path]:
    return [p for p in raiz.rglob("*") if p.is_file()]


def _lib(tmp_path: Path) -> B3FileLibrary:
    return B3FileLibrary(tmp_path / "mercado", FixedClock(_AGORA))


def _cotahist_bytes() -> bytes:
    return (FIXTURE / COTAHIST_NAME).read_bytes()


def _cadastro_bytes() -> bytes:
    return (FIXTURE / INSTRUMENTS_NAME).read_bytes()


def test_importa_cotahist_txt_e_zip_e_o_cadastro(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    txt = _cotahist_bytes()
    importado = lib.import_file(COTAHIST_NAME, txt)
    assert importado.reference_date == _PREGAO
    assert importado.first_date == _PRIMEIRO_PREGAO
    assert importado.imported_at == _AGORA
    assert (
        lib.import_file("COTAHIST_D23102026.ZIP", _zip(COTAHIST_NAME, txt)).kind
        is B3FileKind.COTAHIST
    )
    cad = lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    assert (cad.kind, cad.reference_date, cad.first_date) == (B3FileKind.CADASTRO, _PREGAO, None)


def test_arquivo_errado_e_recusado_e_nada_fica_gravado(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    truncado = b"\n".join(_cotahist_bytes().splitlines()[:-1])
    for nome, conteudo in (
        ("nota.pdf", b"%PDF-1.4 ..."),
        ("COTAHIST.TXT", truncado),
        ("lista.csv", b"Ticker;Preco\nPETR4;52,5\n"),
    ):
        with pytest.raises(B3FileRejectedError):
            lib.import_file(nome, conteudo)
    assert lib.files() == ()
    assert not _arquivos(tmp_path / "mercado")


def test_recusa_diz_o_motivo_em_portugues_sem_o_caminho_temporario(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    with pytest.raises(B3FileRejectedError, match="tipo de arquivo não reconhecido"):
        lib.import_file("nota.pdf", b"%PDF-1.4 ...")
    truncado = b"\n".join(_cotahist_bytes().splitlines()[:-1])
    with pytest.raises(B3FileRejectedError) as excecao:
        lib.import_file("COTAHIST.TXT", truncado)
    mensagem = str(excecao.value)
    assert "COTAHIST.TXT" in mensagem
    assert "truncado" in mensagem
    assert str(tmp_path) not in mensagem
    assert "/tmp" not in mensagem


@pytest.mark.parametrize(
    ("nome", "conteudo", "trecho"),
    [
        ("vazio.txt", b"", "está vazio"),
        ("cotahist.zip", _zip("LEIAME.TXT", b"nada aqui\n"), "tipo de arquivo não reconhecido"),
        ("cadastro.zip", _zip("a.csv", b"x"), "tipo de arquivo não reconhecido"),
        ("cabecalho.csv", b"TckrSymb;OptnStyle\n", "nenhum instrumento"),
    ],
)
def test_outras_recusas_nao_deixam_nada(
    tmp_path: Path, nome: str, conteudo: bytes, trecho: str
) -> None:
    lib = _lib(tmp_path)
    with pytest.raises(B3FileRejectedError, match=trecho):
        lib.import_file(nome, conteudo)
    assert not _arquivos(tmp_path / "mercado")


def test_zip_com_dados_corrompidos_no_meio_e_recusado_sem_erro_cru(tmp_path: Path) -> None:
    # Ruído incompressível: o ZIP guarda os bytes quase crus e o dano cai no meio do fluxo.
    ruido = _cotahist_bytes()[:11] + random.Random(0).randbytes(20_000)
    zipado = bytearray(_zip(COTAHIST_NAME, b"00COTAHIST.2026" + ruido))
    zipado[500:520] = b"\xff" * 20
    with pytest.raises(B3FileRejectedError, match="danificado"):
        _lib(tmp_path).import_file("COTAHIST_D23102026.ZIP", bytes(zipado))
    assert not _arquivos(tmp_path / "mercado")


def test_zip_ilegivel_logo_no_inicio_nao_e_reconhecido(tmp_path: Path) -> None:
    zipado = bytearray(_zip(COTAHIST_NAME, _cotahist_bytes()))
    inicio_dos_dados = 30 + len(COTAHIST_NAME)  # cabeçalho local do ZIP + nome do membro
    zipado[inicio_dos_dados : inicio_dos_dados + 16] = b"\xff" * 16
    with pytest.raises(B3FileRejectedError, match="tipo de arquivo não reconhecido"):
        _lib(tmp_path).import_file("COTAHIST_D23102026.ZIP", bytes(zipado))
    assert not _arquivos(tmp_path / "mercado")


def test_cadastro_com_campo_gigante_e_recusado_sem_erro_cru(tmp_path: Path) -> None:
    conteudo = b"TckrSymb;OptnStyle\nPETRK300;" + b"A" * 200_000 + b"\n"
    with pytest.raises(B3FileRejectedError, match="fora do formato"):
        _lib(tmp_path).import_file("cadastro.csv", conteudo)
    assert not _arquivos(tmp_path / "mercado")


def test_cotahist_so_com_outros_mercados_e_recusado(tmp_path: Path) -> None:
    # Mercado 020 (lote padrão) é descartado pelo parser: sem registro útil não há pregão.
    outros = arquivo(
        [registro(pregao=_PREGAO, simbolo="PETR4", mercado=20)], geracao=_PREGAO, ano=2026
    )
    with pytest.raises(B3FileRejectedError, match="nenhum registro"):
        _lib(tmp_path).import_file("COTAHIST.TXT", outros.encode("cp1252"))
    assert not _arquivos(tmp_path / "mercado")


def test_cotahist_com_varias_datas_usa_a_menor_e_a_maior(tmp_path: Path) -> None:
    dias = (date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23))
    registros = [registro(pregao=d, simbolo="PETR4", mercado=10, ultimo=30.0) for d in dias]
    texto = arquivo(registros, geracao=_PREGAO, ano=2026, fim_de_linha=CRLF)
    importado = _lib(tmp_path).import_file("COTAHIST_A2026.TXT", texto.encode("cp1252"))
    assert (importado.first_date, importado.reference_date) == (dias[0], dias[-1])


def test_cotahist_corrompido_dentro_do_zip_e_recusado(tmp_path: Path) -> None:
    truncado = b"\n".join(_cotahist_bytes().splitlines()[:-1])
    with pytest.raises(B3FileRejectedError, match="truncado"):
        _lib(tmp_path).import_file("COTAHIST_D23102026.ZIP", _zip(COTAHIST_NAME, truncado))
    assert not _arquivos(tmp_path / "mercado")


def test_reimportar_o_mesmo_nome_substitui(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    depois = datetime(2026, 10, 29, 9, 0, tzinfo=UTC)
    lib2 = B3FileLibrary(tmp_path / "mercado", FixedClock(depois))
    lib2.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    (arquivo_gravado,) = lib2.files()
    assert arquivo_gravado.imported_at == depois
    assert len(_arquivos(tmp_path / "mercado" / "cadastro")) == 1


def test_recusa_nao_estraga_o_arquivo_ja_importado_com_o_mesmo_nome(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    lib.import_file(COTAHIST_NAME, _cotahist_bytes())
    with pytest.raises(B3FileRejectedError):
        lib.import_file(COTAHIST_NAME, b"%PDF-1.4 ...")
    (mantido,) = lib.files()
    assert mantido.reference_date == _PREGAO
    assert mantido.path.read_bytes() == _cotahist_bytes()


def test_biblioteca_sobrevive_a_nova_instancia_e_guarda_o_layout(tmp_path: Path) -> None:
    raiz = tmp_path / "mercado"
    lib = _lib(tmp_path)
    cotahist = lib.import_file(COTAHIST_NAME, _cotahist_bytes())
    cadastro = lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    assert cotahist.path == raiz / "cotahist" / COTAHIST_NAME
    assert cadastro.path == raiz / "cadastro" / INSTRUMENTS_NAME
    assert cotahist.path.read_bytes() == _cotahist_bytes()

    outra = B3FileLibrary(raiz, FixedClock(_AGORA))
    assert outra.files() == (cadastro, cotahist)  # ordem estável: tipo e depois nome
    assert outra.latest_cadastro() == cadastro
    assert outra.cotahist_paths() == (cotahist.path,)
    indice = json.loads((raiz / "biblioteca.json").read_text(encoding="utf-8"))
    assert indice["versao"] == 1
    assert not list(raiz.rglob("*.tmp"))


def test_arquivo_apagado_a_mao_some_da_biblioteca(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    cotahist = lib.import_file(COTAHIST_NAME, _cotahist_bytes())
    lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    cotahist.path.unlink()
    assert [f.kind for f in lib.files()] == [B3FileKind.CADASTRO]
    assert lib.cotahist_paths() == ()


def test_cotahist_paths_vem_do_mais_antigo_para_o_mais_novo(tmp_path: Path) -> None:
    lib = _lib(tmp_path)

    def pregao(dia: date) -> bytes:
        registros = [registro(pregao=dia, simbolo="PETR4", mercado=10, ultimo=30.0)]
        return arquivo(registros, geracao=dia, ano=2026).encode("cp1252")

    novo = lib.import_file("A.TXT", pregao(date(2026, 10, 23)))
    antigo = lib.import_file("B.TXT", pregao(date(2026, 10, 22)))
    assert lib.cotahist_paths() == (antigo.path, novo.path)


def test_latest_cadastro_e_o_de_data_mais_recente(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    assert lib.latest_cadastro() is None
    conteudo = b"TckrSymb;OptnStyle\nPETRK300;AMER\n"
    lib.import_file("InstrumentsConsolidatedFile_20261023.csv", conteudo)
    novo = lib.import_file("InstrumentsConsolidatedFile_20261027.csv", conteudo)
    lib.import_file("InstrumentsConsolidatedFile_20261020.csv", conteudo)
    assert lib.latest_cadastro() == novo


def test_cadastro_sem_data_no_nome_tem_data_de_referencia_nula(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    cad = lib.import_file("cadastro.csv", b"TckrSymb;OptnStyle\nPETRK300;AMER\n")
    assert cad.reference_date is None
    assert (
        cadastro_freshness(lib, StaticHolidayCalendar.from_packaged_data(), date(2026, 11, 3))
        is None
    )


def test_data_impossivel_no_nome_nao_vira_data(tmp_path: Path) -> None:
    cad = _lib(tmp_path).import_file("Cad_20261399.csv", b"TckrSymb;OptnStyle\nPETRK300;AMER\n")
    assert cad.reference_date is None


@pytest.mark.parametrize(
    "nome",
    [
        "",
        "   ",
        ".",
        "..",
        "../fora.csv",
        "..\\fora.csv",
        "sub/arquivo.csv",
        "sub\\arquivo.csv",
        "/abs/arquivo.csv",
        "C:arquivo.csv",
        "com\x00nulo.csv",
        "x" * 300 + ".csv",
    ],
)
def test_nome_perigoso_e_recusado_e_nada_sai_da_raiz(tmp_path: Path, nome: str) -> None:
    lib = _lib(tmp_path)
    with pytest.raises(B3FileRejectedError, match="nome"):
        lib.import_file(nome, _cadastro_bytes())
    assert _arquivos(tmp_path) == []


def test_importacoes_simultaneas_nao_perdem_entradas_do_indice(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    conteudo = b"TckrSymb;OptnStyle\nPETRK300;AMER\n"
    nomes = [f"cadastro_{i}.csv" for i in range(12)]
    with ThreadPoolExecutor(max_workers=len(nomes)) as pool:
        list(pool.map(lambda nome: lib.import_file(nome, conteudo), nomes))
    assert sorted(f.name for f in lib.files()) == sorted(nomes)


def test_falha_ao_gravar_nao_deixa_temporario_nem_entrada_no_indice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disco_cheio(origem: object, destino: object) -> None:
        raise OSError("disco cheio")

    lib = _lib(tmp_path)
    monkeypatch.setattr(os, "replace", disco_cheio)
    with pytest.raises(OSError, match="disco cheio"):
        lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    assert not _arquivos(tmp_path / "mercado")
    assert lib.files() == ()


@pytest.mark.parametrize(
    "indice",
    [
        "[]",
        '{"versao": 2, "arquivos": []}',
        '{"versao": 1}',
        '{"versao": 1, "arquivos": [{"tipo": "outro", "nome": "a", "data": null,'
        ' "primeira_data": null, "importado_em": "2026-10-28T15:00:00+00:00"}]}',
        '{"versao": 1, "arquivos": [{"tipo": "cadastro", "nome": "a", "data": null,'
        ' "primeira_data": null, "importado_em": "2026-10-28T15:00:00"}]}',
        '{"versao": 1, "arquivos": ["a"]}',
    ],
)
def test_indice_com_formato_inesperado_e_erro_claro(tmp_path: Path, indice: str) -> None:
    raiz = tmp_path / "mercado"
    raiz.mkdir()
    (raiz / "biblioteca.json").write_text(indice, encoding="utf-8")
    with pytest.raises(InvalidDomainValueError, match=r"biblioteca\.json"):
        B3FileLibrary(raiz, FixedClock(_AGORA)).files()


def test_indice_ilegivel_e_erro_claro_e_nao_e_sobrescrito(tmp_path: Path) -> None:
    raiz = tmp_path / "mercado"
    raiz.mkdir()
    (raiz / "biblioteca.json").write_text("{ não é json", encoding="utf-8")
    lib = B3FileLibrary(raiz, FixedClock(_AGORA))
    with pytest.raises(InvalidDomainValueError, match=r"biblioteca\.json"):
        lib.files()
    with pytest.raises(InvalidDomainValueError, match=r"biblioteca\.json"):
        lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    assert (raiz / "biblioteca.json").read_text(encoding="utf-8") == "{ não é json"
    assert not (raiz / "cadastro").exists()


def test_cadastro_velho_depois_de_5_dias_uteis(tmp_path: Path) -> None:
    lib = B3FileLibrary(tmp_path / "m", FixedClock(_AGORA))
    lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    cal = StaticHolidayCalendar.from_packaged_data()
    assert cadastro_freshness(lib, cal, date(2026, 10, 30)) == CadastroFreshness(
        date(2026, 10, 23), 5, False
    )
    assert cadastro_freshness(lib, cal, date(2026, 11, 3)) == CadastroFreshness(
        date(2026, 10, 23), 6, True
    )


def test_frescor_sem_cadastro_e_nulo(tmp_path: Path) -> None:
    cal = StaticHolidayCalendar.from_packaged_data()
    assert cadastro_freshness(_lib(tmp_path), cal, date(2026, 11, 3)) is None


def test_frescor_com_cadastro_de_data_futura_conta_zero_dias(tmp_path: Path) -> None:
    lib = _lib(tmp_path)
    lib.import_file(INSTRUMENTS_NAME, _cadastro_bytes())
    cal = StaticHolidayCalendar.from_packaged_data()
    assert cadastro_freshness(lib, cal, date(2026, 10, 22)) == CadastroFreshness(
        date(2026, 10, 23), 0, False
    )

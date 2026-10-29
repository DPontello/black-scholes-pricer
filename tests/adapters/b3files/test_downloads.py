"""Importação automática dos arquivos da B3 baixados para a pasta Downloads."""

import os
import shutil
from pathlib import Path

from options_engine.adapters.outbound.b3files.downloads import DownloadsImporter
from options_engine.adapters.outbound.b3files.library import B3FileKind, B3FileLibrary
from tests.adapters._mercado import AGORA, FIXTURE, relogio
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME

_DEPOIS = AGORA.timestamp() + 3600  # baixado depois da importação feita pelo relógio do teste


def _montar(tmp_path: Path) -> tuple[DownloadsImporter, B3FileLibrary, Path]:
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    lib = B3FileLibrary(tmp_path / "mercado", relogio())
    return DownloadsImporter(lib, downloads, relogio()), lib, downloads


def _baixar(origem: Path, destino: Path, mtime: float = _DEPOIS) -> Path:
    shutil.copyfile(origem, destino)
    os.utime(destino, (mtime, mtime))
    return destino


def test_arquivo_da_b3_baixado_e_importado_quando_para_de_mudar(tmp_path: Path) -> None:
    importador, lib, downloads = _montar(tmp_path)
    _baixar(FIXTURE / COTAHIST_NAME, downloads / COTAHIST_NAME)
    _baixar(FIXTURE / INSTRUMENTS_NAME, downloads / INSTRUMENTS_NAME)
    assert importador.scan() == ()  # primeira passada: só anota o tamanho
    eventos = importador.scan()
    assert {e.nome for e in eventos} == {COTAHIST_NAME, INSTRUMENTS_NAME}
    assert all(e.importado for e in eventos)
    assert {f.kind for f in lib.files()} == {B3FileKind.COTAHIST, B3FileKind.CADASTRO}
    assert "pregão de 23/10/2026" in next(e for e in eventos if e.nome == COTAHIST_NAME).detalhe
    assert importador.scan() == ()  # nada novo: não reimporta


def test_ignora_o_que_nao_tem_nome_de_arquivo_da_b3(tmp_path: Path) -> None:
    importador, lib, downloads = _montar(tmp_path)
    _baixar(FIXTURE / INSTRUMENTS_NAME, downloads / "planilha.csv")
    (downloads / "foto.jpg").write_bytes(b"\xff\xd8")
    importador.scan()
    assert importador.scan() == ()
    assert lib.files() == ()


def test_arquivo_recusado_vira_evento_com_o_motivo_e_nao_e_tentado_de_novo(tmp_path: Path) -> None:
    importador, lib, downloads = _montar(tmp_path)
    (downloads / "COTAHIST_A2026.ZIP").write_bytes(b"nao e um zip")
    importador.scan()
    (evento,) = importador.scan()
    assert not evento.importado and "Nada foi guardado" in evento.detalhe
    assert importador.scan() == ()
    assert importador.eventos() == (evento,)
    assert lib.files() == ()


def test_arquivo_ja_importado_depois_do_download_nao_e_reimportado(tmp_path: Path) -> None:
    importador, lib, downloads = _montar(tmp_path)
    lib.import_file(INSTRUMENTS_NAME, (FIXTURE / INSTRUMENTS_NAME).read_bytes())
    _baixar(FIXTURE / INSTRUMENTS_NAME, downloads / INSTRUMENTS_NAME, mtime=AGORA.timestamp() - 60)
    importador.scan()
    assert importador.scan() == ()


def test_download_novo_com_o_mesmo_nome_e_importado_de_novo(tmp_path: Path) -> None:
    importador, _, downloads = _montar(tmp_path)
    arquivo = _baixar(FIXTURE / INSTRUMENTS_NAME, downloads / INSTRUMENTS_NAME)
    importador.scan()
    assert len(importador.scan()) == 1
    os.utime(arquivo, (_DEPOIS + 60, _DEPOIS + 60))
    importador.scan()
    assert [e.importado for e in importador.scan()] == [True]


def test_pasta_inexistente_nao_e_erro(tmp_path: Path) -> None:
    lib = B3FileLibrary(tmp_path / "mercado", relogio())
    importador = DownloadsImporter(lib, tmp_path / "nao-existe", relogio())
    assert importador.scan() == ()

"""Coerência entre o SVG do ícone e o que sai dele (scripts/gerar_icone.sh), sem o ImageMagick."""

import re
import struct
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
ICONE = RAIZ / "packaging" / "icone"
PUBLIC = RAIZ / "frontend" / "public"
SPECS = RAIZ / "packaging" / "windows"
ICON_DO_EXE = 'icon=str(RAIZ / "packaging" / "icone" / "painel-opcoes.ico")'


def _tamanho_png(caminho: Path) -> tuple[int, int]:
    return struct.unpack(">II", caminho.read_bytes()[16:24])


def test_favicon_e_copia_do_svg() -> None:
    assert (PUBLIC / "favicon.svg").read_bytes() == (ICONE / "painel-opcoes.svg").read_bytes()


def test_ico_tem_os_sete_tamanhos() -> None:
    dados = (ICONE / "painel-opcoes.ico").read_bytes()
    _, tipo, quantidade = struct.unpack("<HHH", dados[:6])
    assert tipo == 1
    larguras, alturas = set(), set()
    for i in range(quantidade):
        largura, altura = struct.unpack("<BB", dados[6 + 16 * i : 8 + 16 * i])
        larguras.add(largura or 256)  # 0 quer dizer 256
        alturas.add(altura or 256)
    assert larguras == alturas == {16, 24, 32, 48, 64, 128, 256}


def test_pngs_tem_o_tamanho_do_nome() -> None:
    assert _tamanho_png(ICONE / "painel-opcoes-256.png") == (256, 256)
    assert _tamanho_png(PUBLIC / "icone-192.png") == (192, 192)


def test_index_liga_os_dois_icones() -> None:
    index = (RAIZ / "frontend" / "index.html").read_text(encoding="utf-8")
    assert '<link rel="icon" type="image/svg+xml" href="/favicon.svg" />' in index
    assert '<link rel="icon" type="image/png" sizes="192x192" href="/icone-192.png" />' in index


def test_executaveis_usam_o_ico() -> None:
    for nome in ("painel.spec", "ponte.spec"):
        spec = (SPECS / nome).read_text(encoding="utf-8")
        assert re.search(rf"\bEXE\([^)]*{re.escape(ICON_DO_EXE)}", spec), nome

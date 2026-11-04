"""``scripts/linux/instalar.sh``: a instalação no Linux, com ``--simular`` e com ferramentas falsas.

O PATH de cada teste só tem as ferramentas falsas (python3, node, npm) e as poucas do sistema que
o roteiro usa, e o HOME é uma pasta temporária: nada toca no ``~/.local`` de verdade.
"""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "linux" / "instalar.sh"
TEMPLATE = RAIZ / "scripts" / "linux" / "painel-opcoes.desktop.in"
BASH = shutil.which("bash") or ""
SISTEMA = ("dirname", "ln", "mkdir", "sed")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not BASH, reason="roteiro de bash, para o Linux"
)

# Cada chamada vai para $FAKE_LOG; `-m venv [--clear] DIR` cria DIR/bin/python (o falso, por link).
PYTHON_FALSO = """#!/bin/sh
echo "$0 $*" >> "$FAKE_LOG"
case "$1" in
    --version) echo "Python @VERSAO@" ;;
    -m) if [ "$2" = venv ]; then
            for destino; do :; done
            mkdir -p "$destino/bin"; ln -sf "$0" "$destino/bin/python"
        fi ;;
esac
exit 0
"""
FERRAMENTA_FALSA = """#!/bin/sh
echo "$0 $*" >> "$FAKE_LOG"
"""


@dataclass
class Cenario:
    home: Path
    log: Path
    env: dict[str, str]

    @property
    def venv(self) -> Path:
        return self.home / ".local" / "share" / "painel-opcoes" / "venv"

    @property
    def desktop(self) -> Path:
        return self.home / ".local" / "share" / "applications" / "painel-opcoes.desktop"

    def rodar(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [BASH, str(SCRIPT), *args],
            env=self.env,
            capture_output=True,
            encoding="utf-8",
            check=False,
        )

    def chamadas(self) -> list[str]:
        if not self.log.exists():
            return []
        return self.log.read_text(encoding="utf-8").splitlines()


def _montar(
    tmp_path: Path,
    *,
    versao_python: str = "3.13.1",
    sem: tuple[str, ...] = (),
    nome_home: str = "home",
) -> Cenario:
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nome in SISTEMA:
        caminho = shutil.which(nome)
        assert caminho is not None, nome
        (bin_ / nome).symlink_to(caminho)
    falsos = {
        "python3": PYTHON_FALSO.replace("@VERSAO@", versao_python),
        "node": FERRAMENTA_FALSA,
        "npm": FERRAMENTA_FALSA,
    }
    for nome, conteudo in falsos.items():
        if nome not in sem:
            (bin_ / nome).write_text(conteudo, encoding="utf-8")
            (bin_ / nome).chmod(0o755)
    home = tmp_path / nome_home
    home.mkdir()
    log = tmp_path / "chamadas.log"
    return Cenario(home, log, {"HOME": str(home), "PATH": str(bin_), "FAKE_LOG": str(log)})


def _venv_quebrado(c: Cenario) -> None:
    """Venv que sobrou de um Python que saiu do PC: o link `bin/python` não leva a lugar nenhum."""
    (c.venv / "bin").mkdir(parents=True)
    (c.venv / "bin" / "python").symlink_to(c.home / "python-que-saiu")


def _linhas(saida: str, padrao: str) -> list[str]:
    return [linha for linha in saida.splitlines() if re.search(padrao, linha)]


def test_simular_mostra_o_ambiente_virtual(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    r = c.rodar("--simular")
    assert r.returncode == 0, r.stderr
    assert _linhas(r.stdout, rf"-m venv .*{re.escape(str(c.venv))}")


def test_simular_mostra_a_instalacao_editavel_com_o_extra_app(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    r = c.rodar("--simular")
    assert r.returncode == 0, r.stderr
    (linha,) = _linhas(r.stdout, r"pip install")
    assert f"{c.venv}/bin/python -m pip install -e " in linha
    assert f'"{RAIZ}[app]"' in linha


def test_simular_mostra_o_build_da_tela(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    r = c.rodar("--simular")
    assert r.returncode == 0, r.stderr
    assert _linhas(r.stdout, r"npm .*frontend.* ci$")
    assert _linhas(r.stdout, r"npm .*frontend.* run build$")


def test_simular_mostra_o_atalho_com_o_python_do_venv(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    r = c.rodar("--simular")
    assert r.returncode == 0, r.stderr
    assert str(c.desktop) in r.stdout
    assert f"Exec={c.venv}/bin/python -m options_engine app" in r.stdout
    assert "Name=Painel de Opções" in r.stdout


def test_simular_lembra_da_ponte_do_tryd(tmp_path: Path) -> None:
    r = _montar(tmp_path).rodar("--simular")
    assert r.returncode == 0, r.stderr
    assert "scripts/linux/preparar_ponte_wine.sh --verificar" in r.stdout


def test_simular_nao_grava_nada_nem_roda_a_instalacao(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    r = c.rodar("--simular")
    assert r.returncode == 0, r.stderr
    assert list(c.home.rglob("*")) == []
    assert all("--version" in chamada for chamada in c.chamadas()), c.chamadas()


def test_simular_refaz_o_venv_cujo_python_nao_roda(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    _venv_quebrado(c)
    r = c.rodar("--simular")
    assert r.returncode == 0, r.stderr
    assert _linhas(r.stdout, rf"-m venv --clear .*{re.escape(str(c.venv))}")
    assert "reaproveitado" not in r.stdout
    assert (c.venv / "bin" / "python").is_symlink()  # a simulação não mexeu em nada
    assert not any("-m venv" in chamada for chamada in c.chamadas()), c.chamadas()


@pytest.mark.parametrize("faltando", ["node", "npm"])
def test_sem_node_ou_npm_avisa_e_sai_com_erro(tmp_path: Path, faltando: str) -> None:
    c = _montar(tmp_path, sem=(faltando,))
    r = c.rodar("--simular")
    assert r.returncode != 0
    assert f"não achei o {faltando}" in r.stderr
    assert "Node.js" in r.stderr


def test_python_antigo_avisa_e_sai_com_erro(tmp_path: Path) -> None:
    c = _montar(tmp_path, versao_python="3.11.9")
    r = c.rodar("--simular")
    assert r.returncode != 0
    assert "3.12" in r.stderr
    assert "3.11.9" in r.stderr
    assert not any("venv" in chamada for chamada in c.chamadas())


@pytest.mark.parametrize("versao", ["3.12.0", "3.14.8"])
def test_python_12_ou_mais_novo_passa(tmp_path: Path, versao: str) -> None:
    r = _montar(tmp_path, versao_python=versao).rodar("--simular")
    assert r.returncode == 0, r.stderr


def test_python_que_nao_existe_avisa_e_sai_com_erro(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    c.env["PYTHON"] = "python-que-nao-existe"
    r = c.rodar("--simular")
    assert r.returncode != 0
    assert "python-que-nao-existe" in r.stderr


def test_opcao_desconhecida_mostra_o_uso_e_sai_com_2(tmp_path: Path) -> None:
    r = _montar(tmp_path).rodar("--nao-existe")
    assert r.returncode == 2
    assert "--simular" in r.stderr


def test_ajuda_mostra_o_uso_e_sai_com_0(tmp_path: Path) -> None:
    r = _montar(tmp_path).rodar("--help")
    assert r.returncode == 0
    assert "--simular" in r.stdout


def test_modelo_do_atalho() -> None:
    linhas = TEMPLATE.read_text(encoding="utf-8").splitlines()
    assert "Type=Application" in linhas
    assert "Name=Painel de Opções" in linhas
    assert "Exec=@PYTHON@ -m options_engine app" in linhas
    assert "Terminal=false" in linhas
    assert not [linha for linha in linhas if linha.startswith("Icon=")]  # sem ícone até a semana 5


def test_instala_de_verdade_e_uma_segunda_vez_reaproveita_o_ambiente(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    python_venv = f"{c.venv}/bin/python"

    primeira = c.rodar()
    assert primeira.returncode == 0, primeira.stderr
    chamadas = c.chamadas()
    assert not any("--clear" in chamada for chamada in chamadas), chamadas
    ordem = [
        next((i for i, chamada in enumerate(chamadas) if trecho in chamada), -1)
        for trecho in (f"-m venv {c.venv}", f"{python_venv} -m pip install -e {RAIZ}[app]")
    ]
    assert ordem[0] >= 0, chamadas
    assert ordem == sorted(ordem), chamadas
    assert any(chamada.endswith("ci") and "/frontend" in chamada for chamada in chamadas)
    assert any(chamada.endswith("run build") and "/frontend" in chamada for chamada in chamadas)
    texto = c.desktop.read_text(encoding="utf-8")
    assert f"Exec={python_venv} -m options_engine app\n" in texto

    segunda = c.rodar()
    assert segunda.returncode == 0, segunda.stderr
    assert sum(f"-m venv {c.venv}" in chamada for chamada in c.chamadas()) == 1
    assert "reaproveitado" in segunda.stdout
    assert c.desktop.read_text(encoding="utf-8") == texto


def test_instala_refazendo_o_venv_cujo_python_nao_roda(tmp_path: Path) -> None:
    c = _montar(tmp_path)
    _venv_quebrado(c)
    r = c.rodar()
    assert r.returncode == 0, r.stderr
    chamadas = c.chamadas()
    assert sum(f"-m venv --clear {c.venv}" in chamada for chamada in chamadas) == 1, chamadas
    assert (c.venv / "bin" / "python").exists()  # o link novo leva a um Python que roda
    assert any(f"{c.venv}/bin/python -m pip install -e" in chamada for chamada in chamadas)


NOME_ESQUISITO = "maria & $x 100%"


def test_exec_do_atalho_com_caminho_que_precisa_de_aspas(tmp_path: Path) -> None:
    c = _montar(tmp_path, nome_home=NOME_ESQUISITO)
    r = c.rodar()
    assert r.returncode == 0, r.stderr
    # Spec Desktop Entry: entre aspas, `$` escapado (a barra em dobro pelo escape do arquivo)
    # e `%` dobrado.
    esperado = f'Exec="{c.home}/.local/share/painel-opcoes/venv/bin/python" -m options_engine app'
    esperado = esperado.replace("$", "\\\\$").replace("%", "%%")
    assert esperado in c.desktop.read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(shutil.which("desktop-file-validate") is None, reason="sem desktop-file-utils")
@pytest.mark.parametrize("nome_home", ["home", NOME_ESQUISITO])
def test_atalho_gerado_passa_no_validador(tmp_path: Path, nome_home: str) -> None:
    c = _montar(tmp_path, nome_home=nome_home)
    assert c.rodar().returncode == 0
    validado = subprocess.run(
        ["desktop-file-validate", str(c.desktop)], capture_output=True, text=True, check=False
    )
    assert validado.returncode == 0, validado.stdout + validado.stderr

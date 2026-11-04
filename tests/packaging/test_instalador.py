"""Versão do instalador e o script do Inno Setup (packaging/windows), sem o Inno Setup."""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

PASTA = Path(__file__).resolve().parents[2] / "packaging" / "windows"
ISS = (PASTA / "PainelOpcoes.iss").read_text(encoding="utf-8")


def _versao() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_versao_instalador", PASTA / "versao.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize(
    ("versao", "inno"),
    [("0.5.0.dev0", "0.5.0"), ("1.0.0", "1.0.0"), ("1.2.3rc1", "1.2.3"), ("2.0", "2.0")],
)
def test_versao_do_inno_so_tem_numeros(versao: str, inno: str) -> None:
    assert _versao().versao_inno(versao) == inno


def test_versao_sem_numeros_e_recusada() -> None:
    with pytest.raises(ValueError, match="sem números"):
        _versao().versao_inno("dev")


def test_versao_vem_do_pyproject(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    versao = _versao()
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nname = "x"\nversion = "0.6.1.dev2"\n', encoding="utf-8")
    assert versao.versao_completa(pyproject) == "0.6.1.dev2"
    assert versao.main([]) == 0
    real = capsys.readouterr().out.strip()
    assert real == versao.versao_completa()
    assert versao.main(["--inno"]) == 0
    assert capsys.readouterr().out.strip() == versao.versao_inno(real)


def _diretiva(nome: str) -> str:
    achado = re.search(rf"^{nome}=(.*)$", ISS, re.M)
    assert achado is not None, nome
    return achado.group(1).strip()


def test_instala_por_usuario_sem_administrador() -> None:
    assert _diretiva("PrivilegesRequired") == "lowest"
    assert _diretiva("DefaultDirName") == r"{localappdata}\Programs\PainelOpcoes"


def test_app_id_fixo_para_a_versao_nova_instalar_por_cima() -> None:
    assert _diretiva("AppId") == "{{B68E5C59-513D-4167-93BB-309549E6ECFC}"


def test_fecha_o_app_antes_de_atualizar() -> None:
    assert _diretiva("CloseApplications") == "yes"


def test_nunca_apaga_os_dados_do_usuario() -> None:
    assert "userappdata" not in ISS.lower()
    assert "{app}" in _secao("UninstallDelete")
    for linha in _secao("UninstallDelete").splitlines() + _secao("InstallDelete").splitlines():
        if linha.startswith("Type:"):
            assert '"{app}' in linha, linha


def test_leva_o_app_e_a_ponte_com_os_atalhos() -> None:
    arquivos = _secao("Files")
    assert r'"{#Origem}\PainelOpcoes\*"; DestDir: "{app}"' in arquivos
    assert r'"{#Origem}\ponte\*"; DestDir: "{app}\ponte"' in arquivos
    atalhos = _secao("Icons")
    assert r'{autoprograms}\Painel de Opções"; Filename: "{app}\PainelOpcoes.exe"' in atalhos
    assert r'{autodesktop}\Painel de Opções"; Filename: "{app}\PainelOpcoes.exe"' in atalhos


def _secao(nome: str) -> str:
    achado = re.search(rf"^\[{nome}\]\n(.*?)(?=^\[|\Z)", ISS, re.M | re.S)
    assert achado is not None, nome
    return achado.group(1)

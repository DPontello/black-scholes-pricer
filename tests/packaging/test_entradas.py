"""Pontos de entrada e specs do PyInstaller (packaging/windows): conferidos sem o PyInstaller.

A pasta ``packaging`` não é pacote Python de propósito: o nome sombrearia o ``packaging`` do
pip e do pytest. Os módulos são carregados pelo caminho.
"""

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

import options_ponte.__main__
from options_ponte import rtd

PASTA = Path(__file__).resolve().parents[2] / "packaging" / "windows"


def _carregar(nome: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_entrada_{nome}", PASTA / f"{nome}.py")
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.mark.parametrize(
    ("argv", "esperado"),
    [
        ([], ["app"]),
        (["--sem-ponte"], ["app", "--sem-ponte"]),
        (["app", "--porta", "8799"], ["app", "--porta", "8799"]),
        (["conferir-b3", "--cotahist", "a.zip"], ["conferir-b3", "--cotahist", "a.zip"]),
    ],
)
def test_painel_sem_comando_e_o_app(argv: list[str], esperado: list[str]) -> None:
    assert _carregar("painel").argumentos(argv) == esperado


def test_painel_chama_o_main_do_options_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    painel = _carregar("painel")
    recebido: list[list[str]] = []

    def main_falso(args: list[str]) -> int:
        recebido.append(args)
        return 0

    monkeypatch.setattr(painel, "main_do_app", main_falso)
    assert painel.main(["--sem-janela"]) == 0
    assert recebido == [["app", "--sem-janela"]]


def test_ponte_e_o_main_da_ponte() -> None:
    assert _carregar("ponte").main is options_ponte.__main__.main


def test_spec_da_ponte_inclui_todo_modulo_do_pywin32_que_a_ponte_importa() -> None:
    importados = set(re.findall(r'_importar\("([\w.]+)"\)', Path(rtd.__file__).read_text("utf-8")))
    spec = (PASTA / "ponte.spec").read_text(encoding="utf-8")
    faltando = {m for m in importados - {"winreg"} if f'"{m}"' not in spec}
    assert not faltando


def test_spec_do_app_leva_os_dados_do_pacote() -> None:
    spec = (PASTA / "painel.spec").read_text(encoding="utf-8")
    dados = Path(rtd.__file__).resolve().parents[1] / "options_engine/adapters/outbound/data"
    assert {p.name for p in dados.glob("*.csv")} == {"b3_holidays.csv", "cost_schedules.csv"}
    assert '"options_engine/adapters/outbound/data"' in spec
    assert '"static"' in spec
    assert 'copy_metadata("options-engine")' in spec

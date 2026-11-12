"""A versão do app para o instalador, lida do ``pyproject.toml``.

O Inno Setup só aceita números (``0.5.0``) na versão do arquivo; o nome do instalador leva a
versão inteira (``0.5.0.dev0``). No job Windows:

    python packaging/windows/versao.py          -> 0.5.0.dev0
    python packaging/windows/versao.py --inno   -> 0.5.0
"""

import re
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def versao_completa(pyproject: Path = PYPROJECT) -> str:
    with pyproject.open("rb") as arquivo:
        return str(tomllib.load(arquivo)["project"]["version"])


def versao_inno(versao: str) -> str:
    numeros = re.match(r"\d+(\.\d+){0,3}", versao)
    if numeros is None:
        raise ValueError(f"versão sem números no começo: {versao!r}")
    return numeros.group(0)


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    versao = versao_completa()
    print(versao_inno(versao) if "--inno" in args else versao)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Ponto de entrada do ``PainelOpcoes.exe`` (PyInstaller): o comando ``app`` do options_engine.

O atalho chama o executável sem argumentos, e as opções do ``app`` (``--sem-ponte``) podem vir
sozinhas; os outros comandos (``conferir-b3``) passam como estão.
"""

import sys
from collections.abc import Sequence

from options_engine.__main__ import main as main_do_app


def argumentos(argv: Sequence[str]) -> list[str]:
    args = list(argv)
    return args if args and not args[0].startswith("-") else ["app", *args]


def main(argv: Sequence[str] | None = None) -> int:
    return main_do_app(argumentos(sys.argv[1:] if argv is None else argv))


if __name__ == "__main__":
    sys.exit(main())

"""Ponto de entrada do ``PonteTryd.exe`` (PyInstaller): os comandos da ponte do Tryd."""

import sys

from options_ponte.__main__ import main

if __name__ == "__main__":
    sys.exit(main())

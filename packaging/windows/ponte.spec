# PyInstaller: PonteTryd.exe, a ponte do Tryd (Python 3.12 de 32 bits, com pywin32). Da raiz do
# repositório:
#   pyinstaller --noconfirm packaging/windows/ponte.spec
# 32 bits porque a type library do Tryd só está registrada para 32 bits (README da ponte).
# Programa de console, para o diagnostico e o autoteste mostrarem o resultado; o app a sobe sem
# janela (spawn_process).
from pathlib import Path

RAIZ = Path(SPECPATH).parent.parent

a = Analysis(
    [str(Path(SPECPATH) / "ponte.py")],
    pathex=[str(RAIZ / "src")],
    # rtd.py importa o pywin32 por importlib, que o PyInstaller não enxerga.
    hiddenimports=[
        "pythoncom",
        "pywintypes",
        "win32com.client.CLSIDToClass",
        "win32com.client.gencache",
        "win32com.server.util",
        "win32com.universal",
    ],
    excludes=["tkinter", "options_engine", "fastapi", "uvicorn"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PonteTryd",
    console=True,
    icon=str(RAIZ / "packaging" / "icone" / "painel-opcoes.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, name="ponte")

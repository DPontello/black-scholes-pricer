# PyInstaller: PainelOpcoes.exe, o app (Python 3.12 de 64 bits). Da raiz do repositório, com o
# pacote instalado (pip install ".[app]") e a tela compilada (npm --prefix frontend run build):
#   pyinstaller --noconfirm packaging/windows/painel.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

RAIZ = Path(SPECPATH).parent.parent
SRC = RAIZ / "src"

a = Analysis(
    [str(Path(SPECPATH) / "painel.py")],
    pathex=[str(SRC)],
    datas=[
        # default_static_dir(meipass) procura a tela em <_MEIPASS>/static.
        (str(SRC / "options_engine/adapters/inbound/web/static"), "static"),
        # Calendário de feriados e tabela de custos, lidos por importlib.resources.
        (str(SRC / "options_engine/adapters/outbound/data"), "options_engine/adapters/outbound/data"),
        # A versão do GET /api/saude vem de importlib.metadata.
        *copy_metadata("options-engine"),
    ],
    hiddenimports=collect_submodules("uvicorn"),
    excludes=["tkinter", "pythoncom", "pywintypes", "win32com"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="PainelOpcoes", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="PainelOpcoes")

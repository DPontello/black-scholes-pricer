"""O Tryd 7 por dentro: a pasta do Tryd, o ``StDde.ini``, a porta e o ``Tryd.RtdServer``.

O ``StRtd.dll`` do Tryd 7 é um servidor RTD .NET dentro do processo (``InprocServer32`` =
``mscoree.dll``). O ``StDde.exe`` tenta registrá-lo em ``HKEY_CLASSES_ROOT`` e, sem administrador,
falha (``REGISTROU=False`` no ``StDde.ini``). Aqui a ponte faz o que o RegAsm faria, mas só em
``HKCU\\Software\\Classes``, nas duas visões do registro (64 e 32 bits). Nunca toca ``HKLM`` nem o
CLSID do ``RTDTrading``.

Este módulo só usa a stdlib: ``winreg`` e ``ctypes`` entram dentro das funções, para o pacote
importar (e os testes rodarem) no Linux. Não importa ``rtd``: é o ``rtd`` que importa daqui.
"""

import configparser
import contextlib
import importlib
import re
import socket
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path, PurePath
from typing import Any, Final

from options_ponte.vias import CLSID_TRYD7, PROGID_TRYD7, Raiz, Registro, Visao

__all__ = [
    "CATEGORIA_NET",
    "CLASSE_TRYD7",
    "DLL_RELATIVA",
    "INI_RELATIVO",
    "PORTA_STDDE_PADRAO",
    "RUNTIME_TRYD7",
    "RegistroWinreg",
    "caminhos_em_execucao",
    "chaves_tryd7",
    "codebase",
    "desregistrar",
    "identidade_do_assembly",
    "ler_ini_stdde",
    "ler_ini_stdde_do_arquivo",
    "pasta_do_tryd",
    "pids_do_executavel",
    "porta_aceita",
    "registrar",
]

DLL_RELATIVA: Final = Path("plugins") / "stDde" / "StRtd.dll"
INI_RELATIVO: Final = Path("plugins") / "stDde" / "StDde.ini"
PORTA_STDDE_PADRAO: Final = 12002
CLASSE_TRYD7: Final = "StRtd.Controlador.StRtdServer"
RUNTIME_TRYD7: Final = "v2.0.50727"
CATEGORIA_NET: Final = "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}"  # .NET Category do RegAsm

_EXECUTAVEL_TRYD = "tryd.exe"
_TH32CS_SNAPPROCESS = 0x2
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_TAMANHO_MAXIMO_DO_CAMINHO = 32768  # caracteres: o limite do caminho longo do Windows
_ESPERA_POWERSHELL_S = 30.0  # a primeira partida do PowerShell e do .NET é lenta
_VISOES: Final[tuple[Visao, ...]] = (64, 32)
# onde o HKCU guarda ProgIDs e CLSIDs (o HKCR é a junção com o HKLM)
_CLASSES = "Software\\Classes\\"
_RAIZES: Final[Mapping[Raiz, str]] = {
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKCU": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
}
_SECAO_SOCKET = "SOCKET_SERVER"
_IDENTIDADE = re.compile(
    r"StRtd, Version=(?P<versao>[\d.]+), Culture=\w+, PublicKeyToken=[0-9a-f]{16}"
)
_ASPAS_SIMPLES = re.compile(r"(['\u2018\u2019\u201a\u201b])")  # o PowerShell trata as quatro assim


# ---------------------------------------------------------------------------
# Registro do Windows
# ---------------------------------------------------------------------------


def _winreg() -> Any:
    return importlib.import_module("winreg")


def _raiz(winreg: Any, raiz: Raiz) -> Any:
    return getattr(winreg, _RAIZES[raiz])


def _visao(winreg: Any, visao: Visao) -> int:
    return int(winreg.KEY_WOW64_32KEY if visao == 32 else winreg.KEY_WOW64_64KEY)


def _apagar_chave(winreg: Any, raiz: Any, caminho: str, visao: int) -> None:
    """Apaga a chave de baixo para cima: o Windows não apaga uma chave que ainda tem subchaves."""
    try:
        with winreg.OpenKey(raiz, caminho, 0, winreg.KEY_READ | visao) as chave:
            filhas = [winreg.EnumKey(chave, i) for i in range(winreg.QueryInfoKey(chave)[0])]
    except FileNotFoundError:
        return
    for filha in filhas:
        _apagar_chave(winreg, raiz, f"{caminho}\\{filha}", visao)
    winreg.DeleteKeyEx(raiz, caminho, visao, 0)


class RegistroWinreg:
    """O ``Registro`` da ponte sobre o ``winreg`` (Windows e Wine), numa visão de 32 ou 64 bits.

    O ``winreg`` só é importado dentro dos métodos: construir o objeto não toca o Windows.
    """

    def ler(self, raiz: Raiz, caminho: str, nome: str, visao: Visao) -> str | None:
        winreg = _winreg()
        acesso = winreg.KEY_READ | _visao(winreg, visao)
        try:
            with winreg.OpenKey(_raiz(winreg, raiz), caminho, 0, acesso) as chave:
                return str(winreg.QueryValueEx(chave, nome)[0])
        except OSError:  # chave ou valor ausente (ou sem permissão para ler)
            return None

    def gravar(self, raiz: Raiz, caminho: str, nome: str, valor: str, visao: Visao) -> None:
        winreg = _winreg()
        acesso = winreg.KEY_WRITE | _visao(winreg, visao)
        with winreg.CreateKeyEx(_raiz(winreg, raiz), caminho, 0, acesso) as chave:
            winreg.SetValueEx(chave, nome, 0, winreg.REG_SZ, valor)

    def apagar_arvore(self, raiz: Raiz, caminho: str, visao: Visao) -> None:
        winreg = _winreg()
        _apagar_chave(winreg, _raiz(winreg, raiz), caminho, _visao(winreg, visao))


# ---------------------------------------------------------------------------
# Processos (Toolhelp32): Windows e Wine
# ---------------------------------------------------------------------------


def pids_do_executavel(nome_exe: str) -> frozenset[int]:
    """PIDs dos processos ``nome_exe`` rodando (Toolhelp32). Fora do Windows, vazio."""
    if sys.platform != "win32":
        return frozenset()
    import ctypes
    import ntpath
    from ctypes import wintypes

    class Entrada(ctypes.Structure):  # PROCESSENTRY32W
        _fields_ = (
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        )

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    criar_foto = kernel32.CreateToolhelp32Snapshot
    criar_foto.argtypes = (wintypes.DWORD, wintypes.DWORD)
    criar_foto.restype = wintypes.HANDLE
    primeiro, proximo = kernel32.Process32FirstW, kernel32.Process32NextW
    for funcao in (primeiro, proximo):
        funcao.argtypes = (wintypes.HANDLE, ctypes.POINTER(Entrada))
        funcao.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    foto = criar_foto(_TH32CS_SNAPPROCESS, 0)
    if foto is None or foto == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entrada = Entrada()
        entrada.dwSize = ctypes.sizeof(Entrada)
        # lista vazia não existe (este processo está nela): falha aqui não pode virar "Tryd fechado"
        if not primeiro(foto, ctypes.byref(entrada)):
            raise ctypes.WinError(ctypes.get_last_error())
        pids: set[int] = set()
        while True:
            # o Wine antigo põe o caminho inteiro no szExeFile
            if ntpath.basename(entrada.szExeFile).lower() == nome_exe.lower():
                pids.add(int(entrada.th32ProcessID))
            if not proximo(foto, ctypes.byref(entrada)):
                return frozenset(pids)
    finally:
        kernel32.CloseHandle(foto)


def caminhos_em_execucao(nome_exe: str) -> list[Path]:
    """O caminho completo de cada processo ``nome_exe`` rodando. Fora do Windows, vazio.

    Processo que o Windows não deixa consultar (de outro usuário, protegido) fica de fora.
    """
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    abrir = kernel32.OpenProcess
    abrir.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    abrir.restype = wintypes.HANDLE
    consultar = kernel32.QueryFullProcessImageNameW
    consultar.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    )
    consultar.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

    caminhos: list[Path] = []
    for pid in sorted(pids_do_executavel(nome_exe)):
        processo = abrir(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not processo:
            continue
        try:
            texto = ctypes.create_unicode_buffer(_TAMANHO_MAXIMO_DO_CAMINHO)
            tamanho = wintypes.DWORD(_TAMANHO_MAXIMO_DO_CAMINHO)
            if consultar(processo, 0, texto, ctypes.byref(tamanho)):
                caminhos.append(Path(texto.value))
        finally:
            kernel32.CloseHandle(processo)
    return caminhos


def pasta_do_tryd(
    caminhos: Callable[[str], list[Path]] = caminhos_em_execucao,
) -> Path | None:
    """A pasta do ``tryd.exe`` em execução (a do primeiro, se houver mais de um), ou ``None``."""
    for caminho in caminhos(_EXECUTAVEL_TRYD):
        return caminho.parent
    return None


# ---------------------------------------------------------------------------
# StDde.ini e a porta do StDde
# ---------------------------------------------------------------------------


def _porta_da_secao(secao: Mapping[str, object]) -> int | None:
    """A primeira chave com ``PORT`` no nome e valor inteiro de 1 a 65535 (``configparser`` já
    deixa os nomes em minúsculas)."""
    for chave, valor in secao.items():
        if "port" not in chave or not isinstance(valor, str):  # linha sem ``=`` vem como None
            continue
        try:
            porta = int(valor)
        except ValueError:
            continue
        if 1 <= porta <= 65535:
            return porta
    return None


def ler_ini_stdde(texto: str) -> tuple[int, str | None]:
    """``(porta, REGISTROU)`` do ``StDde.ini``; sem a porta, ``12002``, e sem a chave, ``None``.

    Tolerante: texto que não é INI dá o padrão, sem exceção. A porta vem da seção
    ``[SOCKET_SERVER]``; o ``REGISTROU`` vale em qualquer seção. Os nomes exatos das chaves se
    confirmam no PC do Tryd 7.
    """
    parser = configparser.ConfigParser(interpolation=None, strict=False, allow_no_value=True)
    with contextlib.suppress(configparser.Error):  # o que deu para ler antes do erro fica
        parser.read_string(texto)
    porta: int | None = None
    registrou: str | None = None
    for nome in parser.sections():
        secao = parser[nome]
        valor = secao.get("registrou")
        if registrou is None and isinstance(valor, str):
            registrou = valor
        if porta is None and nome.upper() == _SECAO_SOCKET:
            porta = _porta_da_secao(secao)
    return (porta if porta is not None else PORTA_STDDE_PADRAO), registrou


def ler_ini_stdde_do_arquivo(caminho: Path) -> tuple[int, str | None]:
    """O ``ler_ini_stdde`` do arquivo (UTF-8, senão cp1252). Ausente ou ilegível: o padrão."""
    try:
        bruto = caminho.read_bytes()
    except OSError:
        return PORTA_STDDE_PADRAO, None
    try:
        texto = bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = bruto.decode("cp1252", errors="replace")
    return ler_ini_stdde(texto)


def porta_aceita(porta: int, espera_s: float = 1.0) -> bool:
    """Verdadeiro se algo aceita conexão em ``127.0.0.1:porta`` (o ``StDde`` no ar)."""
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=espera_s):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# registrar / desregistrar
# ---------------------------------------------------------------------------


def _powershell(argumentos: list[str]) -> str:
    """Roda o PowerShell e devolve a saída. Sem janela no Windows (como o ``launcher.py``)."""
    resultado = subprocess.run(
        argumentos,
        capture_output=True,
        text=True,
        check=True,
        timeout=_ESPERA_POWERSHELL_S,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return str(resultado.stdout)


def identidade_do_assembly(dll: Path, executar: Callable[[list[str]], str] = _powershell) -> str:
    """O nome completo do assembly do ``StRtd.dll``, lido pelo PowerShell.

    É o ``StRtd, Version=1.13.0.0, Culture=neutral, PublicKeyToken=cad2126db594d9d0`` que o
    RegAsm grava no ``Assembly``. Saída que não tem essa cara, ou PowerShell que falha:
    ``ValueError`` com o que veio.
    """
    caminho = _ASPAS_SIMPLES.sub(r"\1\1", str(dll))
    comando = [
        "powershell",
        "-NoProfile",
        "-Command",
        f"[System.Reflection.AssemblyName]::GetAssemblyName('{caminho}').FullName",
    ]
    try:
        saida = executar(comando).strip()
    except (OSError, subprocess.SubprocessError) as erro:
        detalhe = erro.stderr if isinstance(erro, subprocess.CalledProcessError) else None
        raise ValueError(
            f"o PowerShell não leu a identidade de {dll}: {str(detalhe or erro).strip()}"
        ) from erro
    if not _IDENTIDADE.fullmatch(saida):
        raise ValueError(f"a identidade de {dll} veio num formato inesperado: {saida!r}")
    return saida


def codebase(dll: PurePath) -> str:
    """O ``CodeBase`` como o RegAsm grava: ``file:///`` e o caminho com ``/``, sem escapar nada."""
    return f"file:///{dll.as_posix()}"


def chaves_tryd7(dll: PurePath, identidade: str) -> list[tuple[str, str, str]]:
    """O que o RegAsm grava para o ``Tryd.RtdServer``: ``(caminho sob Software\\Classes, nome,
    valor)``, com ``nome`` ``""`` para o valor padrão."""
    achado = _IDENTIDADE.fullmatch(identidade)
    if achado is None:
        raise ValueError(f"identidade do assembly sem versão: {identidade!r}")
    clsid = f"CLSID\\{CLSID_TRYD7}"
    inproc = f"{clsid}\\InprocServer32"
    base = codebase(dll)
    detalhes = (
        ("Class", CLASSE_TRYD7),
        ("Assembly", identidade),
        ("RuntimeVersion", RUNTIME_TRYD7),
        ("CodeBase", base),
    )
    return [
        (PROGID_TRYD7, "", CLASSE_TRYD7),
        (f"{PROGID_TRYD7}\\CLSID", "", CLSID_TRYD7),
        (clsid, "", CLASSE_TRYD7),
        (f"{clsid}\\ProgId", "", PROGID_TRYD7),
        (inproc, "", "mscoree.dll"),
        (inproc, "ThreadingModel", "Both"),
        *((inproc, nome, valor) for nome, valor in detalhes),
        *((f"{inproc}\\{achado['versao']}", nome, valor) for nome, valor in detalhes),
        (f"{clsid}\\Implemented Categories\\{CATEGORIA_NET}", "", ""),
    ]


def registrar(registro: Registro, dll: PurePath, identidade: str) -> list[str]:
    """Grava o ``Tryd.RtdServer`` em ``HKCU\\Software\\Classes``, nas visões de 64 e 32 bits.

    Devolve uma descrição legível de cada valor gravado.
    """
    chaves = chaves_tryd7(dll, identidade)
    descricoes: list[str] = []
    for visao in _VISOES:
        for caminho, nome, valor in chaves:
            registro.gravar("HKCU", _CLASSES + caminho, nome, valor, visao)
            descricoes.append(
                f"HKCU\\{_CLASSES}{caminho} [{visao} bits] {nome or '(padrão)'} = {valor}"
            )
    return descricoes


def desregistrar(registro: Registro) -> list[str]:
    """Apaga, em ``HKCU`` e nas duas visões, só o que o ``registrar`` grava.

    Chave ausente não é erro. Devolve a descrição de cada chave que mandou apagar.
    """
    descricoes: list[str] = []
    for visao in _VISOES:
        for caminho in (PROGID_TRYD7, f"CLSID\\{CLSID_TRYD7}"):
            registro.apagar_arvore("HKCU", _CLASSES + caminho, visao)
            descricoes.append(f"HKCU\\{_CLASSES}{caminho} [{visao} bits]")
    return descricoes

"""Camada COM da ponte — a única que fala com o pywin32 (``pythoncom``, ``win32com``).

Os imports do pywin32 ficam dentro das funções, via ``importlib``: o pacote precisa importar
no Linux, onde só o ``espiar`` e os testes rodam. Aqui moram o cliente RTD (``SessaoRtdCom``,
que faz o papel do Excel diante do servidor RTD do Tryd), ``processos_tryd``, o ``diagnostico``
e o ``autoteste`` (um servidor RTD falso, no mesmo processo e em outro).

O cliente vem do spike (``tools/tryd_spike/tryd_poc.py``), com duas diferenças: os ids dos
tópicos são os da ``Ponte`` (não um contador próprio) e as interfaces ``IRtdServer`` e
``IRTDUpdateEvent`` saem de qualquer type library que as tenha (a do Tryd, ou a do Excel).
"""

import contextlib
import importlib
import importlib.metadata
import ntpath
import platform
import re
import struct
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from options_ponte.protocolo import (
    CLSID,
    PROGID,
    TRYD_PERDIDO,
    Assinar,
    Mensagem,
    Status,
    Valor,
)
from options_ponte.servidor import Ponte

__all__ = [
    "DIRETORIO_SRC",
    "BibliotecaDeTipos",
    "ErroRtd",
    "SessaoRtdCom",
    "arquitetura_pe",
    "arquivo_do_comando",
    "autoteste",
    "bombear",
    "carregar_tipos",
    "comando_servidor_falso",
    "criar_servidor",
    "diagnostico",
    "processos_tryd",
    "servir_falso",
]

TLB_TRYD = "{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}"
TLB_EXCEL = "{00020813-0000-0000-C000-000000000046}"
# Na ordem de tentativa. A do Tryd só carrega em Python de 32 bits no Windows (o Tryd a registra
# só em win32) e não carrega no Wine; a do Excel é a do Office ou, no Wine, o shim do .idl.
_BIBLIOTECAS = (("Tryd", TLB_TRYD, 1, 0), ("Excel", TLB_EXCEL, 1, 4))
_INTERFACES = ("IRtdServer", "IRTDUpdateEvent")

CO_E_CLASSSTRING = -2147221005  # 0x800401F3: o ProgID não resolve (o Wine não lê HKCU\Classes)

# src/, de onde `python -m options_ponte` acha o pacote (o autoteste sobe um segundo processo)
DIRETORIO_SRC = Path(__file__).resolve().parents[1]

_FATIA_S = 0.01  # quanto o bombeamento dorme entre uma volta e outra
_CLSID_AUTOTESTE = "{6C1B5E0A-2F44-4B7E-9D7A-3A1F0B9C7E11}"
_VIDA_DO_SERVIDOR_FALSO_S = 2.0
_LIMITE_ENTRE_PROCESSOS_S = 10.0  # cobre os 5 s de silêncio até o Heartbeat perceber a queda
_PASSO_DO_AUTOTESTE_S = 0.05
_TOPICO_AUTOTESTE = ("PETRK300", "ULT")
_TH32CS_SNAPPROCESS = 0x2
_EXECUTAVEL_TRYD = "tryd.exe"  # o LocalServer32 do servidor RTD do Tryd


class ErroRtd(Exception):
    """Ambiente sem o que a camada COM precisa (pywin32, type library, servidor RTD)."""


@dataclass(frozen=True, slots=True)
class BibliotecaDeTipos:
    """A type library que forneceu ``IRtdServer`` e ``IRTDUpdateEvent``, e as que não serviram."""

    nome: str
    guid: str
    major: int
    minor: int
    iid_servidor: str
    iid_aviso: str
    descartadas: tuple[tuple[str, str], ...]  # (descrição, motivo) das tentadas antes desta

    @property
    def descricao(self) -> str:
        return f"{self.nome} {self.guid} {self.major}.{self.minor}"


def _importar(nome: str) -> Any:
    try:
        return importlib.import_module(nome)
    except ImportError as erro:
        raise ErroRtd(
            f"módulo {nome!r} indisponível: a camada COM da ponte roda no Python do Windows "
            f"(ou do Wine) com pywin32 instalado (pip install pywin32)"
        ) from erro


def carregar_tipos() -> BibliotecaDeTipos:
    """Carrega ``IRtdServer``/``IRTDUpdateEvent``: type library do Tryd, senão a do Excel.

    O cliente RTD precisa dessas interfaces tipadas (early binding): os parâmetros ``ByRef`` do
    ``ConnectData``/``RefreshData`` não funcionam por ``IDispatch`` puro.
    """
    gencache = _importar("win32com.client.gencache")
    universal = _importar("win32com.universal")
    descartadas: list[tuple[str, str]] = []
    for nome, guid, major, minor in _BIBLIOTECAS:
        try:
            modulo = gencache.EnsureModule(guid, 0, major, minor)
            iids = modulo.NamesToIIDMap
            faltam = [i for i in _INTERFACES if i not in iids]
            if faltam:
                raise ErroRtd(f"sem a(s) interface(s) {', '.join(faltam)}")
            universal.RegisterInterfaces(guid, 0, major, minor, list(_INTERFACES))
        except Exception as erro:  # com_error, AttributeError (módulo None), ErroRtd acima
            descartadas.append((f"{nome} {guid} {major}.{minor}", str(erro)))
            continue
        return BibliotecaDeTipos(
            nome,
            guid,
            major,
            minor,
            str(iids["IRtdServer"]),
            str(iids["IRTDUpdateEvent"]),
            tuple(descartadas),
        )
    detalhe = "; ".join(f"{descricao}: {motivo}" for descricao, motivo in descartadas)
    raise ErroRtd(
        f"nenhuma type library com IRtdServer/IRTDUpdateEvent carregou ({detalhe}). "
        f"Instale o Excel ou registre a do shim (src/options_ponte/rtd_shim.idl; no Linux, "
        f"scripts/linux/preparar_ponte_wine.sh)"
    )


@dataclass(frozen=True, slots=True)
class _ClasseRtd:
    iid: Any
    contexto: int
    pelo_progid: bool


def _resolver_classe(progid: str, clsid: str) -> _ClasseRtd:
    """O ProgID e, se ele não resolver (``CO_E_CLASSSTRING``), o CLSID com servidor local.

    No Wine o ProgID não resolve: o Tryd o registra só em ``HKCU\\Software\\Classes``. O CLSID
    funciona e leva ao ``LocalServer32`` (o próprio ``tryd.exe``, fora do processo).
    """
    pythoncom = _importar("pythoncom")
    pywintypes = _importar("pywintypes")
    try:
        iid = pywintypes.IID(progid)  # o IID também resolve ProgID (com_error se não existir)
    except pythoncom.com_error as erro:
        if erro.hresult != CO_E_CLASSSTRING:
            raise
    else:
        return _ClasseRtd(iid, pythoncom.CLSCTX_SERVER, True)
    return _ClasseRtd(pywintypes.IID(clsid), pythoncom.CLSCTX_LOCAL_SERVER, False)


def criar_servidor(progid: str = PROGID, clsid: str = CLSID) -> Any:
    """O objeto COM do servidor RTD (``IDispatch``), pelo ProgID ou, se preciso, pelo CLSID."""
    pythoncom = _importar("pythoncom")
    try:
        classe = _resolver_classe(progid, clsid)
        return pythoncom.CoCreateInstance(
            classe.iid, None, classe.contexto, pythoncom.IID_IDispatch
        )
    except pythoncom.com_error as erro:
        raise ErroRtd(
            f"não foi possível criar o servidor RTD (ProgID {progid!r}, CLSID {clsid}): {erro}. "
            f"Rode 'diagnostico' (Tryd aberto e logado? RTD ativado? "
            f"type library do Excel registrada?)"
        ) from erro


class _AvisoDeAtualizacao:
    """Callback ``IRTDUpdateEvent`` que o servidor chama quando há dado novo.

    ``_typelib_guid_`` faz o pywin32 publicar os métodos com os DISPIDs da type library: os
    mesmos que um servidor RTD real (o Tryd) usa ao chamar o callback; sem isso a chamada
    falha com "membro não encontrado".
    """

    _com_interfaces_: ClassVar[list[str]] = ["IRTDUpdateEvent"]
    _public_methods_: ClassVar[list[str]] = ["UpdateNotify", "Disconnect"]
    _public_attrs_: ClassVar[list[str]] = ["HeartbeatInterval"]

    def __init__(self, tipos: BibliotecaDeTipos) -> None:
        self._typelib_guid_ = tipos.guid
        self._typelib_version_ = (tipos.major, tipos.minor)
        self.HeartbeatInterval = 1000
        self.avisos = 0
        self.desconectado = False

    def UpdateNotify(self) -> None:
        self.avisos += 1

    def Disconnect(self) -> None:
        self.desconectado = True


class SessaoRtdCom:
    """``SessaoRtd`` sobre o servidor RTD (o do Tryd) via COM: faz o papel do Excel.

    Vive na thread principal (STA): os avisos ``UpdateNotify`` chegam pelo bombeamento de
    mensagens (``bombear``) nessa mesma thread. ``servidor`` (só para o autoteste) é um objeto
    COM já pronto, no lugar do que ``criar_servidor`` cria.
    """

    def __init__(
        self, progid: str = PROGID, clsid: str = CLSID, *, servidor: object | None = None
    ) -> None:
        classes = _importar("win32com.client.CLSIDToClass")
        util = _importar("win32com.server.util")
        tipos = carregar_tipos()
        bruto = servidor if servidor is not None else criar_servidor(progid, clsid)
        classe = classes.GetClass(tipos.iid_servidor)
        self._servidor = classe(getattr(bruto, "_oleobj_", bruto))
        self._aviso = _AvisoDeAtualizacao(tipos)
        self._ids: set[int] = set()
        status = self._servidor.ServerStart(util.wrap(self._aviso))
        if not status or status < 0:
            raise ErroRtd(f"ServerStart devolveu {status!r}: o servidor RTD recusou o cliente")

    def conectar(self, id_: int, strings: tuple[str, str]) -> object:
        resultado = self._servidor.ConnectData(id_, strings, True)
        self._ids.add(id_)
        return resultado[0] if isinstance(resultado, tuple) else resultado

    def desconectar(self, id_: int) -> None:
        self._servidor.DisconnectData(id_)
        self._ids.discard(id_)

    def atualizar(self) -> list[tuple[int, object]]:
        resultado = self._servidor.RefreshData(0)
        # ByRef: (array, TopicCount); o array é ((ids...), (valores...))
        com_contagem = (
            isinstance(resultado, tuple) and len(resultado) == 2 and isinstance(resultado[1], int)
        )
        dados = resultado[0] if com_contagem else resultado
        if not dados:
            return []
        ids, valores = dados[0], dados[1]
        if ids is None or valores is None:
            return []
        return [(int(i), v) for i, v in zip(ids, valores, strict=False)]

    def vivo(self) -> bool:
        """Heartbeat, como o Excel faz quando o servidor fica em silêncio.

        Sem isso, um servidor que morre só para de mandar UpdateNotify e a ponte seguiria com
        os últimos valores congelados, sem erro nenhum. O ``Disconnect`` do servidor também
        conta como queda.
        """
        if self._aviso.desconectado:
            return False
        pythoncom = _importar("pythoncom")
        try:
            return int(self._servidor.Heartbeat()) > 0
        except pythoncom.com_error:
            return False

    def avisos(self) -> int:
        return int(self._aviso.avisos)

    def encerrar(self) -> None:
        for id_ in sorted(self._ids):
            with contextlib.suppress(Exception):
                self._servidor.DisconnectData(id_)
        self._ids.clear()
        with contextlib.suppress(Exception):
            self._servidor.ServerTerminate()


def bombear(
    passo_s: float,
    *,
    relogio: Callable[[], float] = time.monotonic,
    dormir: Callable[[float], None] = time.sleep,
) -> None:
    """Entrega as mensagens COM pendentes (os ``UpdateNotify``) por ``passo_s`` segundos.

    Dorme entre as voltas: o laço da ponte não pode girar sem esperar.
    """
    pythoncom = _importar("pythoncom")
    fim = relogio() + passo_s
    while True:
        pythoncom.PumpWaitingMessages()
        restante = fim - relogio()
        if not (restante > 0):
            return
        dormir(min(restante, _FATIA_S))


def processos_tryd() -> frozenset[int]:
    """PIDs dos ``tryd.exe`` rodando (Toolhelp32: Windows e Wine). Fora do Windows, vazio."""
    if sys.platform != "win32":
        return frozenset()
    import ctypes
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
            if ntpath.basename(entrada.szExeFile).lower() == _EXECUTAVEL_TRYD:
                pids.add(int(entrada.th32ProcessID))
            if not proximo(foto, ctypes.byref(entrada)):
                return frozenset(pids)
    finally:
        kernel32.CloseHandle(foto)


# ---------------------------------------------------------------------------
# Diagnóstico (só leitura)
# ---------------------------------------------------------------------------


def arquitetura_pe(caminho: Path) -> str:
    """32 ou 64 bits de um executável/DLL, pelo cabeçalho PE."""
    with caminho.open("rb") as arquivo:
        cabecalho = arquivo.read(4096)
    try:
        deslocamento = struct.unpack_from("<I", cabecalho, 0x3C)[0]
        if cabecalho[:2] != b"MZ" or cabecalho[deslocamento : deslocamento + 4] != b"PE\0\0":
            return "formato não reconhecido"
        maquina = struct.unpack_from("<H", cabecalho, deslocamento + 4)[0]
    except struct.error:
        return "formato não reconhecido"
    return {0x14C: "32 bits (x86)", 0x8664: "64 bits (x64)", 0xAA64: "ARM64"}.get(
        maquina, hex(maquina)
    )


def arquivo_do_comando(comando: str) -> str:
    """O executável/DLL de um valor InprocServer32/LocalServer32.

    O valor pode vir com aspas ou sem, com argumentos (``EXCEL.EXE /automation``) e com
    variáveis de ambiente (``%SystemRoot%``).
    """
    texto = ntpath.expandvars(comando.strip())
    if texto.startswith('"'):
        return texto[1:].split('"', 1)[0]
    achado = re.search(r"\.(exe|dll)\b", texto, re.IGNORECASE)
    return texto[: achado.end()] if achado else texto


def _ler_padrao(winreg: Any, raiz: Any, subchave: str, visao: int) -> str | None:
    try:
        with winreg.OpenKey(raiz, subchave, 0, winreg.KEY_READ | visao) as chave:
            return str(winreg.QueryValueEx(chave, "")[0])
    except OSError:
        return None


def _servidores_registrados(clsid: str) -> list[tuple[str, str, str]]:
    """``(servidor, comando, onde)`` de cada LocalServer32/InprocServer32 do CLSID no registro."""
    winreg = _importar("winreg")
    raizes = (
        ("HKCR", winreg.HKEY_CLASSES_ROOT, ""),
        ("HKCU\\Software\\Classes", winreg.HKEY_CURRENT_USER, "Software\\Classes\\"),
        ("HKLM\\Software\\Classes", winreg.HKEY_LOCAL_MACHINE, "Software\\Classes\\"),
    )
    visoes = (("visão 64 bits", winreg.KEY_WOW64_64KEY), ("visão 32 bits", winreg.KEY_WOW64_32KEY))
    achados: dict[tuple[str, str], str] = {}
    for servidor in ("LocalServer32", "InprocServer32"):
        for rotulo, raiz, prefixo in raizes:
            for nome_visao, visao in visoes:
                comando = _ler_padrao(winreg, raiz, f"{prefixo}CLSID\\{clsid}\\{servidor}", visao)
                if comando is not None:
                    achados.setdefault((servidor, comando), f"{rotulo}, {nome_visao}")
    return [(servidor, comando, onde) for (servidor, comando), onde in achados.items()]


def _versao_pywin32() -> str:
    try:
        return importlib.metadata.version("pywin32")
    except importlib.metadata.PackageNotFoundError:
        return "(versão desconhecida)"


def _diagnosticar_classe() -> int:
    """Imprime como a classe do servidor RTD é achada e onde fica o servidor. Devolve as faltas."""
    pythoncom = _importar("pythoncom")
    try:
        classe = _resolver_classe(PROGID, CLSID)
    except pythoncom.com_error as erro:
        print(f"[falta] ProgID {PROGID!r} não resolve: {erro}")
        return 1
    if classe.pelo_progid:
        print(f"[ok] ProgID {PROGID!r} -> CLSID {classe.iid}")
    else:
        print(
            f"[aviso] ProgID {PROGID!r} não resolve pelo nome (CO_E_CLASSSTRING, 0x800401F3; "
            f"provável causa: o Tryd o registra só em HKCU\\Software\\Classes e o Wine não o "
            f"enxerga). A ponte cria pelo CLSID {CLSID} com CLSCTX_LOCAL_SERVER"
        )
    servidores = _servidores_registrados(CLSID)
    if not servidores:
        print(f"[falta] CLSID {CLSID} sem LocalServer32 nem InprocServer32 no registro")
        return 1
    for servidor, comando, onde in servidores:
        arquivo = Path(arquivo_do_comando(comando))
        arquitetura = arquitetura_pe(arquivo) if arquivo.exists() else "arquivo ausente"
        print(f"[ok] {servidor} = {comando} [{arquitetura}] ({onde})")
    print(
        "     InprocServer32 (DLL) só carrega num processo de MESMA arquitetura que o Python; "
        "LocalServer32 (EXE) não tem essa restrição"
    )
    return 0


def _diagnosticar_tipos() -> int:
    try:
        tipos = carregar_tipos()
    except ErroRtd as erro:
        print(f"[falta] {erro}")
        return 1
    for descricao, motivo in tipos.descartadas:
        print(f"[aviso] type library {descricao} não serviu: {motivo}")
    print(
        f"[ok] type library em uso: {tipos.descricao} "
        f"(IRtdServer {tipos.iid_servidor}, IRTDUpdateEvent {tipos.iid_aviso})"
    )
    return 0


def _diagnosticar_processo() -> None:
    try:
        pids = processos_tryd()
    except OSError as erro:
        print(f"[aviso] não foi possível listar os processos: {erro}")
        return
    if pids:
        print(f"[ok] Tryd rodando (tryd.exe, PID {', '.join(map(str, sorted(pids)))})")
    else:
        print("[falta] Tryd fechado (nenhum tryd.exe): a ponte espera o usuário abri-lo")


def diagnostico() -> int:
    """Só lê o ambiente (registro, type libraries, processos); não cria o servidor RTD."""
    bits = struct.calcsize("P") * 8
    print(f"Python {platform.python_version()} {bits} bits em {platform.platform()}")
    _importar("pythoncom")
    print(f"[ok] pywin32 {_versao_pywin32()}")
    faltas = _diagnosticar_classe() + _diagnosticar_tipos()
    _diagnosticar_processo()
    return 1 if faltas else 0


# ---------------------------------------------------------------------------
# Autoteste: servidor RTD falso no mesmo processo e em outro
# ---------------------------------------------------------------------------


class _ServidorFalso:
    """IRtdServer em Python, no molde do exemplo do pywin32 (excelRTDServer.py)."""

    _com_interfaces_: ClassVar[list[str]] = ["IRtdServer"]
    _public_methods_: ClassVar[list[str]] = [
        "ConnectData",
        "DisconnectData",
        "Heartbeat",
        "RefreshData",
        "ServerStart",
        "ServerTerminate",
    ]
    _BOOK: ClassVar[dict[str, float | int]] = {
        "ULT": 1.23,
        "OCP": 1.22,
        "OVD": 1.24,
        "NEG": 37,
        "VOL": 3700,
    }

    def __init__(self, tipos: BibliotecaDeTipos) -> None:
        self._typelib_guid_ = tipos.guid
        self._typelib_version_ = (tipos.major, tipos.minor)
        self._iid_aviso = tipos.iid_aviso
        self.topicos: dict[int, tuple[str, ...]] = {}
        self.mudados: set[int] = set()
        self.callback: Any = None
        self.tique = 0

    def ServerStart(self, callback: Any) -> int:
        classes = _importar("win32com.client.CLSIDToClass")
        self.callback = classes.GetClass(self._iid_aviso)(callback)
        return 1

    def ConnectData(
        self, topico: int, strings: Any, novos: bool
    ) -> tuple[Any, tuple[str, ...], bool]:
        # Strings e GetNewValues são ByRef na type library: o pywin32 espera os dois
        # de volta depois do valor, nessa ordem.
        self.topicos[topico] = tuple(strings)
        return self._valor(tuple(strings)), tuple(strings), True

    def DisconnectData(self, topico: int) -> None:
        self.topicos.pop(topico, None)

    def Heartbeat(self) -> int:
        return 1

    def RefreshData(self, _contagem: int) -> tuple[tuple[tuple[Any, ...], tuple[Any, ...]], int]:
        ids = tuple(sorted(self.mudados))
        self.mudados.clear()
        valores = tuple(self._valor(self.topicos[i]) for i in ids)
        return (ids, valores), len(ids)

    def ServerTerminate(self) -> None:
        self.callback = None

    def _valor(self, strings: tuple[str, ...]) -> Any:
        ativo, campo = strings
        base = self._BOOK.get(campo, f"{ativo}.{campo}")
        return base + self.tique * 0.01 if isinstance(base, float) else base

    def publicar(self) -> None:
        """Simula um negócio: muda o último preço e avisa o cliente."""
        self.tique += 1
        self.mudados.update(t for t, s in self.topicos.items() if s[-1] == "ULT")
        self.callback.UpdateNotify()


def comando_servidor_falso(executavel: str, segundos: float) -> list[str]:
    """O comando que sobe o servidor falso noutro processo (``python -m options_ponte ...``)."""
    return [executavel, "-m", "options_ponte", "servidor-falso", "--segundos", f"{segundos:g}"]


def servir_falso(segundos: float) -> int:
    """Servidor falso noutro processo, como o Tryd: um negócio a cada 0,5 s, depois sai.

    Publica-se na tabela de objetos ativos do COM: nada é gravado no registro.
    """
    pythoncom = _importar("pythoncom")
    util = _importar("win32com.server.util")
    falso = _ServidorFalso(carregar_tipos())
    registro = pythoncom.RegisterActiveObject(util.wrap(falso), _CLSID_AUTOTESTE, 0)
    print("pronto", flush=True)
    agora = time.monotonic()
    fim, proximo = agora + segundos, agora + 0.5
    while time.monotonic() < fim:
        pythoncom.PumpWaitingMessages()
        if falso.callback is not None and falso.topicos and time.monotonic() >= proximo:
            falso.publicar()
            proximo += 0.5
        time.sleep(0.01)
    pythoncom.RevokeActiveObject(registro)
    return 0


def _autoteste_no_processo(tipos: BibliotecaDeTipos) -> bool:
    util = _importar("win32com.server.util")
    falso = _ServidorFalso(tipos)
    sessao = SessaoRtdCom(servidor=util.wrap(falso))
    inicial = sessao.conectar(1, ("PETRK300_B_0", "ULT"))
    sessao.conectar(2, ("PETRK300_B_0", "OCP"))
    falso.publicar()
    bombear(0.1)
    avisos = sessao.avisos()
    mudancas = sessao.atualizar()
    vivo = sessao.vivo()
    falso.callback.Disconnect()  # o servidor avisa que vai embora
    bombear(0.1)
    vivo_depois_do_disconnect = sessao.vivo()
    sessao.encerrar()
    print(f"valor inicial de ULT: {inicial!r}")
    print(f"avisos UpdateNotify recebidos: {avisos}")
    print(f"RefreshData: {mudancas!r}")
    print(f"Heartbeat: {vivo}; depois do Disconnect do servidor: {vivo_depois_do_disconnect}")
    return (
        isinstance(inicial, float)
        and abs(inicial - 1.23) < 1e-9
        and avisos == 1
        and len(mudancas) == 1
        and mudancas[0][0] == 1
        and isinstance(mudancas[0][1], float)
        and abs(mudancas[0][1] - 1.24) < 1e-9
        and vivo
        and not vivo_depois_do_disconnect
    )


def _autoteste_entre_processos() -> bool:
    """A ``Ponte`` e a ``SessaoRtdCom`` aqui; o servidor noutro processo, que morre no meio."""
    pythoncom = _importar("pythoncom")
    servidor = subprocess.Popen(
        comando_servidor_falso(sys.executable, _VIDA_DO_SERVIDOR_FALSO_S),
        cwd=DIRETORIO_SRC,
        stdout=subprocess.PIPE,
        text=True,
    )
    inicio = time.monotonic()
    try:
        assert servidor.stdout is not None
        pronto = servidor.stdout.readline().strip()  # "pronto", ou vazio se o servidor falhou
        if pronto != "pronto":
            print("entre processos: o servidor falso não subiu")
            return False
        bruto = pythoncom.GetActiveObject(_CLSID_AUTOTESTE)
        sessao = SessaoRtdCom(servidor=bruto.QueryInterface(pythoncom.IID_IDispatch))
        ponte = Ponte(lambda: sessao, time.monotonic, lambda: "autoteste", limite=10)
        recebidas: list[Mensagem] = ponte.tratar(Assinar((_TOPICO_AUTOTESTE,)))
        perdido: Status | None = None
        while perdido is None and time.monotonic() - inicio < _LIMITE_ENTRE_PROCESSOS_S:
            bombear(_PASSO_DO_AUTOTESTE_S)
            for mensagem in ponte.ciclo():
                recebidas.append(mensagem)
                if isinstance(mensagem, Status) and mensagem.tryd == TRYD_PERDIDO:
                    perdido = perdido or mensagem
        ponte.encerrar()
    finally:
        with contextlib.suppress(subprocess.TimeoutExpired):
            servidor.wait(timeout=15)
        if servidor.poll() is None:
            servidor.kill()
    duracao = time.monotonic() - inicio
    valores = [m.valor for m in recebidas if isinstance(m, Valor)]
    print(
        f"entre processos: {len(valores)} valor(es) de ULT {valores}; servidor perdido "
        f"detectado em {duracao:.1f} s: {perdido.motivo if perdido else 'NÃO'}"
    )
    return len(valores) >= 3 and perdido is not None and duracao < _LIMITE_ENTRE_PROCESSOS_S


def autoteste() -> int:
    """Cliente RTD contra um servidor RTD FALSO, sem Tryd e sem gravar no registro.

    No mesmo processo: valida o encanamento COM (ServerStart, ConnectData, UpdateNotify,
    RefreshData, parâmetros ByRef, Heartbeat). Noutro processo: o marshaling entre processos
    e a detecção de servidor perdido pela ``Ponte``.
    """
    tipos = carregar_tipos()
    print(f"type library em uso: {tipos.descricao}")
    ok_no_processo = False
    ok_entre_processos = False
    try:
        ok_no_processo = _autoteste_no_processo(tipos)
        ok_entre_processos = _autoteste_entre_processos()
    except Exception as erro:  # o autoteste reporta a falha em vez de morrer com traceback
        print(f"autoteste interrompido: {type(erro).__name__}: {erro}")
    ok = ok_no_processo and ok_entre_processos
    print("AUTOTESTE OK" if ok else "AUTOTESTE FALHOU")
    return 0 if ok else 1

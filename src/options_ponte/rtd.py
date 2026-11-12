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
import platform
import struct
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Final, TextIO

from options_ponte import tryd7, vias
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
from options_ponte.tryd7 import pids_do_executavel
from options_ponte.vias import (
    CLSID_TRYD7,
    VIA_TRYD7,
    VIA_TRYD8,
    VISAO_DO_PROCESSO,
    Registro,
    Via,
    Visao,
    arquivo_do_comando,
    dono_do_rtdtrading,
    valor_da_classe,
)

__all__ = [
    "DIRETORIO_SRC",
    "IID_IRTDSERVER_EXCEL",
    "IID_IRTDUPDATEEVENT_EXCEL",
    "MOTIVO_STDDE_FECHADO",
    "MOTIVO_STDDE_PORTA",
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
    "diagnosticar_vias",
    "diagnostico",
    "processos_tryd",
    "servir_falso",
    "verificar_stdde",
]

TLB_RTDTRADING = "{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}"  # a do RTDTrading (Tryd 8 e Profit)
TLB_EXCEL = "{00020813-0000-0000-C000-000000000046}"
# Na ordem de tentativa. A do RTDTrading só carrega em Python de 32 bits no Windows (o Tryd a
# registra só em win32) e não carrega no Wine; a do Excel é a do Office ou, no Wine, o shim do .idl.
_BIBLIOTECAS = (("RTDTrading", TLB_RTDTRADING, 1, 0), ("Excel", TLB_EXCEL, 1, 4))
_INTERFACES = ("IRtdServer", "IRTDUpdateEvent")
# A preferida é a biblioteca com os IIDs do Excel: são os que o StRtd do Tryd 7 e o tryd.exe
# implementam. Uma de IIDs diferentes só serve se nenhuma outra carregar (``aviso``).
IID_IRTDSERVER_EXCEL: Final = "{EC0E6191-DB51-11D3-8F3E-00C04F3651B8}"
IID_IRTDUPDATEEVENT_EXCEL: Final = "{A43788C1-D91B-11D3-8F39-00C04F3651B8}"
_MOTIVO_IIDS_DIFERENTES: Final = (
    "IIDs diferentes dos do Excel (o StRtd do Tryd 7 e o tryd.exe usam os do Excel)"
)

MOTIVO_STDDE_FECHADO: Final = "o StDde.exe do Tryd não está rodando: ative o DDE/RTD no Tryd"
MOTIVO_STDDE_PORTA: Final = "a porta {porta} do StDde do Tryd não responde"

CO_E_CLASSSTRING = -2147221005  # 0x800401F3: o ProgID não resolve (o Wine não lê HKCU\Classes)

# src/, de onde `python -m options_ponte` acha o pacote (o autoteste sobe um segundo processo)
DIRETORIO_SRC = Path(__file__).resolve().parents[1]

_FATIA_S = 0.01  # quanto o bombeamento dorme entre uma volta e outra
_CLSID_AUTOTESTE = "{6C1B5E0A-2F44-4B7E-9D7A-3A1F0B9C7E11}"
_VIDA_DO_SERVIDOR_FALSO_S = 2.0
_LIMITE_ENTRE_PROCESSOS_S = 10.0  # cobre os 5 s de silêncio até o Heartbeat perceber a queda
_PASSO_DO_AUTOTESTE_S = 0.05
_TOPICO_AUTOTESTE = ("PETRK300", "ULT")
_EXECUTAVEL_TRYD = "tryd.exe"  # o LocalServer32 do servidor RTD do Tryd
_EXECUTAVEL_STDDE = "StDde.exe"  # o Tryd 7 só serve o RTD com ele no ar
_VISOES: Final[tuple[Visao, ...]] = (64, 32)
_DETALHES_TRYD7 = ("Class", "Assembly", "RuntimeVersion", "CodeBase")  # o que o RegAsm grava
_PREFIXO_CODEBASE = "file:///"
_DOTNET35 = "SOFTWARE\\Microsoft\\NET Framework Setup\\NDP\\v3.5"


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
    descartadas: tuple[tuple[str, str], ...]  # (descrição, motivo) das tentadas que não serviram
    aviso: str | None = None  # com IIDs diferentes dos do Excel: usada por falta de outra

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
    """Carrega ``IRtdServer``/``IRTDUpdateEvent``: type library do RTDTrading, senão a do Excel.

    O cliente RTD precisa dessas interfaces tipadas (early binding): os parâmetros ``ByRef`` do
    ``ConnectData``/``RefreshData`` não funcionam por ``IDispatch`` puro. Vale a primeira, na ordem
    de tentativa, com os IIDs do Excel; sem nenhuma, a primeira que carregou (com ``aviso``). Só a
    escolhida é registrada.
    """
    gencache = _importar("win32com.client.gencache")
    universal = _importar("win32com.universal")
    descartadas: list[tuple[str, str]] = []
    reserva: tuple[str, str, int, int, Any] | None = None  # a 1ª que carregou com IIDs de outro
    for nome, guid, major, minor in _BIBLIOTECAS:
        try:
            modulo = gencache.EnsureModule(guid, 0, major, minor)
            iids = modulo.NamesToIIDMap
            faltam = [i for i in _INTERFACES if i not in iids]
            if faltam:
                raise ErroRtd(f"sem a(s) interface(s) {', '.join(faltam)}")
            if (
                str(iids["IRtdServer"]).upper() != IID_IRTDSERVER_EXCEL
                or str(iids["IRTDUpdateEvent"]).upper() != IID_IRTDUPDATEEVENT_EXCEL
            ):
                reserva = reserva or (nome, guid, major, minor, iids)
                raise ErroRtd(_MOTIVO_IIDS_DIFERENTES)
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
    if reserva is not None:
        nome, guid, major, minor, iids = reserva
        descricao = f"{nome} {guid} {major}.{minor}"
        # a escolhida deixa de ser descartada
        descartadas.remove((descricao, _MOTIVO_IIDS_DIFERENTES))
        try:
            universal.RegisterInterfaces(guid, 0, major, minor, list(_INTERFACES))
        except Exception as erro:
            descartadas.append((descricao, str(erro)))
        else:
            return BibliotecaDeTipos(
                nome,
                guid,
                major,
                minor,
                str(iids["IRtdServer"]),
                str(iids["IRTDUpdateEvent"]),
                tuple(descartadas),
                _MOTIVO_IIDS_DIFERENTES,
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


def criar_servidor(via: Via = VIA_TRYD8) -> Any:
    """O objeto COM do servidor RTD (``IDispatch``) da via.

    Tryd 8 (fora do processo): pelo ProgID ou, se preciso, pelo CLSID. Tryd 7 (dentro do
    processo): direto pelo CLSID, com ``CLSCTX_INPROC_SERVER``, sem passar pelo ProgID: o
    ``mscoree`` carrega o CLR v2 aqui dentro. Dele se pede o ``IRtdServer`` pelo IID do Excel
    (como o Excel faz): o ``IDispatch`` padrão de um servidor .NET pode ser o da interface de
    classe, com DISPIDs do CLR. Se o ``QueryInterface`` falhar, vale o ``IDispatch`` cru.
    """
    pythoncom = _importar("pythoncom")
    try:
        if via.dentro_do_processo:
            pywintypes = _importar("pywintypes")
            bruto = pythoncom.CoCreateInstance(
                pywintypes.IID(via.clsid),
                None,
                pythoncom.CLSCTX_INPROC_SERVER,
                pythoncom.IID_IDispatch,
            )
            try:
                return bruto.QueryInterface(
                    pywintypes.IID(IID_IRTDSERVER_EXCEL), pythoncom.IID_IDispatch
                )
            except pythoncom.com_error:
                return bruto
        classe = _resolver_classe(via.progid, via.clsid)
        return pythoncom.CoCreateInstance(
            classe.iid, None, classe.contexto, pythoncom.IID_IDispatch
        )
    except pythoncom.com_error as erro:
        if via.dentro_do_processo:
            raise ErroRtd(
                f"não foi possível criar o servidor RTD ({via.nome}, CLSID {via.clsid}): {erro}. "
                f"Rode 'diagnostico' (Tryd.RtdServer registrado? .NET 3.5 instalado?)"
            ) from erro
        raise ErroRtd(
            f"não foi possível criar o servidor RTD (ProgID {via.progid!r}, CLSID {via.clsid}): "
            f"{erro}. Rode 'diagnostico' (Tryd aberto e logado? RTD ativado? "
            f"type library do Excel registrada?)"
        ) from erro


def verificar_stdde(
    caminhos: Callable[[str], list[Path]] = tryd7.caminhos_em_execucao,
    ler_ini: Callable[[Path], tuple[int, str | None]] = tryd7.ler_ini_stdde_do_arquivo,
    aceita: Callable[[int], bool] = tryd7.porta_aceita,
) -> None:
    """Confere o que o servidor RTD do Tryd 7 precisa antes de ser criado: o ``StDde.exe``
    rodando e a porta dele (a do ``StDde.ini``, ``12002`` se não achar) aceitando conexão.

    Levanta ``ErroRtd`` com o motivo. A pasta do Tryd, onde está o INI, vem do ``tryd.exe`` em
    execução; sem ela, vale a porta padrão.
    """
    if not caminhos(_EXECUTAVEL_STDDE):
        raise ErroRtd(MOTIVO_STDDE_FECHADO)
    pasta = tryd7.pasta_do_tryd(caminhos)
    porta = (
        ler_ini(pasta / tryd7.INI_RELATIVO)[0] if pasta is not None else tryd7.PORTA_STDDE_PADRAO
    )
    if not aceita(porta):
        raise ErroRtd(MOTIVO_STDDE_PORTA.format(porta=porta))


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


def _escolher_via() -> Via:
    """A via que serve nesta máquina, pelo registro, ou ``ErroRtd`` com o motivo de nenhuma."""
    via = vias.escolher_via(tryd7.RegistroWinreg())
    if isinstance(via, str):
        raise ErroRtd(via)
    return via


class SessaoRtdCom:
    """``SessaoRtd`` sobre o servidor RTD (o do Tryd) via COM: faz o papel do Excel.

    Vive na thread principal (STA): os avisos ``UpdateNotify`` chegam pelo bombeamento de
    mensagens (``bombear``) nessa mesma thread. A ``via`` diz qual servidor criar e o formato do
    tópico; sem ela, a sessão escolhe pelo registro a cada abertura (Tryd 8 ou Tryd 7). ``servidor``
    (só para o autoteste) é um objeto COM já pronto, no lugar do que ``criar_servidor`` cria; com
    ele e sem ``via``, vale a do Tryd 8.
    """

    def __init__(self, via: Via | None = None, *, servidor: object | None = None) -> None:
        tipos = carregar_tipos()  # primeiro: a falha da type library é o motivo que o app vê
        classes = _importar("win32com.client.CLSIDToClass")
        util = _importar("win32com.server.util")
        if via is None:
            via = VIA_TRYD8 if servidor is not None else _escolher_via()
        if servidor is None:
            if via is VIA_TRYD7:
                verificar_stdde()
            bruto = criar_servidor(via)
        else:
            bruto = servidor
        self._via = via
        classe = classes.GetClass(tipos.iid_servidor)
        self._servidor = classe(getattr(bruto, "_oleobj_", bruto))
        self._aviso = _AvisoDeAtualizacao(tipos)
        self._ids: set[int] = set()
        status = self._servidor.ServerStart(util.wrap(self._aviso))
        if not status or status < 0:
            raise ErroRtd(f"ServerStart devolveu {status!r}: o servidor RTD recusou o cliente")

    def topico(self, ticker: str, campo: str) -> tuple[str, ...]:
        return self._via.topico(ticker, campo)

    def conectar(self, id_: int, strings: tuple[str, ...]) -> object:
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
    return pids_do_executavel(_EXECUTAVEL_TRYD)


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
    if tipos.aviso is not None:
        print(f"[aviso] type library {tipos.descricao} usada por falta de outra: {tipos.aviso}")
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


def _diagnosticar_dono(registro: Registro, visao: Visao, saida: TextIO) -> None:
    """Quem atende o ``RTDTrading``: o ``tryd.exe`` (Tryd 8) ou o ``profitchart.exe`` (Profit)."""
    dono = dono_do_rtdtrading(registro, visao)
    if dono is None:
        print("[info] RTDTrading.RtdServer não registrado", file=saida)
    elif dono == _EXECUTAVEL_TRYD:
        print("[ok] RTDTrading.RtdServer -> tryd.exe (Tryd 8)", file=saida)
    elif dono == "profitchart.exe":
        print(
            "[aviso] RTDTrading.RtdServer aponta para o profitchart.exe: "
            "isso é o RTD do Profit, não do Tryd",
            file=saida,
        )
    else:
        print(
            f"[aviso] RTDTrading.RtdServer aponta para {dono}, que não é o tryd.exe (Tryd 8)",
            file=saida,
        )


def _diagnosticar_tryd7(
    registro: Registro, visao: Visao, arquivo_existe: Callable[[Path], bool], saida: TextIO
) -> int:
    """O ``Tryd.RtdServer`` numa visão do registro e o ``CodeBase`` dele. Devolve as faltas."""
    if not vias.tryd7_registrado(registro, visao):
        print(f"[falta] Tryd.RtdServer não registrado na visão de {visao} bits", file=saida)
        return 1
    inproc = f"CLSID\\{CLSID_TRYD7}\\InprocServer32"
    valores = {nome: valor_da_classe(registro, inproc, nome, visao) for nome in _DETALHES_TRYD7}
    detalhes = ", ".join(f"{nome} {valor or '(ausente)'}" for nome, valor in valores.items())
    print(f"[ok] Tryd.RtdServer na visão de {visao} bits: mscoree.dll, {detalhes}", file=saida)
    codebase = valores["CodeBase"]
    if codebase is None:
        print("[falta] sem CodeBase: o registro não diz onde está o StRtd.dll", file=saida)
        return 1
    if codebase.lower().startswith(_PREFIXO_CODEBASE):
        codebase = codebase[len(_PREFIXO_CODEBASE) :]
    caminho = Path(codebase)
    if arquivo_existe(caminho):
        print("[ok] StRtd.dll existe", file=saida)
        return 0
    print(f"[falta] o CodeBase aponta para um arquivo que não existe: {caminho}", file=saida)
    return 1


def _diagnosticar_dotnet(registro: Registro, saida: TextIO) -> int:
    """O .NET 3.5 (CLR v2), que o ``Tryd.RtdServer`` precisa no ``mscoree``. Devolve as faltas."""
    if registro.ler("HKLM", _DOTNET35, "Install", 64) == "1":
        print("[ok] .NET 3.5 (CLR v2) instalado", file=saida)
        return 0
    print(
        "[falta] .NET 3.5 (CLR v2) não instalado: "
        'ative em "Ativar ou desativar recursos do Windows"',
        file=saida,
    )
    return 1


def _diagnosticar_stdde(
    caminhos: Callable[[str], list[Path]],
    aceita: Callable[[int], bool],
    ler_ini: Callable[[Path], tuple[int, str | None]],
    saida: TextIO,
) -> int:
    """O ``StDde.exe``, a porta dele e o ``REGISTROU`` do ``StDde.ini``. Devolve as faltas."""
    try:
        stdde_roda = bool(caminhos(_EXECUTAVEL_STDDE))
        pasta = tryd7.pasta_do_tryd(caminhos)
    except OSError as erro:
        print(f"[aviso] não foi possível listar os processos: {erro}", file=saida)
        return 1
    faltas = 0
    if stdde_roda:
        print("[ok] StDde.exe rodando", file=saida)
    else:
        print("[falta] StDde.exe não está rodando (ative o DDE/RTD no Tryd)", file=saida)
        faltas += 1
    porta, registrou = (
        ler_ini(pasta / tryd7.INI_RELATIVO)
        if pasta is not None
        else (tryd7.PORTA_STDDE_PADRAO, None)
    )
    if aceita(porta):
        print(f"[ok] porta {porta} do StDde respondendo", file=saida)
    else:
        print(f"[falta] porta {porta} do StDde não responde", file=saida)
        faltas += 1
    if registrou is None:
        sem_pasta = "" if pasta is not None else " (Tryd fechado: sem a pasta do INI)"
        print(f"[info] StDde.ini: REGISTROU não encontrado{sem_pasta}", file=saida)
    else:
        dica = (
            " (o StDde não se registra sem administrador; o 'PonteTryd.exe registrar' resolve)"
            if registrou.lower() == "false"
            else ""
        )
        print(f"[info] StDde.ini: REGISTROU={registrou}{dica}", file=saida)
    return faltas


def diagnosticar_vias(
    registro: Registro,
    visao: Visao,
    *,
    caminhos: Callable[[str], list[Path]],
    aceita: Callable[[int], bool],
    ler_ini: Callable[[Path], tuple[int, str | None]],
    arquivo_existe: Callable[[Path], bool],
    saida: TextIO,
) -> int:
    """Mostra as duas vias RTD (RTDTrading e Tryd.RtdServer) e a que a ponte vai usar.

    Só lê: registro, processos, porta e arquivos entram pelos parâmetros e o COM não é chamado.
    ``visao`` é a do processo. Devolve as faltas que impedem a via escolhida: "nenhuma via" e,
    com a via do Tryd 7, o que falta na visão do processo, o .NET 3.5 e o StDde. As demais linhas
    ``[falta]`` aparecem, mas não contam: um Tryd 8 que funciona não precisa do que é do Tryd 7.
    """
    _diagnosticar_dono(registro, visao, saida)
    faltas_do_tryd7 = 0
    for visao_do_tryd7 in _VISOES:
        faltas = _diagnosticar_tryd7(registro, visao_do_tryd7, arquivo_existe, saida)
        if visao_do_tryd7 == visao:
            faltas_do_tryd7 += faltas
    faltas_do_tryd7 += _diagnosticar_dotnet(registro, saida)
    faltas_do_tryd7 += _diagnosticar_stdde(caminhos, aceita, ler_ini, saida)
    via = vias.escolher_via(registro, visao)
    if isinstance(via, str):
        print(f"[falta] nenhuma via: {via}", file=saida)
        return 1
    print(f"[ok] a ponte vai usar: {via.nome}", file=saida)
    return faltas_do_tryd7 if via is VIA_TRYD7 else 0


def diagnostico() -> int:
    """Só lê o ambiente (registro, type libraries, processos); não cria o servidor RTD."""
    bits = struct.calcsize("P") * 8
    print(f"Python {platform.python_version()} {bits} bits em {platform.platform()}")
    _importar("pythoncom")
    print(f"[ok] pywin32 {_versao_pywin32()}")
    registro = tryd7.RegistroWinreg()
    faltas_da_classe = _diagnosticar_classe()
    faltas = _diagnosticar_tipos()
    if vias.escolher_via(registro) is not VIA_TRYD7:  # a classe do RTDTrading só importa sem ela
        faltas += faltas_da_classe
    _diagnosticar_processo()
    faltas += diagnosticar_vias(
        registro,
        VISAO_DO_PROCESSO,
        caminhos=tryd7.caminhos_em_execucao,
        aceita=tryd7.porta_aceita,
        ler_ini=tryd7.ler_ini_stdde_do_arquivo,
        arquivo_existe=Path.exists,
        saida=sys.stdout,
    )
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
        ativo, campo = strings[-2:]  # ("PETR4_B_0", "ULT") no Tryd 8, ("COT", "PETR4", "ULT") no 7
        base = self._BOOK.get(campo, f"{ativo}.{campo}")
        return base + self.tique * 0.01 if isinstance(base, float) else base

    def publicar(self) -> None:
        """Simula um negócio: muda o último preço e avisa o cliente."""
        self.tique += 1
        self.mudados.update(t for t, s in self.topicos.items() if s[-1] == "ULT")
        self.callback.UpdateNotify()


def comando_servidor_falso(executavel: str, segundos: float, *, frozen: bool = False) -> list[str]:
    """O comando que sobe o servidor falso noutro processo (``python -m options_ponte ...``).
    Na ponte instalada (``frozen``), o executável já é a ponte: sem ``-m options_ponte``."""
    modulo = [] if frozen else ["-m", "options_ponte"]
    return [executavel, *modulo, "servidor-falso", "--segundos", f"{segundos:g}"]


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
        comando_servidor_falso(
            sys.executable, _VIDA_DO_SERVIDOR_FALSO_S, frozen=getattr(sys, "frozen", False)
        ),
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

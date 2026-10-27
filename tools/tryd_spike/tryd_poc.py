"""Prova de conceito do spike Tryd: ler cotações em tempo real por RTD ou DDE (ADR-0008, proposta).

NÃO é código de produção nem entra no pacote: é ferramenta de spike, roda
só no Windows e depende do ``pywin32`` (que NÃO é dependência do projeto).
Instale num venv separado::

    python -m venv .venv-tryd
    .venv-tryd\\Scripts\\pip install pywin32

Modos (rode da raiz do repositório)::

    python tools\\tryd_spike\\tryd_poc.py diagnostico
    python tools\\tryd_spike\\tryd_poc.py autoteste
    python tools\\tryd_spike\\tryd_poc.py rtd --ativos PETR4,PETRK300 --saida captura.json
    python tools\\tryd_spike\\tryd_poc.py dde --servico TRYD --topico COT --itens PETR4.ULT

- ``diagnostico``: só lê o registro e o ambiente (ProgID ``tryd.rtdserver``,
  DLL ou EXE do servidor e a arquitetura dela, bitness do Python, type library
  do Excel, Tryd rodando). Não muda nada.
- ``autoteste``: roda o cliente RTD contra um servidor RTD FALSO, sem Tryd e
  sem registro no Windows: primeiro no mesmo processo, depois noutro processo
  que morre no meio da captura. Valida o encanamento COM (ServerStart,
  ConnectData, UpdateNotify, RefreshData, parâmetros ByRef, marshaling entre
  processos) e a detecção de servidor perdido por Heartbeat.
- ``rtd``: assina ``=RTD("tryd.rtdserver";;"COT";ATIVO;CAMPO)`` para cada ativo
  e campo, bombeia mensagens por N segundos e grava em JSON cada atualização
  com o valor CRU (tipo e repr) — se número chega como float ou como texto
  pt-BR é uma das perguntas do spike. Servidor perdido sai com código 1.
- ``dde``: pede itens por DDE (``servico|topico!item``), uma vez; item que
  falha vira ``{"erro": ...}`` sem derrubar os outros.

Fórmula RTD e campos do tipo COT segundo um blog de 2017 (a conferir no Tryd
atual, roteiro em ``docs/spikes/tryd-intraday.md``): Ult, PrcCpa, PrcVda,
QtdNeg, Vol, DataHora, Exerc, Expir, DiaUtExp, Estado.
"""

import argparse
import contextlib
import datetime as dt
import importlib
import json
import os
import platform
import re
import struct
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar

PROGID = "tryd.rtdserver"
CAMPOS_PADRAO = ("Ult", "PrcCpa", "PrcVda", "QtdNeg", "Vol", "DataHora", "Exerc", "Expir")
EXCEL_TLB = "{00020813-0000-0000-C000-000000000046}"
IID_IRTDSERVER = "{EC0E6191-DB51-11D3-8F3E-00C04F3651B8}"
IID_IRTDUPDATEEVENT = "{A43788C1-D91B-11D3-8F39-00C04F3651B8}"


class SpikeError(Exception):
    """Falha esperada do spike, com mensagem para o usuário (sem traceback)."""


# ---------------------------------------------------------------------------
# Diagnóstico (só stdlib: winreg)
# ---------------------------------------------------------------------------


def _arquitetura_pe(caminho: Path) -> str:
    """32 ou 64 bits de um executável/DLL, pelo cabeçalho PE."""
    with caminho.open("rb") as arquivo:
        cabecalho = arquivo.read(4096)
    deslocamento = struct.unpack_from("<I", cabecalho, 0x3C)[0]
    maquina = struct.unpack_from("<H", cabecalho, deslocamento + 4)[0]
    return {0x14C: "32 bits (x86)", 0x8664: "64 bits (x64)", 0xAA64: "ARM64"}.get(
        maquina, hex(maquina)
    )


def _arquivo_do_comando(comando: str) -> Path:
    """O executável/DLL de um valor InprocServer32/LocalServer32.

    O valor pode vir com aspas ou sem, com argumentos (``EXCEL.EXE /automation``)
    e com variáveis de ambiente (``%SystemRoot%``).
    """
    texto = os.path.expandvars(comando.strip())
    if texto.startswith('"'):
        return Path(texto[1:].split('"', 1)[0])
    achado = re.search(r"\.(exe|dll)\b", texto, re.IGNORECASE)
    return Path(texto[: achado.end()] if achado else texto)


def _valor(chave: str, visao: int = 0) -> str | None:
    import winreg

    raiz, _, sub = chave.partition("\\")
    raizes = {"HKCR": winreg.HKEY_CLASSES_ROOT, "HKLM": winreg.HKEY_LOCAL_MACHINE}
    try:
        with winreg.OpenKey(raizes[raiz], sub, 0, winreg.KEY_READ | visao) as k:
            return str(winreg.QueryValueEx(k, "")[0])
    except OSError:
        return None


def diagnostico() -> int:
    import winreg

    bits = struct.calcsize("P") * 8
    print(f"Python {platform.python_version()} {bits} bits em {platform.platform()}")
    clsid = _valor(f"HKCR\\{PROGID}\\CLSID")
    if clsid is None:
        print(f"[falta] ProgID {PROGID!r} não registrado: Tryd ausente ou RTD nunca ativado")
        print("        (no Tryd: Arquivo > Ativar DDE e RTD, rodando como administrador)")
    else:
        print(f"[ok] ProgID {PROGID!r} -> CLSID {clsid}")
        for nome, visao in (
            ("64 bits", winreg.KEY_WOW64_64KEY),
            ("32 bits", winreg.KEY_WOW64_32KEY),
        ):
            for servidor in ("InprocServer32", "LocalServer32"):
                # HKCR é a visão unida de HKLM e HKCU: pega registro por usuário também.
                caminho = _valor(f"HKCR\\CLSID\\{clsid}\\{servidor}", visao)
                if caminho:
                    arquivo = _arquivo_do_comando(caminho)
                    arq = _arquitetura_pe(arquivo) if arquivo.exists() else "arquivo ausente"
                    print(f"     visão {nome}: {servidor} = {caminho} [{arq}]")
        print(
            "     InprocServer32 (DLL) só carrega num processo de MESMA arquitetura: Python e "
            "Excel precisam bater com ela; LocalServer32 (EXE) não tem essa restrição"
        )
    versoes = []
    with (
        contextlib.suppress(OSError),
        winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"TypeLib\\{EXCEL_TLB}") as k,
    ):
        versoes = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
    print(
        f"[{'ok' if versoes else 'falta'}] type library do Excel (IRtdServer): "
        f"{', '.join(versoes) or 'não registrada'}"
    )
    try:
        import win32com  # noqa: F401

        print("[ok] pywin32 instalado")
    except ImportError:
        print("[falta] pywin32: pip install pywin32 (num venv separado)")
    tarefas = subprocess.run(
        ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, check=False
    ).stdout.lower()
    print(f"[{'ok' if 'tryd' in tarefas else 'falta'}] processo do Tryd rodando")
    return 0


# ---------------------------------------------------------------------------
# Cliente RTD (pywin32, early binding pela type library do Excel)
# ---------------------------------------------------------------------------


def _tipos_rtd() -> None:
    """Carrega IRtdServer/IRTDUpdateEvent da type library do Excel (ByRef exige early binding)."""
    try:
        from win32com import universal
        from win32com.client import gencache
    except ImportError as erro:
        raise SpikeError("pywin32 não instalado: pip install pywin32") from erro
    try:
        gencache.EnsureModule(EXCEL_TLB, 0, 1, 4)
        universal.RegisterInterfaces(EXCEL_TLB, 0, 1, 4, ["IRtdServer", "IRTDUpdateEvent"])
    except Exception as erro:  # pythoncom.com_error e afins
        raise SpikeError(
            f"type library do Excel indisponível ({erro}); o cliente RTD precisa dela"
        ) from erro


class _AvisoDeAtualizacao:
    """Callback IRTDUpdateEvent que o servidor chama quando há dado novo.

    ``_typelib_guid_`` faz o pywin32 publicar os métodos com os DISPIDs da type
    library do Excel — os mesmos que um servidor RTD real (o Tryd) usa ao
    chamar o callback; sem isso a chamada falha com "membro não encontrado".
    """

    _typelib_guid_ = EXCEL_TLB
    _typelib_version_: ClassVar[tuple[int, int]] = (1, 4)
    _com_interfaces_: ClassVar[list[str]] = ["IRTDUpdateEvent"]
    _public_methods_: ClassVar[list[str]] = ["UpdateNotify", "Disconnect"]
    _public_attrs_: ClassVar[list[str]] = ["HeartbeatInterval"]

    def __init__(self) -> None:
        self.HeartbeatInterval = 1000
        self.avisos = 0
        self.desconectado = False

    def UpdateNotify(self) -> None:
        self.avisos += 1

    def Disconnect(self) -> None:
        self.desconectado = True


class ClienteRtd:
    """Faz o papel do Excel diante de um servidor RTD."""

    def __init__(self, servidor_bruto: Any) -> None:
        import win32com.client
        from win32com.server import util

        _tipos_rtd()
        classe = win32com.client.CLSIDToClass.GetClass(IID_IRTDSERVER)
        bruto = getattr(servidor_bruto, "_oleobj_", servidor_bruto)
        self._servidor = classe(bruto)
        self.aviso = _AvisoDeAtualizacao()
        self._topicos: dict[int, tuple[str, ...]] = {}
        status = self._servidor.ServerStart(util.wrap(self.aviso))
        if not status or status < 0:
            raise SpikeError(f"ServerStart devolveu {status!r}: servidor recusou o cliente")

    @classmethod
    def do_progid(cls, progid: str) -> "ClienteRtd":
        _tipos_rtd()
        import pythoncom
        import win32com.client

        try:
            return cls(win32com.client.Dispatch(progid))
        except pythoncom.com_error as erro:
            raise SpikeError(
                f"não foi possível criar {progid!r}: {erro}. Rode 'diagnostico' "
                f"(Tryd aberto e logado? RTD ativado? arquitetura da DLL igual à do Python?)"
            ) from erro

    def assinar(self, *strings: str) -> Any:
        """ConnectData de um tópico; devolve o valor inicial que o servidor der."""
        topico = len(self._topicos) + 1
        self._topicos[topico] = strings
        resultado = self._servidor.ConnectData(topico, strings, True)
        return resultado[0] if isinstance(resultado, tuple) else resultado

    def atualizar(self) -> list[tuple[tuple[str, ...], Any]]:
        """RefreshData: os tópicos que mudaram desde a última chamada, com o valor novo."""
        resultado = self._servidor.RefreshData(0)
        dados = resultado[0] if isinstance(resultado, tuple) and len(resultado) == 2 else resultado
        if not dados:
            return []
        ids, valores = dados[0], dados[1]
        return [(self._topicos.get(int(i), ("?",)), v) for i, v in zip(ids, valores, strict=False)]

    def vivo(self) -> bool:
        """Heartbeat, como o Excel faz quando o servidor fica em silêncio.

        Sem isso, um servidor que morre só para de mandar UpdateNotify e o
        cliente segue com os últimos valores congelados, sem erro nenhum.
        """
        import pythoncom

        try:
            return int(self._servidor.Heartbeat()) > 0
        except pythoncom.com_error:
            return False

    def encerrar(self) -> None:
        for topico in list(self._topicos):
            with contextlib.suppress(Exception):
                self._servidor.DisconnectData(topico)
        with contextlib.suppress(Exception):
            self._servidor.ServerTerminate()


def _bombear(segundos: float) -> None:
    import pythoncom

    fim = time.monotonic() + segundos
    while time.monotonic() < fim:
        pythoncom.PumpWaitingMessages()
        time.sleep(0.02)


def _cru(valor: Any) -> dict[str, str]:
    return {"tipo": type(valor).__name__, "repr": repr(valor)}


def capturar_rtd(
    cliente: ClienteRtd,
    ativos: Sequence[str],
    campos: Sequence[str],
    segundos: float,
    ao_assinar: Callable[[], None] | None = None,
    pulso_s: float = 5.0,
) -> dict[str, Any]:
    """Assina COT x ativo x campo, coleta por ``segundos`` e devolve a captura em JSON.

    Como o Excel, só chama RefreshData depois de um UpdateNotify novo e chama
    Heartbeat depois de ``pulso_s`` sem aviso. Servidor perdido encerra a
    captura e fica registrado em ``servidor_perdido``.
    ``ao_assinar`` roda logo depois das assinaturas (o autoteste publica ali).
    """
    import pythoncom

    inicio = dt.datetime.now().astimezone()
    iniciais: dict[str, dict[str, Any]] = {}
    for ativo in ativos:
        for campo in campos:
            iniciais.setdefault(ativo, {})[campo] = _cru(cliente.assinar("COT", ativo, campo))
    if ao_assinar is not None:
        ao_assinar()
    atualizacoes = []
    ultimos: dict[str, dict[str, Any]] = {a: dict(c) for a, c in iniciais.items()}
    processados = 0
    perdido: dict[str, str] | None = None
    ultimo_sinal = time.monotonic()
    fim = ultimo_sinal + segundos
    while time.monotonic() < fim and perdido is None:
        _bombear(0.25)
        agora = dt.datetime.now().astimezone().isoformat(timespec="milliseconds")
        if cliente.aviso.avisos > processados:
            processados = cliente.aviso.avisos
            ultimo_sinal = time.monotonic()
            try:
                mudancas = cliente.atualizar()
            except pythoncom.com_error as erro:
                perdido = {"t": agora, "erro": f"RefreshData: {erro}"}
                break
            for strings, valor in mudancas:
                if len(strings) == 3:
                    _, ativo, campo = strings
                    ultimos.setdefault(ativo, {})[campo] = _cru(valor)
                atualizacoes.append({"t": agora, "topico": list(strings), **_cru(valor)})
        elif cliente.aviso.desconectado:
            perdido = {"t": agora, "erro": "o servidor chamou Disconnect"}
        elif time.monotonic() - ultimo_sinal >= pulso_s:
            if not cliente.vivo():
                perdido = {"t": agora, "erro": f"Heartbeat falhou após {pulso_s:g} s sem aviso"}
            ultimo_sinal = time.monotonic()
    return {
        "progid": PROGID,
        "inicio": inicio.isoformat(timespec="seconds"),
        "duracao_s": segundos,
        "avisos_update_notify": cliente.aviso.avisos,
        "servidor_perdido": perdido,
        "valores_iniciais": iniciais,
        "ultimos": ultimos,
        "atualizacoes": atualizacoes,
    }


# ---------------------------------------------------------------------------
# Autoteste: servidor RTD falso no mesmo processo
# ---------------------------------------------------------------------------


class _ServidorFalso:
    """IRtdServer em Python, no molde do exemplo do pywin32 (excelRTDServer.py)."""

    _typelib_guid_ = EXCEL_TLB
    _typelib_version_: ClassVar[tuple[int, int]] = (1, 4)
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
        "Ult": 1.23,
        "PrcCpa": 1.22,
        "PrcVda": 1.24,
        "QtdNeg": 37,
        "Vol": 3700,
    }

    def __init__(self) -> None:
        self.topicos: dict[int, tuple[str, ...]] = {}
        self.mudados: set[int] = set()
        self.callback: Any = None
        self.tique = 0

    def ServerStart(self, callback: Any) -> int:
        import win32com.client

        self.callback = win32com.client.CLSIDToClass.GetClass(IID_IRTDUPDATEEVENT)(callback)
        return 1

    def ConnectData(
        self, topico: int, strings: Sequence[str], novos: bool
    ) -> tuple[Any, Sequence[str], bool]:
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
        _, ativo, campo = strings
        base = self._BOOK.get(campo, f"{ativo}.{campo}")
        return base + self.tique * 0.01 if isinstance(base, float) else base

    def publicar(self) -> None:
        """Simula um negócio: muda o último preço e avisa o cliente."""
        self.tique += 1
        self.mudados.update(t for t, s in self.topicos.items() if s[-1] == "Ult")
        self.callback.UpdateNotify()


def autoteste() -> int:
    from win32com.server import util

    _tipos_rtd()
    falso = _ServidorFalso()
    cliente = ClienteRtd(util.wrap(falso))
    inicial = cliente.assinar("COT", "PETRK300", "Ult")
    cliente.assinar("COT", "PETRK300", "PrcCpa")
    falso.publicar()
    _bombear(0.1)
    mudancas = cliente.atualizar()
    cliente.encerrar()
    print(f"valor inicial de Ult: {inicial!r}")
    print(f"avisos UpdateNotify recebidos: {cliente.aviso.avisos}")
    print(f"RefreshData: {mudancas!r}")
    esperado = [(("COT", "PETRK300", "Ult"), 1.24)]
    ok = (
        abs(inicial - 1.23) < 1e-12
        and cliente.aviso.avisos == 1
        and len(mudancas) == 1
        and mudancas[0][0] == esperado[0][0]
        and abs(mudancas[0][1] - 1.24) < 1e-12
    )
    falso_2 = _ServidorFalso()
    cliente_2 = ClienteRtd(util.wrap(falso_2))
    captura = capturar_rtd(cliente_2, ["PETRK300"], ["Ult", "PrcCpa"], 0.5, falso_2.publicar)
    cliente_2.encerrar()
    json.dumps(captura)  # a captura tem de ser serializável
    ultimo = captura["ultimos"]["PETRK300"]["Ult"]
    print(f"captura: {len(captura['atualizacoes'])} atualização(ões), último Ult {ultimo}")
    ok = ok and len(captura["atualizacoes"]) == 1 and ultimo == {"tipo": "float", "repr": "1.24"}
    ok = _autoteste_entre_processos() and ok
    print("AUTOTESTE OK: encanamento COM do cliente RTD funcionando" if ok else "AUTOTESTE FALHOU")
    return 0 if ok else 1


_CLSID_AUTOTESTE = "{6C1B5E0A-2F44-4B7E-9D7A-3A1F0B9C7E11}"


def servir_falso(segundos: float) -> int:
    """Servidor falso noutro processo, como o Tryd: um negócio a cada 0,5 s, depois sai.

    Publica-se na tabela de objetos ativos do COM: nada é gravado no registro.
    """
    import pythoncom
    from win32com.server import util

    _tipos_rtd()
    falso = _ServidorFalso()
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


def _autoteste_entre_processos() -> bool:
    """Cliente aqui, servidor noutro processo que morre no meio da captura."""
    import pythoncom

    servidor = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "servidor-falso", "--segundos", "2"],
        stdout=subprocess.PIPE,
        text=True,
    )
    inicio = time.monotonic()
    try:
        assert servidor.stdout is not None
        servidor.stdout.readline()  # "pronto", ou vazio se o servidor falhou
        try:
            bruto = pythoncom.GetActiveObject(_CLSID_AUTOTESTE)
        except pythoncom.com_error as erro:
            print(f"entre processos: servidor falso não apareceu ({erro})")
            return False
        cliente = ClienteRtd(bruto.QueryInterface(pythoncom.IID_IDispatch))
        captura = capturar_rtd(cliente, ["PETRK300"], ["Ult"], 8.0, pulso_s=1.0)
        cliente.encerrar()
    finally:
        servidor.wait(timeout=15)
    duracao = time.monotonic() - inicio
    perdido = captura["servidor_perdido"]
    print(
        f"entre processos: {len(captura['atualizacoes'])} atualização(ões); servidor "
        f"perdido detectado em {duracao:.1f} s: {perdido['erro'] if perdido else 'NÃO'}"
    )
    return len(captura["atualizacoes"]) >= 2 and perdido is not None and duracao < 8.0


# ---------------------------------------------------------------------------
# DDE (pywin32)
# ---------------------------------------------------------------------------


def pedir_dde(servico: str, topico: str, itens: Sequence[str]) -> dict[str, Any]:
    try:
        # O win32ui tem de vir ANTES: sem ele, "import dde" falha com "This must
        # be an MFC application". O importlib impede o isort de inverter a ordem.
        import win32ui  # noqa: F401

        dde = importlib.import_module("dde")
    except ImportError as erro:
        raise SpikeError(f"módulo dde do pywin32 indisponível ({erro})") from erro
    servidor = dde.CreateServer()
    servidor.Create("SpikeTryd")
    try:
        conversa = dde.CreateConversation(servidor)
        try:
            conversa.ConnectTo(servico, topico)
        except Exception as erro:
            raise SpikeError(
                f"DDE {servico}|{topico} não respondeu ({erro}); confira o nome do serviço "
                f"e do tópico nos links que o Tryd gera"
            ) from erro
        resposta: dict[str, Any] = {}
        for item in itens:
            # Item inexistente falha só ele (dde.error "Request failed"); os outros seguem.
            try:
                resposta[item] = _cru(conversa.Request(item))
            except dde.error as erro:
                resposta[item] = {"erro": str(erro)}
        return resposta
    finally:
        servidor.Destroy()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _lista(texto: str) -> tuple[str, ...]:
    return tuple(t.strip() for t in texto.split(",") if t.strip())


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tryd_poc", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="modo", required=True)
    sub.add_parser("diagnostico", help="registro, arquitetura e ambiente (só leitura)")
    sub.add_parser("autoteste", help="cliente RTD contra servidor falso, sem Tryd")
    p_rtd = sub.add_parser("rtd", help="captura real pelo tryd.rtdserver")
    p_rtd.add_argument("--ativos", required=True, type=_lista, help="ex.: PETR4,PETRK300")
    p_rtd.add_argument("--campos", type=_lista, default=CAMPOS_PADRAO)
    p_rtd.add_argument("--segundos", type=float, default=15.0)
    p_rtd.add_argument("--saida", type=Path, help="arquivo JSON da captura")
    p_dde = sub.add_parser("dde", help="pedido único por DDE")
    p_dde.add_argument("--servico", required=True)
    p_dde.add_argument("--topico", required=True)
    p_dde.add_argument("--itens", required=True, type=_lista)
    p_falso = sub.add_parser("servidor-falso", help="uso interno do autoteste")
    p_falso.add_argument("--segundos", type=float, default=2.0)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        print("o spike Tryd só roda no Windows", file=sys.stderr)
        return 2
    try:
        if args.modo == "diagnostico":
            return diagnostico()
        if args.modo == "autoteste":
            return autoteste()
        if args.modo == "servidor-falso":
            return servir_falso(args.segundos)
        if args.modo == "rtd":
            cliente = ClienteRtd.do_progid(PROGID)
            try:
                captura = capturar_rtd(cliente, args.ativos, args.campos, args.segundos)
            finally:
                cliente.encerrar()
            texto = json.dumps(captura, ensure_ascii=False, indent=2)
            if args.saida:
                args.saida.write_text(texto, encoding="utf-8")
                print(
                    f"captura gravada em {args.saida}: {len(captura['atualizacoes'])} "
                    f"atualizações em {args.segundos:g} s"
                )
            else:
                print(texto)
            if perdido := captura["servidor_perdido"]:
                print(f"aviso: servidor RTD perdido: {perdido}", file=sys.stderr)
                return 1
            return 0
        resposta = pedir_dde(args.servico, args.topico, args.itens)
        print(json.dumps(resposta, ensure_ascii=False, indent=2))
        return 0
    except SpikeError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

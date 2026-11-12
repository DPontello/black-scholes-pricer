"""Camada COM da ponte — a lógica que não precisa de COM, com um pywin32 falso nos ``sys.modules``.

O que fala de verdade com o Tryd (ProgID/CLSID, type library, RefreshData) só roda no Windows
ou no Wine; a evidência desse trecho é a saída do ``autoteste`` e do ``espiar`` ao vivo, no
relatório da Task 8. Aqui ficam a ordem das type libraries, a escolha ProgID -> CLSID, o formato
do que o ``RefreshData`` devolve, o bombeamento e o parsing do registro.
"""

import inspect
import struct
import sys
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from options_ponte import rtd, tryd7, vias
from options_ponte.protocolo import CLSID
from options_ponte.tryd7 import INI_RELATIVO
from options_ponte.vias import (
    CLSID_TRYD7,
    MOTIVO_SO_PROFIT,
    VIA_TRYD7,
    VIA_TRYD8,
    VISAO_DO_PROCESSO,
)
from tests.ponte.registro_falso import RegistroFalso

TLB_RTDTRADING = "{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}"
TLB_EXCEL = "{00020813-0000-0000-C000-000000000046}"
IID_SERVIDOR = "{EC0E6191-DB51-11D3-8F3E-00C04F3651B8}"
IID_AVISO = "{A43788C1-D91B-11D3-8F39-00C04F3651B8}"
IID_DE_OUTRO = "{11111111-2222-3333-4444-555555555555}"
TYPE_E_LIBNOTREGISTERED = -2147319779
CO_E_CLASSSTRING = -2147221005
REGDB_E_CLASSNOTREG = -2147221164
E_NOINTERFACE = -2147467262
MOTIVO_IIDS_DIFERENTES = (
    "IIDs diferentes dos do Excel (o StRtd do Tryd 7 e o tryd.exe usam os do Excel)"
)


class ErroCom(Exception):
    """Faz o papel do ``pythoncom.com_error``: o HRESULT vem em ``hresult`` e em ``args[0]``."""

    def __init__(self, hresult: int, texto: str) -> None:
        super().__init__(hresult, texto, None, None)
        self.hresult = hresult


class Pywin32Falso:
    """Os módulos do pywin32 que ``rtd`` importa, trocados por objetos simples."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.carregaveis: dict[str, dict[str, str]] = {}  # guid -> NamesToIIDMap
        self.chamadas_ensure: list[tuple[str, int, int, int]] = []
        self.chamadas_register: list[tuple[str, int, int, int, list[str]]] = []
        self.progid_resolve_para: str | None = "{PROGID-RESOLVIDO}"
        self.erro_do_progid = ErroCom(CO_E_CLASSSTRING, "Class string inválida")
        self.chamadas_create: list[tuple[Any, object, int, Any]] = []
        self.erro_ao_criar: ErroCom | None = None
        self.erro_ao_registrar: ErroCom | None = None
        self.objeto_criado: object = "servidor-bruto"
        self.bombeadas = 0
        gencache = SimpleNamespace(EnsureModule=self._ensure_module)
        universal = SimpleNamespace(RegisterInterfaces=self._register_interfaces)
        pythoncom = SimpleNamespace(
            com_error=ErroCom,
            CLSCTX_SERVER=21,
            CLSCTX_LOCAL_SERVER=4,
            CLSCTX_INPROC_SERVER=1,
            IID_IDispatch="IDispatch",
            CoCreateInstance=self._criar,
            PumpWaitingMessages=self._bombear,
        )
        for nome, modulo in {
            "pythoncom": pythoncom,
            "pywintypes": SimpleNamespace(IID=self._iid),
            "win32com.client.gencache": gencache,
            "win32com.universal": universal,
            "win32com.client.CLSIDToClass": SimpleNamespace(GetClass=lambda _iid: lambda b: b),
            "win32com.server.util": SimpleNamespace(wrap=lambda objeto: objeto),
        }.items():
            monkeypatch.setitem(sys.modules, nome, modulo)

    def tornar_carregavel(self, guid: str, interfaces: dict[str, str] | None = None) -> None:
        self.carregaveis[guid] = (
            {"IRtdServer": IID_SERVIDOR, "IRTDUpdateEvent": IID_AVISO}
            if interfaces is None
            else interfaces
        )

    def _ensure_module(self, guid: str, lcid: int, major: int, minor: int) -> object:
        self.chamadas_ensure.append((guid, lcid, major, minor))
        if guid not in self.carregaveis:
            raise ErroCom(TYPE_E_LIBNOTREGISTERED, "TYPE_E_LIBNOTREGISTERED")
        return SimpleNamespace(NamesToIIDMap=self.carregaveis[guid])

    def _register_interfaces(
        self, guid: str, lcid: int, major: int, minor: int, nomes: list[str]
    ) -> list[object]:
        self.chamadas_register.append((guid, lcid, major, minor, nomes))
        if self.erro_ao_registrar is not None:
            raise self.erro_ao_registrar
        return []

    def _iid(self, texto: str) -> Any:
        """``pywintypes.IID``: CLSID entre chaves vira IID; o resto é ProgID e pode não resolver."""
        if texto.startswith("{"):
            return ("IID", texto)
        if self.progid_resolve_para is None:
            raise self.erro_do_progid
        return ("IID", self.progid_resolve_para)

    def _criar(self, clsid: Any, externo: object, contexto: int, iid: Any) -> object:
        self.chamadas_create.append((clsid, externo, contexto, iid))
        if self.erro_ao_criar is not None:
            raise self.erro_ao_criar
        return self.objeto_criado

    def _bombear(self) -> None:
        self.bombeadas += 1


class ObjetoCom:
    """O ``IDispatch`` cru do ``CoCreateInstance``, com o ``QueryInterface`` do pywin32."""

    def __init__(self) -> None:
        self.consultas: list[tuple[Any, Any]] = []  # (IID pedido, IID do invólucro)
        self.interface: object = "servidor-pelo-qi"
        self.erro_no_qi: ErroCom | None = None

    def QueryInterface(self, iid: Any, iid_do_involucro: Any) -> object:
        self.consultas.append((iid, iid_do_involucro))
        if self.erro_no_qi is not None:
            raise self.erro_no_qi
        return self.interface


@pytest.fixture
def pywin32(monkeypatch: pytest.MonkeyPatch) -> Pywin32Falso:
    return Pywin32Falso(monkeypatch)


# --------------------------------------------------------------------------- type libraries

COM_IIDS_DE_OUTRO = pytest.mark.parametrize(
    "interfaces",
    [
        {"IRtdServer": IID_DE_OUTRO, "IRTDUpdateEvent": IID_AVISO},
        {"IRtdServer": IID_SERVIDOR, "IRTDUpdateEvent": IID_DE_OUTRO},
    ],
    ids=["IRtdServer_de_outro", "IRTDUpdateEvent_de_outro"],
)


def test_carregar_tipos_prefere_a_type_library_do_rtdtrading(pywin32: Pywin32Falso) -> None:
    pywin32.tornar_carregavel(TLB_RTDTRADING)
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert (tipos.nome, tipos.guid, tipos.major, tipos.minor) == (
        "RTDTrading",
        TLB_RTDTRADING,
        1,
        0,
    )
    assert (tipos.iid_servidor, tipos.iid_aviso) == (IID_SERVIDOR, IID_AVISO)
    assert tipos.descartadas == ()
    assert tipos.aviso is None
    assert [c[0] for c in pywin32.chamadas_ensure] == [TLB_RTDTRADING]  # a do Excel nem é tentada
    assert pywin32.chamadas_register == [
        (TLB_RTDTRADING, 0, 1, 0, ["IRtdServer", "IRTDUpdateEvent"])
    ]


def test_carregar_tipos_cai_na_do_excel_e_guarda_o_motivo_da_do_rtdtrading(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert (tipos.nome, tipos.guid, tipos.major, tipos.minor) == ("Excel", TLB_EXCEL, 1, 4)
    ((descricao, motivo),) = tipos.descartadas
    assert "RTDTrading" in descricao
    assert TLB_RTDTRADING in descricao
    assert "TYPE_E_LIBNOTREGISTERED" in motivo
    assert [c[0] for c in pywin32.chamadas_ensure] == [TLB_RTDTRADING, TLB_EXCEL]


def test_type_library_do_rtdtrading_sem_a_interface_nao_serve_e_cai_na_do_excel(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.tornar_carregavel(TLB_RTDTRADING, {"IRtdServer": IID_SERVIDOR})  # sem IRTDUpdateEvent
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert tipos.nome == "Excel"
    ((_, motivo),) = tipos.descartadas
    assert "IRTDUpdateEvent" in motivo


@COM_IIDS_DE_OUTRO
def test_biblioteca_com_iids_de_outro_nao_serve_e_cai_na_do_excel(
    pywin32: Pywin32Falso, interfaces: dict[str, str]
) -> None:
    """O StRtd do Tryd 7 e o ``tryd.exe`` usam os IIDs do Excel: uma biblioteca com outros daria
    um cliente que o servidor não reconhece."""
    pywin32.tornar_carregavel(TLB_RTDTRADING, interfaces)
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert tipos.nome == "Excel"
    assert tipos.aviso is None
    ((descricao, motivo),) = tipos.descartadas
    assert TLB_RTDTRADING in descricao
    assert motivo == MOTIVO_IIDS_DIFERENTES
    # a descartada não chegou ao RegisterInterfaces
    assert [c[0] for c in pywin32.chamadas_register] == [TLB_EXCEL]


@COM_IIDS_DE_OUTRO
def test_biblioteca_com_iids_de_outro_serve_se_a_do_excel_nao_carrega(
    pywin32: Pywin32Falso, interfaces: dict[str, str]
) -> None:
    """Nada prova que a do RTDTrading tenha os IIDs do Excel: sem a do Excel (Windows sem Office
    de 32 bits), ela é usada com o aviso, em vez de a ponte ficar sem type library."""
    pywin32.tornar_carregavel(TLB_RTDTRADING, interfaces)
    tipos = rtd.carregar_tipos()
    assert tipos.nome == "RTDTrading"
    assert (tipos.iid_servidor, tipos.iid_aviso) == (
        interfaces["IRtdServer"],
        interfaces["IRTDUpdateEvent"],
    )
    assert tipos.aviso == MOTIVO_IIDS_DIFERENTES
    ((descricao, motivo),) = tipos.descartadas  # só a do Excel, que nem carregou
    assert TLB_EXCEL in descricao
    assert "TYPE_E_LIBNOTREGISTERED" in motivo
    assert [c[0] for c in pywin32.chamadas_ensure] == [TLB_RTDTRADING, TLB_EXCEL]
    assert pywin32.chamadas_register == [
        (TLB_RTDTRADING, 0, 1, 0, ["IRtdServer", "IRTDUpdateEvent"])
    ]


def test_com_as_duas_de_iids_diferentes_vale_a_primeira_que_carregou(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.tornar_carregavel(
        TLB_RTDTRADING, {"IRtdServer": IID_DE_OUTRO, "IRTDUpdateEvent": IID_AVISO}
    )
    pywin32.tornar_carregavel(
        TLB_EXCEL, {"IRtdServer": IID_SERVIDOR, "IRTDUpdateEvent": IID_DE_OUTRO}
    )
    tipos = rtd.carregar_tipos()
    assert tipos.nome == "RTDTrading"
    assert tipos.aviso == MOTIVO_IIDS_DIFERENTES
    assert [(descricao.split()[0], motivo) for descricao, motivo in tipos.descartadas] == [
        ("Excel", MOTIVO_IIDS_DIFERENTES)
    ]
    assert [c[0] for c in pywin32.chamadas_register] == [TLB_RTDTRADING]  # só a escolhida


def test_biblioteca_de_iids_diferentes_que_nao_registra_vira_erro_com_o_motivo(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.tornar_carregavel(
        TLB_RTDTRADING, {"IRtdServer": IID_DE_OUTRO, "IRTDUpdateEvent": IID_AVISO}
    )
    pywin32.erro_ao_registrar = ErroCom(E_NOINTERFACE, "RegisterInterfaces falhou")
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.carregar_tipos()
    assert "RegisterInterfaces falhou" in str(erro.value)
    assert MOTIVO_IIDS_DIFERENTES not in str(erro.value)  # o motivo verdadeiro, não o do IID


def test_diagnostico_dos_tipos_mostra_a_do_rtdtrading_de_iids_diferentes_como_descartada(
    pywin32: Pywin32Falso, capsys: pytest.CaptureFixture[str]
) -> None:
    pywin32.tornar_carregavel(
        TLB_RTDTRADING, {"IRtdServer": IID_DE_OUTRO, "IRTDUpdateEvent": IID_AVISO}
    )
    pywin32.tornar_carregavel(TLB_EXCEL)
    assert rtd._diagnosticar_tipos() == 0
    linhas = capsys.readouterr().out.splitlines()
    assert linhas[0] == f"[aviso] type library RTDTrading {TLB_RTDTRADING} 1.0 não serviu: " + (
        MOTIVO_IIDS_DIFERENTES
    )
    assert linhas[1].startswith(f"[ok] type library em uso: Excel {TLB_EXCEL} 1.4 ")
    assert len(linhas) == 2


def test_diagnostico_dos_tipos_avisa_da_de_iids_diferentes_que_ficou_em_uso(
    pywin32: Pywin32Falso, capsys: pytest.CaptureFixture[str]
) -> None:
    pywin32.tornar_carregavel(
        TLB_RTDTRADING, {"IRtdServer": IID_DE_OUTRO, "IRTDUpdateEvent": IID_AVISO}
    )
    assert rtd._diagnosticar_tipos() == 0  # com aviso, mas serve: não conta como falta
    linhas = capsys.readouterr().out.splitlines()
    assert f"[aviso] type library Excel {TLB_EXCEL} 1.4 não serviu: " in linhas[0]
    assert linhas[1] == (
        f"[aviso] type library RTDTrading {TLB_RTDTRADING} 1.0 usada por falta de outra: "
        f"{MOTIVO_IIDS_DIFERENTES}"
    )
    assert linhas[2].startswith(f"[ok] type library em uso: RTDTrading {TLB_RTDTRADING} 1.0 ")
    assert f"(IRtdServer {IID_DE_OUTRO}, IRTDUpdateEvent {IID_AVISO})" in linhas[2]


def test_biblioteca_com_os_iids_do_excel_em_minusculas_ainda_serve(pywin32: Pywin32Falso) -> None:
    pywin32.tornar_carregavel(
        TLB_RTDTRADING,
        {"IRtdServer": IID_SERVIDOR.lower(), "IRTDUpdateEvent": IID_AVISO.lower()},
    )
    assert rtd.carregar_tipos().nome == "RTDTrading"


def test_nenhuma_type_library_vira_erro_que_diz_qual_faltou(pywin32: Pywin32Falso) -> None:
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.carregar_tipos()
    texto = str(erro.value)
    assert "RTDTrading" in texto
    assert "Excel" in texto
    assert TLB_RTDTRADING in texto
    assert TLB_EXCEL in texto
    assert "TYPE_E_LIBNOTREGISTERED" in texto


def test_pywin32_ausente_vira_erro_explicito(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "win32com.client.gencache", None)  # import -> ImportError
    with pytest.raises(rtd.ErroRtd, match="pywin32"):
        rtd.carregar_tipos()


# --------------------------------------------------------------------------- ProgID -> CLSID


def test_progid_que_resolve_cria_pelo_clsid_do_progid_em_qualquer_contexto(
    pywin32: Pywin32Falso,
) -> None:
    assert rtd.criar_servidor(VIA_TRYD8) == "servidor-bruto"
    assert pywin32.chamadas_create == [(("IID", "{PROGID-RESOLVIDO}"), None, 21, "IDispatch")]


def test_progid_com_co_e_classstring_cai_no_clsid_com_servidor_local(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.progid_resolve_para = None  # o Wine não acha o ProgID registrado só em HKCU
    assert rtd.criar_servidor(VIA_TRYD8) == "servidor-bruto"
    assert pywin32.chamadas_create == [(("IID", CLSID), None, 4, "IDispatch")]


def test_outro_erro_do_progid_nao_cai_no_clsid(pywin32: Pywin32Falso) -> None:
    pywin32.progid_resolve_para = None
    pywin32.erro_do_progid = ErroCom(REGDB_E_CLASSNOTREG, "classe não registrada")
    with pytest.raises(rtd.ErroRtd, match="classe não registrada"):
        rtd.criar_servidor(VIA_TRYD8)
    assert pywin32.chamadas_create == []


def test_falha_ao_criar_o_servidor_vira_erro_que_diz_como_foi_criado(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.progid_resolve_para = None
    pywin32.erro_ao_criar = ErroCom(-2147023174, "O servidor RPC não está disponível")
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.criar_servidor(VIA_TRYD8)
    assert CLSID in str(erro.value)
    assert "servidor RPC" in str(erro.value)
    assert "diagnostico" in str(erro.value)


def test_criar_servidor_sem_via_e_o_do_tryd8(pywin32: Pywin32Falso) -> None:
    pywin32.progid_resolve_para = None
    assert rtd.criar_servidor() == "servidor-bruto"
    assert pywin32.chamadas_create == [(("IID", CLSID), None, 4, "IDispatch")]


def test_tryd7_cria_dentro_do_processo_pelo_clsid_sem_passar_pelo_progid(
    pywin32: Pywin32Falso,
) -> None:
    # se passasse pelo ProgID, o falso levantaria o erro abaixo
    pywin32.progid_resolve_para = None
    pywin32.erro_do_progid = ErroCom(REGDB_E_CLASSNOTREG, "o ProgID não devia ser tocado")
    pywin32.objeto_criado = ObjetoCom()
    assert rtd.criar_servidor(VIA_TRYD7) == "servidor-pelo-qi"
    assert pywin32.chamadas_create == [(("IID", CLSID_TRYD7), None, 1, "IDispatch")]


def test_tryd7_pede_o_irtdserver_pelo_iid_do_excel_e_usa_esse_ponteiro(
    pywin32: Pywin32Falso,
) -> None:
    """O IDispatch padrão de um servidor .NET pode ser o da interface de classe (DISPIDs do CLR):
    o Excel pede o IRtdServer pelo IID, e a ponte também."""
    bruto = ObjetoCom()
    pywin32.objeto_criado = bruto
    assert rtd.criar_servidor(VIA_TRYD7) is bruto.interface
    assert bruto.consultas == [(("IID", IID_SERVIDOR), "IDispatch")]


def test_tryd7_com_o_qi_falhando_usa_o_idispatch_cru(pywin32: Pywin32Falso) -> None:
    bruto = ObjetoCom()
    bruto.erro_no_qi = ErroCom(E_NOINTERFACE, "Interface não suportada")
    pywin32.objeto_criado = bruto
    assert rtd.criar_servidor(VIA_TRYD7) is bruto
    assert len(bruto.consultas) == 1


@pytest.mark.parametrize("progid_resolve", [True, False], ids=["pelo_progid", "pelo_clsid"])
def test_tryd8_nao_faz_query_interface(pywin32: Pywin32Falso, progid_resolve: bool) -> None:
    if not progid_resolve:
        pywin32.progid_resolve_para = None
    bruto = ObjetoCom()
    pywin32.objeto_criado = bruto
    assert rtd.criar_servidor(VIA_TRYD8) is bruto
    assert bruto.consultas == []


def test_falha_ao_criar_o_servidor_do_tryd7_diz_a_via_o_clsid_e_o_que_conferir(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.erro_ao_criar = ErroCom(REGDB_E_CLASSNOTREG, "Classe não registrada")
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.criar_servidor(VIA_TRYD7)
    texto = str(erro.value)
    assert VIA_TRYD7.nome in texto
    assert CLSID_TRYD7 in texto
    assert "Classe não registrada" in texto
    assert "Rode 'diagnostico' (Tryd.RtdServer registrado? .NET 3.5 instalado?)" in texto


# --------------------------------------------------------------------------- bombear


def test_bombear_bombeia_e_dorme_ate_o_fim_do_passo_sem_girar(pywin32: Pywin32Falso) -> None:
    agora = [100.0]
    sonos: list[float] = []

    def relogio() -> float:
        agora[0] += 1e-6  # o tempo corre um pouco por chamada: sem dormir o laço ainda acabaria
        return agora[0]

    def dormir(segundos: float) -> None:
        sonos.append(segundos)
        agora[0] += segundos

    rtd.bombear(0.05, relogio=relogio, dormir=dormir)
    assert agora[0] == pytest.approx(100.05, abs=1e-4)
    assert sonos  # nunca gira sem dormir
    assert all(0 < s <= 0.02 for s in sonos)
    assert pywin32.bombeadas == len(sonos) + 1  # uma volta a mais, a que vê o fim do passo


def test_bombear_com_passo_nulo_bombeia_uma_vez_e_volta(pywin32: Pywin32Falso) -> None:
    rtd.bombear(0.0, relogio=lambda: 1.0, dormir=lambda _s: pytest.fail("não devia dormir"))
    assert pywin32.bombeadas == 1


# --------------------------------------------------------------------------- SessaoRtdCom


class ServidorRtdFalso:
    """O que o ``SessaoRtdCom`` chama no servidor RTD (a IRtdServer), com retornos configuráveis."""

    def __init__(self) -> None:
        self.chamadas: list[tuple[Any, ...]] = []
        self.retorno_server_start: Any = 1
        self.retorno_connect: Any = (38.42, ("PETR4_B_0", "ULT"), True)
        self.retorno_refresh: Any = (((), ()), 0)
        self.retorno_heartbeat: Any = 1
        self.erro_no_heartbeat: Exception | None = None
        self.erro_ao_conectar: Exception | None = None
        self.erro_ao_desconectar: Exception | None = None

    def QueryInterface(self, iid: Any, iid_do_involucro: Any) -> Any:
        """O ponteiro que o objeto COM devolve ao ser pedido pelo IID do IRtdServer: ele mesmo."""
        return self

    def ServerStart(self, aviso: object) -> Any:
        self.chamadas.append(("ServerStart", aviso))
        return self.retorno_server_start

    def ConnectData(self, id_: int, strings: Any, novos: bool) -> Any:
        self.chamadas.append(("ConnectData", id_, strings, novos))
        if self.erro_ao_conectar is not None:
            raise self.erro_ao_conectar
        return self.retorno_connect

    def RefreshData(self, contagem: int) -> Any:
        self.chamadas.append(("RefreshData", contagem))
        return self.retorno_refresh

    def DisconnectData(self, id_: int) -> None:
        self.chamadas.append(("DisconnectData", id_))
        if self.erro_ao_desconectar is not None:
            raise self.erro_ao_desconectar

    def Heartbeat(self) -> Any:
        self.chamadas.append(("Heartbeat",))
        if self.erro_no_heartbeat is not None:
            raise self.erro_no_heartbeat
        return self.retorno_heartbeat

    def ServerTerminate(self) -> None:
        self.chamadas.append(("ServerTerminate",))


def _sessao(pywin32: Pywin32Falso) -> tuple[rtd.SessaoRtdCom, ServidorRtdFalso]:
    pywin32.tornar_carregavel(TLB_EXCEL)
    servidor = ServidorRtdFalso()
    return rtd.SessaoRtdCom(servidor=servidor), servidor


def test_sessao_inicia_o_servidor_com_o_aviso_de_atualizacao(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    ((nome, aviso),) = servidor.chamadas
    assert nome == "ServerStart"
    assert aviso is not None
    assert sessao.avisos() == 0
    aviso.UpdateNotify()
    aviso.UpdateNotify()
    assert sessao.avisos() == 2


def test_server_start_que_recusa_vira_erro(pywin32: Pywin32Falso) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    servidor = ServidorRtdFalso()
    servidor.retorno_server_start = 0
    with pytest.raises(rtd.ErroRtd, match="ServerStart"):
        rtd.SessaoRtdCom(servidor=servidor)


def test_conectar_devolve_o_valor_inicial_do_connect_data(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    assert sessao.conectar(7, ("PETR4_B_0", "ULT")) == 38.42
    assert servidor.chamadas[-1] == ("ConnectData", 7, ("PETR4_B_0", "ULT"), True)


def test_conectar_aceita_retorno_sem_tupla(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.retorno_connect = "texto"
    assert sessao.conectar(1, ("PETR4_B_0", "HOR")) == "texto"


@pytest.mark.parametrize(
    "retorno",
    [
        (((1, 2), (38.5, "10:03:00")), 2),  # (array, TopicCount) por causa do ByRef
        ((1, 2), (38.5, "10:03:00")),  # o array sozinho
    ],
    ids=["array_e_contagem", "so_o_array"],
)
def test_atualizar_pareia_ids_e_valores(pywin32: Pywin32Falso, retorno: Any) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.retorno_refresh = retorno
    assert sessao.atualizar() == [(1, 38.5), (2, "10:03:00")]
    assert servidor.chamadas[-1] == ("RefreshData", 0)


@pytest.mark.parametrize(
    "retorno",
    [None, (None, 0), ((), ()), (((), ()), 0), ((None, None), 0)],
    ids=["nada", "nada_e_zero", "vazio", "vazio_e_zero", "listas_nulas"],
)
def test_atualizar_sem_mudancas_devolve_lista_vazia(pywin32: Pywin32Falso, retorno: Any) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.retorno_refresh = retorno
    assert sessao.atualizar() == []


def test_atualizar_converte_o_id_para_int(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.retorno_refresh = (((3.0,), ("x",)), 1)  # o COM pode entregar o id como float
    (par,) = sessao.atualizar()
    assert par == (3, "x")
    assert type(par[0]) is int


def test_vivo_segue_o_heartbeat(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    assert sessao.vivo() is True
    servidor.retorno_heartbeat = 0
    assert sessao.vivo() is False


def test_vivo_e_falso_se_o_heartbeat_der_erro_com(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.erro_no_heartbeat = ErroCom(-2147023174, "O servidor RPC não está disponível")
    assert sessao.vivo() is False


def test_vivo_e_falso_depois_que_o_servidor_chama_disconnect(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.chamadas[0][1].Disconnect()
    assert sessao.vivo() is False
    assert ("Heartbeat",) not in servidor.chamadas


def test_desconectar_chama_disconnect_data_e_esquece_o_id(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    sessao.conectar(1, ("PETR4_B_0", "ULT"))
    sessao.desconectar(1)
    sessao.encerrar()
    assert servidor.chamadas.count(("DisconnectData", 1)) == 1  # o encerrar não repete


def test_encerrar_desconecta_o_que_sobrou_e_termina_o_servidor_mesmo_com_erros(
    pywin32: Pywin32Falso,
) -> None:
    sessao, servidor = _sessao(pywin32)
    sessao.conectar(1, ("PETR4_B_0", "ULT"))
    sessao.conectar(2, ("PETR4_B_0", "OCP"))
    servidor.erro_ao_desconectar = ErroCom(-2147023174, "RPC")
    sessao.encerrar()
    assert [c for c in servidor.chamadas if c[0] != "ServerStart" and c[0] != "ConnectData"] == [
        ("DisconnectData", 1),
        ("DisconnectData", 2),
        ("ServerTerminate",),
    ]


def test_conectar_que_falha_nao_deixa_o_id_para_o_encerrar(pywin32: Pywin32Falso) -> None:
    sessao, servidor = _sessao(pywin32)
    servidor.erro_ao_conectar = ErroCom(-2147023174, "RPC")
    with pytest.raises(ErroCom):
        sessao.conectar(5, ("PETR4_B_0", "ULT"))
    sessao.encerrar()
    assert ("DisconnectData", 5) not in servidor.chamadas


# --------------------------------------------------------------------------- a via da sessão

TRYD_EXE = "C:\\Users\\Maria Silva\\AppData\\Roaming\\Tryd\\Tryd\\tryd.exe"
MSCOREE = "C:\\Windows\\System32\\mscoree.dll"


def _classe(registro: RegistroFalso, clsid: str, servidor: str, comando: str) -> None:
    """``CLSID\\{clsid}\\{servidor}`` em ``HKCU``, na visão do processo (onde a escolha lê)."""
    registro.definir(
        "HKCU",
        f"Software\\Classes\\CLSID\\{clsid}\\{servidor}",
        comando,
        visao=VISAO_DO_PROCESSO,
    )


def _registro_do_tryd8() -> RegistroFalso:
    registro = RegistroFalso()
    _classe(registro, CLSID, "LocalServer32", TRYD_EXE)
    return registro


def _registro_do_tryd7() -> RegistroFalso:
    registro = RegistroFalso()
    _classe(registro, CLSID_TRYD7, "InprocServer32", MSCOREE)
    return registro


def _nao_deveria_tocar() -> object:
    pytest.fail("o registro não pode ser tocado neste cenário")


def test_sessao_do_tryd8_monta_topico_com_o_sufixo_de_book(pywin32: Pywin32Falso) -> None:
    sessao, _ = _sessao(pywin32)  # com servidor e sem via: a do Tryd 8
    assert sessao.topico("PETR4", "ULT") == ("PETR4_B_0", "ULT")


def test_sessao_com_servidor_pronto_nao_toca_o_registro(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tryd7, "RegistroWinreg", _nao_deveria_tocar)
    monkeypatch.setattr(rtd, "verificar_stdde", _nao_deveria_tocar)
    sessao, _ = _sessao(pywin32)
    assert sessao.topico("PETR4", "ULT") == ("PETR4_B_0", "ULT")


def test_sessao_do_tryd7_cria_dentro_do_processo_pelo_clsid(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    servidor = ServidorRtdFalso()
    pywin32.objeto_criado = servidor
    criados_ao_verificar: list[int] = []
    monkeypatch.setattr(
        rtd, "verificar_stdde", lambda: criados_ao_verificar.append(len(pywin32.chamadas_create))
    )
    sessao = rtd.SessaoRtdCom(VIA_TRYD7)
    assert criados_ao_verificar == [0]  # o StDde é conferido antes de criar
    assert pywin32.chamadas_create == [(("IID", CLSID_TRYD7), None, 1, "IDispatch")]
    assert [chamada[0] for chamada in servidor.chamadas] == ["ServerStart"]
    assert sessao.topico("PETR4", "ULT") == ("COT", "PETR4", "ULT")


def test_sessao_do_tryd7_fala_com_o_ponteiro_do_query_interface(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    bruto = ObjetoCom()
    interface = ServidorRtdFalso()
    bruto.interface = interface
    pywin32.objeto_criado = bruto
    monkeypatch.setattr(rtd, "verificar_stdde", lambda: None)
    sessao = rtd.SessaoRtdCom(VIA_TRYD7)
    assert sessao.conectar(1, ("COT", "PETR4", "ULT")) == 38.42
    assert [chamada[0] for chamada in interface.chamadas] == ["ServerStart", "ConnectData"]


def test_sessao_do_tryd7_monta_topico_de_tres_strings(pywin32: Pywin32Falso) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    servidor = ServidorRtdFalso()
    sessao = rtd.SessaoRtdCom(VIA_TRYD7, servidor=servidor)
    topico = sessao.topico("PETR4", "ULT")
    assert topico == ("COT", "PETR4", "ULT")
    assert sessao.conectar(3, topico) == 38.42
    assert servidor.chamadas[-1] == ("ConnectData", 3, ("COT", "PETR4", "ULT"), True)


def test_sessao_do_tryd7_sem_stdde_nao_cria_o_servidor(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)

    def sem_stdde() -> None:
        raise rtd.ErroRtd(rtd.MOTIVO_STDDE_FECHADO)

    monkeypatch.setattr(rtd, "verificar_stdde", sem_stdde)
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.SessaoRtdCom(VIA_TRYD7)
    assert str(erro.value) == rtd.MOTIVO_STDDE_FECHADO
    assert pywin32.chamadas_create == []


def test_sessao_do_tryd8_nao_confere_o_stdde(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    pywin32.objeto_criado = ServidorRtdFalso()
    monkeypatch.setattr(rtd, "verificar_stdde", _nao_deveria_tocar)
    sessao = rtd.SessaoRtdCom(VIA_TRYD8)
    assert sessao.topico("PETR4", "ULT") == ("PETR4_B_0", "ULT")
    assert pywin32.chamadas_create  # criou, sem passar pelo StDde


def test_sessao_sem_via_escolhe_pelo_registro_o_tryd8(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    pywin32.objeto_criado = ServidorRtdFalso()
    registro = _registro_do_tryd8()
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    monkeypatch.setattr(rtd, "verificar_stdde", _nao_deveria_tocar)
    sessao = rtd.SessaoRtdCom()
    assert pywin32.chamadas_create == [(("IID", "{PROGID-RESOLVIDO}"), None, 21, "IDispatch")]
    assert sessao.topico("PETR4", "ULT") == ("PETR4_B_0", "ULT")


def test_sessao_sem_via_escolhe_pelo_registro_o_tryd7(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    pywin32.objeto_criado = ServidorRtdFalso()
    registro = _registro_do_tryd7()
    conferencias: list[str] = []
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    monkeypatch.setattr(rtd, "verificar_stdde", lambda: conferencias.append("stdde"))
    sessao = rtd.SessaoRtdCom()
    assert conferencias == ["stdde"]
    assert pywin32.chamadas_create == [(("IID", CLSID_TRYD7), None, 1, "IDispatch")]
    assert sessao.topico("PETR4", "ULT") == ("COT", "PETR4", "ULT")


def test_sessao_sem_via_utilizavel_vira_erro_com_o_motivo(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    registro = RegistroFalso()
    recebidos: list[object] = []

    def escolher_via(registro_recebido: object) -> str:
        recebidos.append(registro_recebido)
        return MOTIVO_SO_PROFIT

    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    monkeypatch.setattr(vias, "escolher_via", escolher_via)
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.SessaoRtdCom()
    assert str(erro.value) == MOTIVO_SO_PROFIT
    assert recebidos == [registro]
    assert pywin32.chamadas_create == []


def test_sessao_sem_type_library_falha_antes_de_escolher_a_via(
    pywin32: Pywin32Falso, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A falha da type library chega inteira ao motivo do ``Status``: ela vem antes de tudo."""
    monkeypatch.setattr(tryd7, "RegistroWinreg", _nao_deveria_tocar)
    with pytest.raises(rtd.ErroRtd, match="nenhuma type library") as erro:
        rtd.SessaoRtdCom()
    assert TLB_RTDTRADING in str(erro.value)
    assert pywin32.chamadas_create == []


# --------------------------------------------------------------------------- StDde


def _caminhos(processos: dict[str, list[Path]], pedidos: list[str]) -> Callable[[str], list[Path]]:
    """``caminhos_em_execucao`` falso: o nome do executável não diferencia maiúscula."""

    def caminhos(nome: str) -> list[Path]:
        pedidos.append(nome)
        return processos.get(nome.lower(), [])

    return caminhos


@pytest.mark.parametrize(
    ("stdde_roda", "tryd_roda", "porta_responde", "erro", "porta_conferida"),
    [
        (True, True, True, None, 12003),
        (False, True, True, "o StDde.exe do Tryd não está rodando: ative o DDE/RTD no Tryd", None),
        (True, True, False, "a porta 12003 do StDde do Tryd não responde", 12003),
        (True, False, False, "a porta 12002 do StDde do Tryd não responde", 12002),
        (True, False, True, None, 12002),  # sem a pasta do Tryd, não há INI: a porta padrão
    ],
    ids=["ok", "sem_stdde", "porta_recusada", "sem_pasta_e_porta_recusada", "sem_pasta"],
)
def test_verificar_stdde(
    tmp_path: Path,
    stdde_roda: bool,
    tryd_roda: bool,
    porta_responde: bool,
    erro: str | None,
    porta_conferida: int | None,
) -> None:
    processos: dict[str, list[Path]] = {}
    if stdde_roda:
        processos["stdde.exe"] = [tmp_path / "plugins" / "stDde" / "StDde.exe"]
    if tryd_roda:
        processos["tryd.exe"] = [tmp_path / "tryd.exe"]
    pedidos: list[str] = []
    inis_lidos: list[Path] = []
    portas_testadas: list[int] = []

    def ler_ini(caminho: Path) -> tuple[int, str | None]:
        inis_lidos.append(caminho)
        return 12003, None  # o INI diz 12003, não a padrão

    def aceita(porta: int) -> bool:
        portas_testadas.append(porta)
        return porta_responde

    if erro is None:
        rtd.verificar_stdde(_caminhos(processos, pedidos), ler_ini, aceita)
    else:
        with pytest.raises(rtd.ErroRtd) as falha:
            rtd.verificar_stdde(_caminhos(processos, pedidos), ler_ini, aceita)
        assert str(falha.value) == erro
    assert pedidos[0] == "StDde.exe"
    assert inis_lidos == ([tmp_path / INI_RELATIVO] if stdde_roda and tryd_roda else [])
    assert portas_testadas == ([] if porta_conferida is None else [porta_conferida])


def test_verificar_stdde_usa_por_padrao_os_processos_e_a_porta_de_verdade() -> None:
    padroes = {
        nome: parametro.default
        for nome, parametro in inspect.signature(rtd.verificar_stdde).parameters.items()
    }
    assert padroes == {
        "caminhos": tryd7.caminhos_em_execucao,
        "ler_ini": tryd7.ler_ini_stdde_do_arquivo,
        "aceita": tryd7.porta_aceita,
    }


# --------------------------------------------------------------------------- servidor falso


def test_comando_do_servidor_falso_usa_o_modulo_da_ponte() -> None:
    comando = rtd.comando_servidor_falso(r"C:\Python312\python.exe", 2.0)
    assert comando == [
        r"C:\Python312\python.exe",
        "-m",
        "options_ponte",
        "servidor-falso",
        "--segundos",
        "2",
    ]
    assert rtd.comando_servidor_falso("python", 0.5)[-1] == "0.5"


def test_na_ponte_instalada_o_servidor_falso_e_o_proprio_executavel() -> None:
    comando = rtd.comando_servidor_falso(r"C:\App\ponte\PonteTryd.exe", 2.0, frozen=True)
    assert comando == [r"C:\App\ponte\PonteTryd.exe", "servidor-falso", "--segundos", "2"]


def test_servidor_falso_aceita_topico_de_tres_strings(pywin32: Pywin32Falso) -> None:
    """O autoteste do Tryd 7 manda ``("COT", ativo, código)``; o do Tryd 8, duas strings."""
    pywin32.tornar_carregavel(TLB_EXCEL)
    falso = rtd._ServidorFalso(rtd.carregar_tipos())
    assert falso.ConnectData(1, ("COT", "PETR4", "ULT"), True) == (
        1.23,
        ("COT", "PETR4", "ULT"),
        True,
    )
    assert falso.ConnectData(2, ("COT", "PETR4", "HOR"), True)[0] == "PETR4.HOR"
    assert falso.ConnectData(3, ("PETR4_B_0", "OCP"), True)[0] == 1.22


def test_diretorio_do_pacote_e_o_src_que_contem_options_ponte() -> None:
    assert (rtd.DIRETORIO_SRC / "options_ponte" / "rtd.py").is_file()


# --------------------------------------------------------------------------- registro


@pytest.mark.parametrize(
    ("comando", "esperado"),
    [
        (r'"C:\Users\h\Tryd\tryd.exe"', r"C:\Users\h\Tryd\tryd.exe"),
        (r'"C:\Tryd\tryd.exe" /Automation', r"C:\Tryd\tryd.exe"),
        (r"C:\Tryd\tryd.exe /Automation", r"C:\Tryd\tryd.exe"),
        (r"C:\Tryd\rtd.DLL", r"C:\Tryd\rtd.DLL"),
        (r"  C:\Tryd\tryd.exe  ", r"C:\Tryd\tryd.exe"),
        (r"sem-extensao", "sem-extensao"),
    ],
)
def test_arquivo_do_comando_tira_aspas_e_argumentos(comando: str, esperado: str) -> None:
    assert rtd.arquivo_do_comando(comando) == esperado


def test_arquivo_do_comando_expande_variaveis_de_ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAIZ_TRYD", r"C:\Tryd")
    assert rtd.arquivo_do_comando("%RAIZ_TRYD%\\tryd.exe") == r"C:\Tryd\tryd.exe"


def _cabecalho_pe(maquina: int) -> bytes:
    posicao_pe = 0x80
    cabecalho = bytearray(0x100)
    cabecalho[:2] = b"MZ"
    struct.pack_into("<I", cabecalho, 0x3C, posicao_pe)
    cabecalho[posicao_pe : posicao_pe + 4] = b"PE\0\0"
    struct.pack_into("<H", cabecalho, posicao_pe + 4, maquina)
    return bytes(cabecalho)


@pytest.mark.parametrize(
    ("maquina", "esperado"),
    [
        (0x14C, "32 bits (x86)"),
        (0x8664, "64 bits (x64)"),
        (0xAA64, "ARM64"),
        (0x1234, "0x1234"),
    ],
)
def test_arquitetura_pe_le_a_maquina_do_cabecalho(
    tmp_path: Path, maquina: int, esperado: str
) -> None:
    arquivo = tmp_path / "servidor.exe"
    arquivo.write_bytes(_cabecalho_pe(maquina))
    assert rtd.arquitetura_pe(arquivo) == esperado


def test_arquitetura_pe_de_arquivo_que_nao_e_pe_diz_que_nao_reconhece(tmp_path: Path) -> None:
    arquivo = tmp_path / "texto.exe"
    arquivo.write_bytes(b"isto nao e um executavel")
    assert rtd.arquitetura_pe(arquivo) == "formato não reconhecido"

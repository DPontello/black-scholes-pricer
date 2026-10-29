"""Camada COM da ponte — a lógica que não precisa de COM, com um pywin32 falso nos ``sys.modules``.

O que fala de verdade com o Tryd (ProgID/CLSID, type library, RefreshData) só roda no Windows
ou no Wine; a evidência desse trecho é a saída do ``autoteste`` e do ``espiar`` ao vivo, no
relatório da Task 8. Aqui ficam a ordem das type libraries, a escolha ProgID -> CLSID, o formato
do que o ``RefreshData`` devolve, o bombeamento e o parsing do registro.
"""

import struct
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from options_ponte import rtd
from options_ponte.protocolo import CLSID, PROGID

TLB_TRYD = "{EFCFBDCA-78A5-450B-8228-346C4F44D5B8}"
TLB_EXCEL = "{00020813-0000-0000-C000-000000000046}"
IID_SERVIDOR = "{EC0E6191-DB51-11D3-8F3E-00C04F3651B8}"
IID_AVISO = "{A43788C1-D91B-11D3-8F39-00C04F3651B8}"
TYPE_E_LIBNOTREGISTERED = -2147319779
CO_E_CLASSSTRING = -2147221005
REGDB_E_CLASSNOTREG = -2147221164


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
        self.bombeadas = 0
        gencache = SimpleNamespace(EnsureModule=self._ensure_module)
        universal = SimpleNamespace(RegisterInterfaces=self._register_interfaces)
        pythoncom = SimpleNamespace(
            com_error=ErroCom,
            CLSCTX_SERVER=21,
            CLSCTX_LOCAL_SERVER=4,
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
        return "servidor-bruto"

    def _bombear(self) -> None:
        self.bombeadas += 1


@pytest.fixture
def pywin32(monkeypatch: pytest.MonkeyPatch) -> Pywin32Falso:
    return Pywin32Falso(monkeypatch)


# --------------------------------------------------------------------------- type libraries


def test_carregar_tipos_prefere_a_type_library_do_tryd(pywin32: Pywin32Falso) -> None:
    pywin32.tornar_carregavel(TLB_TRYD)
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert (tipos.nome, tipos.guid, tipos.major, tipos.minor) == ("Tryd", TLB_TRYD, 1, 0)
    assert (tipos.iid_servidor, tipos.iid_aviso) == (IID_SERVIDOR, IID_AVISO)
    assert tipos.descartadas == ()
    assert [c[0] for c in pywin32.chamadas_ensure] == [TLB_TRYD]  # a do Excel nem é tentada
    assert pywin32.chamadas_register == [(TLB_TRYD, 0, 1, 0, ["IRtdServer", "IRTDUpdateEvent"])]


def test_carregar_tipos_cai_na_do_excel_e_guarda_o_motivo_da_do_tryd(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert (tipos.nome, tipos.guid, tipos.major, tipos.minor) == ("Excel", TLB_EXCEL, 1, 4)
    ((descricao, motivo),) = tipos.descartadas
    assert "Tryd" in descricao
    assert TLB_TRYD in descricao
    assert "TYPE_E_LIBNOTREGISTERED" in motivo
    assert [c[0] for c in pywin32.chamadas_ensure] == [TLB_TRYD, TLB_EXCEL]


def test_type_library_do_tryd_sem_a_interface_nao_serve_e_cai_na_do_excel(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.tornar_carregavel(TLB_TRYD, {"IRtdServer": IID_SERVIDOR})  # sem IRTDUpdateEvent
    pywin32.tornar_carregavel(TLB_EXCEL)
    tipos = rtd.carregar_tipos()
    assert tipos.nome == "Excel"
    ((_, motivo),) = tipos.descartadas
    assert "IRTDUpdateEvent" in motivo


def test_nenhuma_type_library_vira_erro_que_diz_qual_faltou(pywin32: Pywin32Falso) -> None:
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.carregar_tipos()
    texto = str(erro.value)
    assert "Tryd" in texto
    assert "Excel" in texto
    assert TLB_TRYD in texto
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
    assert rtd.criar_servidor(PROGID, CLSID) == "servidor-bruto"
    assert pywin32.chamadas_create == [(("IID", "{PROGID-RESOLVIDO}"), None, 21, "IDispatch")]


def test_progid_com_co_e_classstring_cai_no_clsid_com_servidor_local(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.progid_resolve_para = None  # o Wine não acha o ProgID registrado só em HKCU
    assert rtd.criar_servidor(PROGID, CLSID) == "servidor-bruto"
    assert pywin32.chamadas_create == [(("IID", CLSID), None, 4, "IDispatch")]


def test_outro_erro_do_progid_nao_cai_no_clsid(pywin32: Pywin32Falso) -> None:
    pywin32.progid_resolve_para = None
    pywin32.erro_do_progid = ErroCom(REGDB_E_CLASSNOTREG, "classe não registrada")
    with pytest.raises(rtd.ErroRtd, match="classe não registrada"):
        rtd.criar_servidor(PROGID, CLSID)
    assert pywin32.chamadas_create == []


def test_falha_ao_criar_o_servidor_vira_erro_que_diz_como_foi_criado(
    pywin32: Pywin32Falso,
) -> None:
    pywin32.progid_resolve_para = None
    pywin32.erro_ao_criar = ErroCom(-2147023174, "O servidor RPC não está disponível")
    with pytest.raises(rtd.ErroRtd) as erro:
        rtd.criar_servidor(PROGID, CLSID)
    assert CLSID in str(erro.value)
    assert "servidor RPC" in str(erro.value)
    assert "diagnostico" in str(erro.value)


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

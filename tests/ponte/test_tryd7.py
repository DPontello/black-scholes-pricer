"""Tryd 7 na ponte — registro, pasta do Tryd, ``StDde.ini`` e porta, tudo por falsos.

Nada aqui toca o registro, os processos nem o PowerShell de verdade: o registro entra pelo
``RegistroFalso`` (e, para o ``RegistroWinreg``, por um ``winreg`` falso nos ``sys.modules``), os
processos e o PowerShell por funções injetadas, os arquivos por ``tmp_path``.
"""

import socket
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from types import ModuleType, TracebackType
from typing import Self, cast

import pytest

from options_ponte import rtd, tryd7
from options_ponte.protocolo import CLSID
from options_ponte.tryd7 import (
    CATEGORIA_NET,
    CLASSE_TRYD7,
    PORTA_STDDE_PADRAO,
    RUNTIME_TRYD7,
    RegistroWinreg,
    chaves_tryd7,
    codebase,
    desregistrar,
    identidade_do_assembly,
    ler_ini_stdde,
    ler_ini_stdde_do_arquivo,
    pasta_do_tryd,
    porta_aceita,
    registrar,
)
from options_ponte.vias import CLSID_TRYD7, PROGID_TRYD7, Raiz, Visao
from tests.ponte.registro_falso import RegistroFalso

IDENTIDADE = "StRtd, Version=1.13.0.0, Culture=neutral, PublicKeyToken=cad2126db594d9d0"
DLL_MARIA = PureWindowsPath(
    "C:/Users/Maria Silva/AppData/Roaming/Tryd/Tryd/plugins/stDde/StRtd.dll"
)
CODEBASE_MARIA = "file:///C:/Users/Maria Silva/AppData/Roaming/Tryd/Tryd/plugins/stDde/StRtd.dll"
CLASSES = "software\\classes\\"
VISOES: tuple[Visao, ...] = (64, 32)


# --------------------------------------------------------------------------- codebase e chaves


def test_codebase_mantem_espaco_e_acento() -> None:
    assert codebase(DLL_MARIA) == CODEBASE_MARIA
    com_acento = PureWindowsPath("C:/Users/Maria/Programação/Tryd/plugins/stDde/StRtd.dll")
    assert codebase(com_acento) == "file:///C:/Users/Maria/Programação/Tryd/plugins/stDde/StRtd.dll"


def test_chaves_tryd7_tem_o_que_o_regasm_grava() -> None:
    clsid = f"CLSID\\{CLSID_TRYD7}"
    inproc = f"{clsid}\\InprocServer32"
    esperado = [
        ("Tryd.RtdServer", "", CLASSE_TRYD7),
        ("Tryd.RtdServer\\CLSID", "", CLSID_TRYD7),
        (clsid, "", CLASSE_TRYD7),
        (f"{clsid}\\ProgId", "", PROGID_TRYD7),
        (inproc, "", "mscoree.dll"),
        (inproc, "ThreadingModel", "Both"),
        (inproc, "Class", CLASSE_TRYD7),
        (inproc, "Assembly", IDENTIDADE),
        (inproc, "RuntimeVersion", RUNTIME_TRYD7),
        (inproc, "CodeBase", CODEBASE_MARIA),
        (f"{inproc}\\1.13.0.0", "Class", CLASSE_TRYD7),
        (f"{inproc}\\1.13.0.0", "Assembly", IDENTIDADE),
        (f"{inproc}\\1.13.0.0", "RuntimeVersion", RUNTIME_TRYD7),
        (f"{inproc}\\1.13.0.0", "CodeBase", CODEBASE_MARIA),
        (f"{clsid}\\Implemented Categories\\{CATEGORIA_NET}", "", ""),
    ]
    assert sorted(chaves_tryd7(DLL_MARIA, IDENTIDADE)) == sorted(esperado)


def test_chaves_tryd7_recusa_identidade_sem_versao() -> None:
    with pytest.raises(ValueError, match="StRtd, Version=x"):
        chaves_tryd7(DLL_MARIA, "StRtd, Version=x")


def test_constantes_do_tryd7() -> None:
    assert CLASSE_TRYD7 == "StRtd.Controlador.StRtdServer"
    assert RUNTIME_TRYD7 == "v2.0.50727"
    assert CATEGORIA_NET == "{62C8FE65-4EBB-45E7-B440-6E39B2CDBF29}"
    assert PORTA_STDDE_PADRAO == 12002
    assert tryd7.DLL_RELATIVA.parts == ("plugins", "stDde", "StRtd.dll")
    assert tryd7.INI_RELATIVO.parts == ("plugins", "stDde", "StDde.ini")


# --------------------------------------------------------------------------- registrar


def test_registrar_grava_so_em_hkcu_nas_duas_visoes() -> None:
    registro = RegistroFalso()
    descricoes = registrar(registro, DLL_MARIA, IDENTIDADE)
    chaves = chaves_tryd7(DLL_MARIA, IDENTIDADE)
    caminhos = {CLASSES + caminho.lower() for caminho, _, _ in chaves}
    for visao in VISOES:
        gravado = registro.gravado("HKCU", visao)
        assert set(gravado) == caminhos
        assert gravado[CLASSES + "tryd.rtdserver"] == {"": CLASSE_TRYD7}
        inproc = gravado[f"{CLASSES}clsid\\{CLSID_TRYD7.lower()}\\inprocserver32"]
        assert inproc[""] == "mscoree.dll"
        assert inproc["CodeBase"] == CODEBASE_MARIA
        assert not any(CLSID.lower() in caminho for caminho in gravado)  # nada do RTDTrading
    for raiz in ("HKCR", "HKLM"):
        for visao in VISOES:
            assert registro.gravado(raiz, visao) == {}
    assert len(descricoes) == 2 * len(chaves)
    assert all(d.startswith("HKCU\\Software\\Classes\\") for d in descricoes)
    assert sum(f"CodeBase = {CODEBASE_MARIA}" in d for d in descricoes) == 4  # 2 chaves x 2 visões
    assert sum("[32 bits]" in d for d in descricoes) == len(chaves)


def test_registrar_de_novo_sobrescreve_sem_duplicar() -> None:
    registro = RegistroFalso()
    registrar(registro, DLL_MARIA, IDENTIDADE)
    antes = {visao: registro.gravado("HKCU", visao) for visao in VISOES}
    registrar(registro, DLL_MARIA, IDENTIDADE)
    assert {visao: registro.gravado("HKCU", visao) for visao in VISOES} == antes


def test_desregistrar_apaga_so_o_que_o_registrar_grava() -> None:
    registro = RegistroFalso()
    registrar(registro, DLL_MARIA, IDENTIDADE)
    rtdtrading = f"Software\\Classes\\CLSID\\{CLSID}\\LocalServer32"
    for visao in VISOES:
        registro.definir("HKCU", "Software\\Classes\\Outro", "x", visao=visao)
        registro.definir("HKCU", rtdtrading, "C:\\Tryd\\tryd.exe", visao=visao)
        registro.definir("HKLM", "Software\\Classes\\Tryd.RtdServer", "de outro", visao=visao)
    registro.definir("HKLM", rtdtrading, "C:\\Profit\\profitchart.exe", visao=64)

    descricoes = desregistrar(registro)
    desregistrar(registro)  # de novo: ausente não é erro

    for visao in VISOES:
        assert set(registro.gravado("HKCU", visao)) == {
            CLASSES + "outro",
            f"{CLASSES}clsid\\{CLSID.lower()}\\localserver32",
        }
        assert set(registro.gravado("HKLM", visao)) >= {CLASSES + "tryd.rtdserver"}
    assert registro.ler("HKLM", rtdtrading, "", 64) == "C:\\Profit\\profitchart.exe"
    assert len(descricoes) == 4  # 2 chaves x 2 visões
    assert sum("Tryd.RtdServer" in d for d in descricoes) == 2
    assert sum(CLSID_TRYD7 in d for d in descricoes) == 2
    assert all(d.startswith("HKCU\\Software\\Classes\\") for d in descricoes)


# --------------------------------------------------------------------------- identidade


def test_identidade_do_assembly_le_a_saida_do_powershell() -> None:
    comandos: list[list[str]] = []

    def executar(comando: list[str]) -> str:
        comandos.append(comando)
        return IDENTIDADE + "\r\n"

    assert identidade_do_assembly(Path("C:/Tryd/StRtd.dll"), executar) == IDENTIDADE
    assert comandos == [
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "[System.Reflection.AssemblyName]::GetAssemblyName('C:/Tryd/StRtd.dll').FullName",
        ]
    ]


@pytest.mark.parametrize(
    ("aspa", "dobrada"), [("'", "''"), ("\u2019", "\u2019\u2019"), ("\u2018", "\u2018\u2018")]
)
def test_identidade_do_assembly_escapa_a_aspa_do_caminho(aspa: str, dobrada: str) -> None:
    comandos: list[list[str]] = []

    def executar(comando: list[str]) -> str:
        comandos.append(comando)
        return IDENTIDADE

    identidade_do_assembly(Path(f"C:/Users/O{aspa}Brien/StRtd.dll"), executar)
    assert f"GetAssemblyName('C:/Users/O{dobrada}Brien/StRtd.dll')" in comandos[0][3]


def test_identidade_do_assembly_recusa_saida_que_nao_e_a_do_strtd() -> None:
    with pytest.raises(ValueError, match=r"Outra, Version=1\.0\.0\.0"):
        identidade_do_assembly(Path("C:/x/StRtd.dll"), lambda _: "Outra, Version=1.0.0.0\r\n")
    with pytest.raises(ValueError, match="Exception calling"):
        identidade_do_assembly(Path("C:/x/StRtd.dll"), lambda _: "Exception calling GetAssembly")


@pytest.mark.parametrize(
    "erro",
    [
        subprocess.CalledProcessError(1, "powershell", output="", stderr="não é um assembly"),
        subprocess.TimeoutExpired("powershell", 30),
        FileNotFoundError("powershell"),
    ],
)
def test_identidade_do_assembly_vira_value_error_se_o_powershell_falha(erro: Exception) -> None:
    def executar(_comando: list[str]) -> str:
        raise erro

    with pytest.raises(ValueError, match=r"StRtd\.dll"):
        identidade_do_assembly(Path("C:/x/StRtd.dll"), executar)


def test_powershell_roda_sem_janela_e_com_prazo(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas: list[tuple[list[str], dict[str, object]]] = []

    def run(comando: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        chamadas.append((comando, kwargs))
        return subprocess.CompletedProcess(comando, 0, stdout="saída\r\n", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    assert tryd7._powershell(["powershell", "-NoProfile"]) == "saída\r\n"
    (comando, kwargs), *resto = chamadas
    assert (comando, resto) == (["powershell", "-NoProfile"], [])
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["check"] is True
    assert isinstance(kwargs["timeout"], int | float)
    assert kwargs["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --------------------------------------------------------------------------- StDde.ini


@pytest.mark.parametrize(
    ("texto", "esperado"),
    [
        ("[SOCKET_SERVER]\nPORTA=12003\n[GERAL]\nREGISTROU=False\n", (12003, "False")),
        ("[GERAL]\nNOME=x\n", (PORTA_STDDE_PADRAO, None)),  # sem a seção
        ("[SOCKET_SERVER]\nHOST=127.0.0.1\n", (PORTA_STDDE_PADRAO, None)),  # sem a chave da porta
        ("[SOCKET_SERVER]\nPORTA=abc\n[GERAL]\nREGISTROU=False\n", (PORTA_STDDE_PADRAO, "False")),
        ("[SOCKET_SERVER]\nPORTA=70000\n", (PORTA_STDDE_PADRAO, None)),  # fora de 1 a 65535
        ("[SOCKET_SERVER]\nPORTA=0\n", (PORTA_STDDE_PADRAO, None)),
        ("[GERAL]\nPORTA=1234\n", (PORTA_STDDE_PADRAO, None)),  # porta fora da seção do socket
        ("[SOCKET_SERVER]\nPORTA=abc\nPORT=12004\nPORTAL=12005\n", (12004, None)),  # 1ª inteira
        ("[socket_server]\nport = 12010\nregistrou=True\n", (12010, "True")),
        ("[SOCKET_SERVER]\nPORTA=12003\nREGISTROU=True\n", (12003, "True")),  # em qualquer seção
        ("[SOCKET_SERVER]\nlinha solta\nPORTA=12003\n", (12003, None)),
        ("[SOCKET_SERVER]\nPORTA\n[GERAL]\nREGISTROU\n", (PORTA_STDDE_PADRAO, None)),  # sem valor
        ("[SOCKET_SERVER]\nPORTA=12003\n[SOCKET_SERVER]\nPORTA=12099\n", (12099, None)),
        ("", (PORTA_STDDE_PADRAO, None)),
        ("isto nem é um INI", (PORTA_STDDE_PADRAO, None)),
        ("PORTA=12003\n", (PORTA_STDDE_PADRAO, None)),  # chave antes de qualquer seção
        ("[SOCKET_SERVER]\nPORTA=%(x)s\n", (PORTA_STDDE_PADRAO, None)),  # sem interpolação
    ],
)
def test_ini_do_stdde(texto: str, esperado: tuple[int, str | None]) -> None:
    assert ler_ini_stdde(texto) == esperado


@pytest.mark.parametrize(
    "conteudo",
    [
        "[SOCKET_SERVER]\nPORTA=12005\n[GERAL]\nUSUARIO=João\nREGISTROU=True\n".encode(),
        "\ufeff[SOCKET_SERVER]\nPORTA=12005\n[GERAL]\nUSUARIO=João\nREGISTROU=True\n".encode(),
        "[SOCKET_SERVER]\nPORTA=12005\n[GERAL]\nUSUARIO=João\nREGISTROU=True\n".encode("cp1252"),
        # 0x81 não existe no cp1252: ainda assim lê
        b"[SOCKET_SERVER]\nPORTA=12005\n[GERAL]\nUSUARIO=Jo\x81o\nREGISTROU=True\n",
    ],
    ids=["utf-8", "utf-8 com BOM", "cp1252 com acento", "cp1252 com byte indefinido"],
)
def test_ini_do_stdde_do_arquivo_le_utf8_e_cp1252(tmp_path: Path, conteudo: bytes) -> None:
    ini = tmp_path / "StDde.ini"
    ini.write_bytes(conteudo)
    assert ler_ini_stdde_do_arquivo(ini) == (12005, "True")


def test_ini_do_stdde_ausente_ou_ilegivel_da_a_porta_padrao(tmp_path: Path) -> None:
    assert ler_ini_stdde_do_arquivo(tmp_path / "StDde.ini") == (PORTA_STDDE_PADRAO, None)
    assert ler_ini_stdde_do_arquivo(tmp_path) == (PORTA_STDDE_PADRAO, None)  # é uma pasta


# --------------------------------------------------------------------------- pasta e porta


def test_pasta_do_tryd_e_a_do_tryd_exe_em_execucao() -> None:
    pedidos: list[str] = []

    def com_tryd(nome_exe: str) -> list[Path]:
        pedidos.append(nome_exe)
        return [Path("C:/Tryd/tryd.exe")]

    assert pasta_do_tryd(com_tryd) == Path("C:/Tryd")
    assert pedidos == ["tryd.exe"]
    assert pasta_do_tryd(lambda _: []) is None


@pytest.mark.skipif(sys.platform == "win32", reason="fora do Windows não há Toolhelp32")
def test_fora_do_windows_nao_ha_processos_nem_pasta() -> None:
    assert tryd7.caminhos_em_execucao("tryd.exe") == []
    assert tryd7.pids_do_executavel("tryd.exe") == frozenset()
    assert rtd.processos_tryd() == frozenset()
    assert pasta_do_tryd() is None


def test_porta_aceita() -> None:
    with socket.create_server(("127.0.0.1", 0)) as escuta:
        assert porta_aceita(int(escuta.getsockname()[1])) is True
        porta_fechada = int(escuta.getsockname()[1])
    assert porta_aceita(porta_fechada, espera_s=0.5) is False  # fechou ao sair do with


# --------------------------------------------------------------------------- RegistroWinreg


class _ChaveFalsa:
    def __init__(self, raiz: int, visao: int, caminho: str) -> None:
        self.raiz, self.visao, self.caminho = raiz, visao, caminho

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        tipo: type[BaseException] | None,
        erro: BaseException | None,
        rastro: TracebackType | None,
    ) -> None:
        return None


class WinregFalso:
    """O ``winreg`` do Windows em memória: chaves por ``(raiz, visão, caminho em minúsculas)``."""

    HKEY_CLASSES_ROOT = 1
    HKEY_CURRENT_USER = 2
    HKEY_LOCAL_MACHINE = 3
    KEY_READ = 0x20019
    KEY_WRITE = 0x20006
    KEY_WOW64_64KEY = 0x100
    KEY_WOW64_32KEY = 0x200
    REG_SZ = 1
    REG_DWORD = 4

    def __init__(self) -> None:
        self.chaves: dict[tuple[int, int, str], dict[str, tuple[object, int]]] = {}

    def _chave(self, raiz: int, caminho: str, acesso: int) -> tuple[int, int, str]:
        visao = acesso & (self.KEY_WOW64_32KEY | self.KEY_WOW64_64KEY)
        assert visao in (self.KEY_WOW64_32KEY, self.KEY_WOW64_64KEY), "faltou a visão"
        return raiz, visao, caminho.lower()

    def OpenKey(self, raiz: int, caminho: str, reservado: int, acesso: int) -> _ChaveFalsa:
        chave = self._chave(raiz, caminho, acesso)
        if chave not in self.chaves:
            raise FileNotFoundError(2, "chave ausente", caminho)
        return _ChaveFalsa(*chave)

    def CreateKeyEx(self, raiz: int, caminho: str, reservado: int, acesso: int) -> _ChaveFalsa:
        _, visao, minusculo = self._chave(raiz, caminho, acesso)
        partes = minusculo.split("\\")
        for fim in range(1, len(partes) + 1):  # cria também as chaves do meio
            self.chaves.setdefault((raiz, visao, "\\".join(partes[:fim])), {})
        return _ChaveFalsa(raiz, visao, minusculo)

    def SetValueEx(
        self, chave: _ChaveFalsa, nome: str, reservado: int, tipo: int, valor: object
    ) -> None:
        self.chaves[(chave.raiz, chave.visao, chave.caminho)][nome.lower()] = (valor, tipo)

    def QueryValueEx(self, chave: _ChaveFalsa, nome: str) -> tuple[object, int]:
        valores = self.chaves[(chave.raiz, chave.visao, chave.caminho)]
        if nome.lower() not in valores:
            raise FileNotFoundError(2, "valor ausente", nome)
        return valores[nome.lower()]

    def _filhas(self, chave: _ChaveFalsa) -> list[str]:
        prefixo = chave.caminho + "\\"
        return [
            caminho.removeprefix(prefixo)
            for (raiz, visao, caminho) in self.chaves
            if (raiz, visao) == (chave.raiz, chave.visao)
            and caminho.startswith(prefixo)
            and "\\" not in caminho.removeprefix(prefixo)
        ]

    def QueryInfoKey(self, chave: _ChaveFalsa) -> tuple[int, int, int]:
        return (
            len(self._filhas(chave)),
            len(self.chaves[(chave.raiz, chave.visao, chave.caminho)]),
            0,
        )

    def EnumKey(self, chave: _ChaveFalsa, indice: int) -> str:
        return self._filhas(chave)[indice]

    def DeleteKeyEx(self, raiz: int, caminho: str, acesso: int, reservado: int = 0) -> None:
        chave = self._chave(raiz, caminho, acesso)
        if chave not in self.chaves:
            raise FileNotFoundError(2, "chave ausente", caminho)
        if self._filhas(_ChaveFalsa(*chave)):
            raise OSError(145, "a chave tem subchaves", caminho)  # como o Windows
        del self.chaves[chave]


@pytest.fixture
def winreg_falso(monkeypatch: pytest.MonkeyPatch) -> WinregFalso:
    falso = WinregFalso()
    monkeypatch.setitem(sys.modules, "winreg", cast(ModuleType, falso))
    return falso


def _chaves_do(falso: WinregFalso, raiz: int, visao: int) -> set[str]:
    return {c for (r, v, c) in falso.chaves if (r, v) == (raiz, visao)}


def test_registro_winreg_grava_e_le_por_visao(winreg_falso: WinregFalso) -> None:
    registro = RegistroWinreg()
    registro.gravar("HKCU", "Software\\Classes\\Tryd.RtdServer\\CLSID", "", CLSID_TRYD7, 32)
    registro.gravar("HKCU", "Software\\Classes\\Tryd.RtdServer\\CLSID", "Nome", "x", 32)
    chave = (winreg_falso.HKEY_CURRENT_USER, winreg_falso.KEY_WOW64_32KEY)
    assert winreg_falso.chaves[(*chave, "software\\classes\\tryd.rtdserver\\clsid")] == {
        "": (CLSID_TRYD7, winreg_falso.REG_SZ),
        "nome": ("x", winreg_falso.REG_SZ),
    }
    assert "software\\classes\\tryd.rtdserver" in _chaves_do(winreg_falso, *chave)  # as do meio
    ler = registro.ler
    assert ler("HKCU", "Software\\Classes\\Tryd.RtdServer\\CLSID", "", 32) == CLSID_TRYD7
    assert ler("HKCU", "Software\\Classes\\Tryd.RtdServer\\CLSID", "", 64) is None  # outra visão
    assert ler("HKLM", "Software\\Classes\\Tryd.RtdServer\\CLSID", "", 32) is None  # outra raiz


def test_registro_winreg_ler_devolve_texto_ou_none(winreg_falso: WinregFalso) -> None:
    chave = (winreg_falso.HKEY_LOCAL_MACHINE, winreg_falso.KEY_WOW64_64KEY, "software\\x")
    winreg_falso.chaves[chave] = {"dword": (1, winreg_falso.REG_DWORD), "": ("padrão", 1)}
    registro = RegistroWinreg()
    assert registro.ler("HKLM", "Software\\X", "dword", 64) == "1"
    assert registro.ler("HKLM", "Software\\X", "", 64) == "padrão"
    assert registro.ler("HKLM", "Software\\X", "faltando", 64) is None  # valor ausente
    assert registro.ler("HKLM", "Software\\Y", "", 64) is None  # chave ausente


@pytest.mark.parametrize(
    ("raiz", "constante"),
    [("HKCR", 1), ("HKCU", 2), ("HKLM", 3)],
)
def test_registro_winreg_usa_a_raiz_pedida(
    winreg_falso: WinregFalso, raiz: Raiz, constante: int
) -> None:
    RegistroWinreg().gravar(raiz, "A", "", "x", 64)
    assert _chaves_do(winreg_falso, constante, winreg_falso.KEY_WOW64_64KEY) == {"a"}


def test_registro_winreg_apaga_de_baixo_para_cima_e_poupa_o_resto(
    winreg_falso: WinregFalso,
) -> None:
    registro = RegistroWinreg()
    for visao in VISOES:
        for caminho in ("A\\B\\C\\D", "A\\B\\E", "A\\BB"):
            registro.gravar("HKCU", caminho, "", "x", visao)
    registro.apagar_arvore("HKCU", "A\\B", 64)  # o falso recusa apagar chave com subchaves
    assert _chaves_do(winreg_falso, 2, winreg_falso.KEY_WOW64_64KEY) == {"a", "a\\bb"}
    assert _chaves_do(winreg_falso, 2, winreg_falso.KEY_WOW64_32KEY) >= {"a\\b", "a\\b\\c\\d"}
    registro.apagar_arvore("HKCU", "A\\B", 64)  # ausente não é erro
    registro.apagar_arvore("HKCU", "Nao\\Existe", 32)


def test_registro_winreg_nao_importa_o_winreg_ao_construir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "winreg", None)  # o import falharia aqui
    RegistroWinreg()

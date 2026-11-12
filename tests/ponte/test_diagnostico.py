"""O diagnóstico das duas vias RTD — com registro, processos, porta e arquivos falsos."""

import io
import sys
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any

import pytest

from options_ponte import rtd, tryd7, vias
from options_ponte.protocolo import CLSID
from options_ponte.tryd7 import CLASSE_TRYD7, DLL_RELATIVA, INI_RELATIVO, RUNTIME_TRYD7
from options_ponte.vias import (
    CLSID_TRYD7,
    MOTIVO_SEM_RTD,
    MOTIVO_SO_PROFIT,
    MOTIVO_TRYD7_OUTRA_VISAO,
    VISAO_DO_PROCESSO,
    Raiz,
    Visao,
)
from tests.ponte.registro_falso import RegistroFalso

IDENTIDADE = "StRtd, Version=1.13.0.0, Culture=neutral, PublicKeyToken=cad2126db594d9d0"
PASTA_TRYD = Path("C:/Users/Maria Silva/AppData/Roaming/Tryd/Tryd")
DLL = PureWindowsPath("C:/Users/Maria Silva/AppData/Roaming/Tryd/Tryd/plugins/stDde/StRtd.dll")
TRYD_EXE = "C:\\Users\\Maria Silva\\AppData\\Roaming\\Tryd\\Tryd\\tryd.exe"
PROFIT_EXE = "C:\\Profit\\profitchart.exe -Embedding"
DOTNET35 = "SOFTWARE\\Microsoft\\NET Framework Setup\\NDP\\v3.5"

AVISO_DO_PROFIT = (
    "[aviso] RTDTrading.RtdServer aponta para o profitchart.exe: "
    "isso é o RTD do Profit, não do Tryd"
)
DICA_DO_REGISTROU = (
    " (o StDde não se registra sem administrador; o 'PonteTryd.exe registrar' resolve)"
)
SEM_DOTNET = (
    '[falta] .NET 3.5 (CLR v2) não instalado: ative em "Ativar ou desativar recursos do Windows"'
)
SEM_STDDE = "[falta] StDde.exe não está rodando (ative o DDE/RTD no Tryd)"


@dataclass
class Ambiente:
    """O que o diagnóstico consulta fora do registro: processos, porta, INI e arquivos."""

    processos: dict[str, list[Path]] = field(default_factory=dict)
    portas: set[int] = field(default_factory=set)
    inis: dict[Path, tuple[int, str | None]] = field(default_factory=dict)
    arquivos: set[Path] = field(default_factory=set)
    inis_lidos: list[Path] = field(default_factory=list)
    portas_testadas: list[int] = field(default_factory=list)

    def caminhos(self, nome: str) -> list[Path]:
        return self.processos.get(nome.lower(), [])

    def aceita(self, porta: int) -> bool:
        self.portas_testadas.append(porta)
        return porta in self.portas

    def ler_ini(self, caminho: Path) -> tuple[int, str | None]:
        """Como o real: INI ausente dá a porta padrão e ``REGISTROU`` desconhecido."""
        self.inis_lidos.append(caminho)
        return self.inis.get(caminho, (tryd7.PORTA_STDDE_PADRAO, None))

    def existe(self, caminho: Path) -> bool:
        return caminho in self.arquivos


def _ambiente_da_maria() -> Ambiente:
    """O PC dela: Tryd 7 aberto, StDde no ar na porta 12003, ``REGISTROU=False``, DLL no lugar."""
    return Ambiente(
        processos={"tryd.exe": [PASTA_TRYD / "tryd.exe"], "stdde.exe": [PASTA_TRYD / "stDde.exe"]},
        portas={12003},
        inis={PASTA_TRYD / INI_RELATIVO: (12003, "False")},
        arquivos={PASTA_TRYD / DLL_RELATIVA},
    )


def _rodar(
    registro: RegistroFalso, ambiente: Ambiente | None = None, visao: Visao = 32
) -> tuple[int, str]:
    """``(faltas, saída)`` do ``diagnosticar_vias``."""
    ambiente = ambiente if ambiente is not None else Ambiente()
    saida = io.StringIO()
    faltas = rtd.diagnosticar_vias(
        registro,
        visao,
        caminhos=ambiente.caminhos,
        aceita=ambiente.aceita,
        ler_ini=ambiente.ler_ini,
        arquivo_existe=ambiente.existe,
        saida=saida,
    )
    return faltas, saida.getvalue()


def _classe(registro: RegistroFalso, raiz: Raiz, clsid: str, servidor: str, comando: str) -> None:
    """``CLSID\\{clsid}\\{servidor}`` em ``HKCU``/``HKLM``, na visão de 32 bits."""
    registro.definir(raiz, f"Software\\Classes\\CLSID\\{clsid}\\{servidor}", comando, visao=32)


def _com_tryd8(registro: RegistroFalso) -> RegistroFalso:
    _classe(registro, "HKCU", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation')
    return registro


def _com_profit(registro: RegistroFalso) -> RegistroFalso:
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE)
    return registro


def _com_tryd7(registro: RegistroFalso) -> RegistroFalso:
    """O que o ``registrar`` grava, em ``HKCU``, nas duas visões."""
    tryd7.registrar(registro, DLL, IDENTIDADE)
    return registro


def _com_dotnet(registro: RegistroFalso) -> RegistroFalso:
    registro.definir("HKLM", DOTNET35, "1", nome="Install", visao=64)
    return registro


def _linha_do_tryd7(visao: Visao) -> str:
    return (
        f"[ok] Tryd.RtdServer na visão de {visao} bits: mscoree.dll, Class {CLASSE_TRYD7}, "
        f"Assembly {IDENTIDADE}, RuntimeVersion {RUNTIME_TRYD7}, CodeBase {tryd7.codebase(DLL)}"
    )


# --------------------------------------------------------------------------- os quatro cenários


def test_diagnostico_tryd8_ok() -> None:
    faltas, texto = _rodar(_com_tryd8(RegistroFalso()))
    assert "[ok] RTDTrading.RtdServer -> tryd.exe (Tryd 8)" in texto
    assert "[ok] a ponte vai usar: Tryd 8 (RTDTrading)" in texto
    assert "[aviso] RTDTrading.RtdServer aponta para o profitchart.exe" not in texto
    assert faltas == 0


def test_diagnostico_so_profit() -> None:
    faltas, texto = _rodar(_com_profit(RegistroFalso()))
    assert AVISO_DO_PROFIT in texto
    assert "[falta] Tryd.RtdServer não registrado na visão de 32 bits" in texto
    assert f"[falta] nenhuma via: {MOTIVO_SO_PROFIT}" in texto
    assert "a ponte vai usar" not in texto
    assert faltas == 1


def test_diagnostico_profit_e_tryd7_registrado() -> None:
    registro = _com_dotnet(_com_tryd7(_com_profit(RegistroFalso())))
    faltas, texto = _rodar(registro, _ambiente_da_maria())
    assert AVISO_DO_PROFIT in texto
    assert _linha_do_tryd7(32) in texto
    assert _linha_do_tryd7(64) in texto
    assert "[ok] StRtd.dll existe" in texto
    assert "[ok] .NET 3.5 (CLR v2) instalado" in texto
    assert "[ok] StDde.exe rodando" in texto
    assert "[ok] porta 12003 do StDde respondendo" in texto
    assert f"[info] StDde.ini: REGISTROU=False{DICA_DO_REGISTROU}" in texto
    assert "[ok] a ponte vai usar: Tryd 7 (Tryd.RtdServer)" in texto
    assert faltas == 0


def test_diagnostico_nada() -> None:
    faltas, texto = _rodar(RegistroFalso())
    assert "[info] RTDTrading.RtdServer não registrado" in texto
    assert f"[falta] nenhuma via: {MOTIVO_SEM_RTD}" in texto
    assert faltas == 1


# --------------------------------------------------------------------------- o dono do RTDTrading


def test_o_tryd8_registrado_so_na_outra_visao_ainda_e_o_dono() -> None:
    """O servidor fora do processo atravessa as visões (Ruling 6): o diagnóstico acha igual."""
    registro = RegistroFalso()
    registro.definir(
        "HKLM",
        f"Software\\Classes\\CLSID\\{CLSID}\\LocalServer32",
        f'"{TRYD_EXE}" /automation',
        visao=64,
    )
    faltas, texto = _rodar(registro)
    assert "[ok] RTDTrading.RtdServer -> tryd.exe (Tryd 8)" in texto
    assert "[ok] a ponte vai usar: Tryd 8 (RTDTrading)" in texto
    assert faltas == 0


def test_dono_que_nao_e_o_tryd_nem_o_profit_aparece_pelo_nome() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", "C:\\Outro\\Coisa.exe /automation")
    faltas, texto = _rodar(registro)
    assert "[aviso] RTDTrading.RtdServer aponta para coisa.exe, que não é o tryd.exe" in texto
    assert f"[falta] nenhuma via: {MOTIVO_SEM_RTD}" in texto
    assert faltas == 1


# --------------------------------------------------------------------------- o Tryd 7 por visão


def test_tryd7_registrado_so_na_outra_visao_mostra_as_duas_linhas_e_diz_para_registrar() -> None:
    registro = RegistroFalso()
    registro.definir(
        "HKCU", f"Software\\Classes\\CLSID\\{CLSID_TRYD7}\\InprocServer32", "mscoree.dll", visao=64
    )
    faltas, texto = _rodar(registro)
    assert "[ok] Tryd.RtdServer na visão de 64 bits: mscoree.dll" in texto
    assert "[falta] Tryd.RtdServer não registrado na visão de 32 bits" in texto
    assert f"[falta] nenhuma via: {MOTIVO_TRYD7_OUTRA_VISAO.format(outra=64, visao=32)}" in texto
    assert faltas == 1


def test_o_diagnostico_segue_o_predicado_da_escolha_para_dizer_registrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ok``/``falta`` vêm de ``vias.tryd7_registrado``, o mesmo que ``escolher_via`` usa."""
    monkeypatch.setattr(vias, "tryd7_registrado", lambda registro, visao: visao == 64)
    _, texto = _rodar(RegistroFalso())
    assert "[ok] Tryd.RtdServer na visão de 64 bits: mscoree.dll" in texto
    assert "[falta] Tryd.RtdServer não registrado na visão de 32 bits" in texto
    assert f"[falta] nenhuma via: {MOTIVO_TRYD7_OUTRA_VISAO.format(outra=64, visao=32)}" in texto


def test_tryd7_com_outro_servidor_nao_conta_como_registrado() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "C:\\outro\\coisa.dll")
    _, texto = _rodar(registro)
    assert "[falta] Tryd.RtdServer não registrado na visão de 32 bits" in texto
    assert "[falta] Tryd.RtdServer não registrado na visão de 64 bits" in texto


def test_o_codebase_vira_o_caminho_sem_o_prefixo_file_e_o_arquivo_e_conferido() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    conferidos: list[Path] = []

    def existe(caminho: Path) -> bool:
        conferidos.append(caminho)
        return ambiente.existe(caminho)

    saida = io.StringIO()
    rtd.diagnosticar_vias(
        registro,
        32,
        caminhos=ambiente.caminhos,
        aceita=ambiente.aceita,
        ler_ini=ambiente.ler_ini,
        arquivo_existe=existe,
        saida=saida,
    )
    assert PASTA_TRYD / DLL_RELATIVA in conferidos
    assert all(not str(caminho).lower().startswith("file:") for caminho in conferidos)


def test_diagnostico_codebase_para_arquivo_que_nao_existe() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    ambiente.arquivos.clear()
    faltas, texto = _rodar(registro, ambiente)
    assert (
        f"[falta] o CodeBase aponta para um arquivo que não existe: {PASTA_TRYD / DLL_RELATIVA}"
        in texto
    )
    assert "StRtd.dll existe" not in texto
    assert "[ok] a ponte vai usar: Tryd 7 (Tryd.RtdServer)" in texto
    assert faltas >= 1


def test_tryd7_sem_codebase_mostra_o_que_ha_e_falta_o_arquivo() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    for visao in (32, 64):
        registro.apagar_arvore(
            "HKCU", f"Software\\Classes\\CLSID\\{CLSID_TRYD7}\\InprocServer32", visao
        )
        registro.definir(
            "HKCU",
            f"Software\\Classes\\CLSID\\{CLSID_TRYD7}\\InprocServer32",
            "mscoree.dll",
            visao=visao,
        )
    faltas, texto = _rodar(registro, _ambiente_da_maria())
    assert (
        "[ok] Tryd.RtdServer na visão de 32 bits: mscoree.dll, Class (ausente), "
        "Assembly (ausente), RuntimeVersion (ausente), CodeBase (ausente)"
    ) in texto
    assert "[falta] sem CodeBase: o registro não diz onde está o StRtd.dll" in texto
    assert "StRtd.dll existe" not in texto
    assert faltas == 1


# --------------------------------------------------------------------------- o .NET 3.5


@pytest.mark.parametrize("instalado", [True, False])
def test_dotnet35_pelo_install_do_hklm_na_visao_de_64_bits(instalado: bool) -> None:
    registro = _com_tryd7(RegistroFalso())
    registro.definir("HKLM", DOTNET35, "1" if instalado else "0", nome="Install", visao=64)
    _, texto = _rodar(registro, _ambiente_da_maria())
    assert ("[ok] .NET 3.5 (CLR v2) instalado" in texto) is instalado
    assert (SEM_DOTNET in texto) is (not instalado)


def test_dotnet35_so_na_visao_de_32_bits_nao_conta() -> None:
    registro = _com_tryd7(RegistroFalso())
    registro.definir("HKLM", DOTNET35, "1", nome="Install", visao=32)
    _, texto = _rodar(registro, _ambiente_da_maria())
    assert SEM_DOTNET in texto


# --------------------------------------------------------------------------- o StDde


def test_stdde_fechado_e_porta_muda() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    del ambiente.processos["stdde.exe"]
    ambiente.portas.clear()
    faltas, texto = _rodar(registro, ambiente)
    assert SEM_STDDE in texto
    assert "[falta] porta 12003 do StDde não responde" in texto
    assert faltas >= 1


@pytest.mark.parametrize(
    ("registrou", "esperado"),
    [
        ("False", f"[info] StDde.ini: REGISTROU=False{DICA_DO_REGISTROU}"),
        ("false", f"[info] StDde.ini: REGISTROU=false{DICA_DO_REGISTROU}"),
        ("True", "[info] StDde.ini: REGISTROU=True\n"),
        (None, "[info] StDde.ini: REGISTROU não encontrado\n"),
    ],
    ids=["False", "false", "True", "sem_a_chave"],
)
def test_registrou_do_stdde_ini(registrou: str | None, esperado: str) -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    ambiente.inis = {PASTA_TRYD / INI_RELATIVO: (12003, registrou)}
    _, texto = _rodar(registro, ambiente)
    assert esperado in texto


def test_stdde_ini_ausente_usa_a_porta_padrao_e_nao_acha_o_registrou() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    ambiente.inis.clear()
    ambiente.portas = {12002}
    faltas, texto = _rodar(registro, ambiente)
    assert ambiente.inis_lidos == [PASTA_TRYD / INI_RELATIVO]
    assert "[ok] porta 12002 do StDde respondendo" in texto
    assert "[info] StDde.ini: REGISTROU não encontrado" in texto
    assert faltas == 0


def test_falha_ao_listar_os_processos_vira_aviso_e_o_diagnostico_segue() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()

    def caminhos(nome: str) -> list[Path]:
        raise OSError("[WinError 5] Acesso negado")

    saida = io.StringIO()
    faltas = rtd.diagnosticar_vias(
        registro,
        32,
        caminhos=caminhos,
        aceita=ambiente.aceita,
        ler_ini=ambiente.ler_ini,
        arquivo_existe=ambiente.existe,
        saida=saida,
    )
    texto = saida.getvalue()
    assert "[aviso] não foi possível listar os processos: [WinError 5] Acesso negado" in texto
    assert "[ok] a ponte vai usar: Tryd 7 (Tryd.RtdServer)" in texto
    assert faltas == 1


def test_sem_o_tryd_aberto_nao_ha_pasta_do_ini_e_vale_a_porta_padrao() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    del ambiente.processos["tryd.exe"]
    ambiente.portas = {12002}
    _, texto = _rodar(registro, ambiente)
    assert ambiente.inis_lidos == []
    assert ambiente.portas_testadas == [12002]
    assert "[ok] porta 12002 do StDde respondendo" in texto
    assert "[info] StDde.ini: REGISTROU não encontrado" in texto


# --------------------------------------------------------------------------- o código de saída


def test_com_o_tryd8_as_faltas_do_tryd7_aparecem_mas_nao_contam() -> None:
    """Um Tryd 8 que funciona não pode dar erro por causa do que só o Tryd 7 precisa."""
    faltas, texto = _rodar(_com_tryd8(RegistroFalso()))
    assert "[falta] Tryd.RtdServer não registrado na visão de 64 bits" in texto
    assert "[falta] Tryd.RtdServer não registrado na visão de 32 bits" in texto
    assert SEM_DOTNET in texto
    assert SEM_STDDE in texto
    assert "[ok] a ponte vai usar: Tryd 8 (RTDTrading)" in texto
    assert faltas == 0


def test_com_o_tryd7_e_o_stdde_fechado_as_faltas_contam() -> None:
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    ambiente = _ambiente_da_maria()
    del ambiente.processos["stdde.exe"]
    faltas, texto = _rodar(registro, ambiente)
    assert SEM_STDDE in texto
    assert "[ok] a ponte vai usar: Tryd 7 (Tryd.RtdServer)" in texto
    assert faltas >= 1


def test_com_o_tryd7_sem_o_dotnet_as_faltas_contam() -> None:
    faltas, texto = _rodar(_com_tryd7(RegistroFalso()), _ambiente_da_maria())
    assert SEM_DOTNET in texto
    assert faltas == 1


def test_com_o_tryd7_a_falta_da_outra_visao_nao_conta() -> None:
    """A ponte é de 32 bits: o que falta na visão de 64 não a impede."""
    registro = _com_dotnet(_com_tryd7(RegistroFalso()))
    registro.apagar_arvore("HKCU", f"Software\\Classes\\CLSID\\{CLSID_TRYD7}", 64)
    faltas, texto = _rodar(registro, _ambiente_da_maria())
    assert "[falta] Tryd.RtdServer não registrado na visão de 64 bits" in texto
    assert "[ok] a ponte vai usar: Tryd 7 (Tryd.RtdServer)" in texto
    assert faltas == 0


def _tudo_o_que_esta_gravado(registro: RegistroFalso) -> dict[tuple[Raiz, Visao], Any]:
    raizes: tuple[Raiz, ...] = ("HKCR", "HKCU", "HKLM")
    visoes: tuple[Visao, ...] = (32, 64)
    return {(r, v): registro.gravado(r, v) for r in raizes for v in visoes}


def test_o_diagnostico_das_vias_so_le_o_registro() -> None:
    registro = _com_profit(_com_tryd7(RegistroFalso()))
    antes = _tudo_o_que_esta_gravado(registro)
    _rodar(registro, _ambiente_da_maria())
    assert _tudo_o_que_esta_gravado(registro) == antes


# --------------------------------------------------------------------------- o diagnostico()


def _preparar_diagnostico(
    monkeypatch: pytest.MonkeyPatch, registro: RegistroFalso, *, faltas_da_classe: int
) -> list[dict[str, Any]]:
    """Troca o que o ``diagnostico()`` lê; devolve as chamadas a ``diagnosticar_vias``."""
    chamadas: list[dict[str, Any]] = []

    def vias_falso(registro_recebido: object, visao: Visao, **dependencias: Any) -> int:
        chamadas.append({"registro": registro_recebido, "visao": visao, **dependencias})
        return 0

    monkeypatch.setattr(rtd, "_importar", lambda nome: None)
    monkeypatch.setattr(rtd, "_versao_pywin32", lambda: "0")
    monkeypatch.setattr(rtd, "_diagnosticar_classe", lambda: faltas_da_classe)
    monkeypatch.setattr(rtd, "_diagnosticar_tipos", lambda: 0)
    monkeypatch.setattr(rtd, "_diagnosticar_processo", lambda: None)
    monkeypatch.setattr(rtd, "diagnosticar_vias", vias_falso)
    monkeypatch.setattr(tryd7, "RegistroWinreg", lambda: registro)
    return chamadas


def test_diagnostico_passa_as_dependencias_reais_ao_diagnosticar_vias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registro = RegistroFalso()
    chamadas = _preparar_diagnostico(monkeypatch, registro, faltas_da_classe=0)
    assert rtd.diagnostico() == 0
    assert len(chamadas) == 1
    chamada = chamadas[0]
    assert chamada["registro"] is registro
    assert chamada["visao"] == VISAO_DO_PROCESSO
    assert chamada["caminhos"] is tryd7.caminhos_em_execucao
    assert chamada["aceita"] is tryd7.porta_aceita
    assert chamada["ler_ini"] is tryd7.ler_ini_stdde_do_arquivo
    assert chamada["arquivo_existe"] is Path.exists
    assert chamada["saida"] is sys.stdout


def test_diagnostico_soma_as_faltas_das_vias(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar_diagnostico(monkeypatch, RegistroFalso(), faltas_da_classe=0)
    monkeypatch.setattr(rtd, "diagnosticar_vias", lambda *args, **kwargs: 2)
    assert rtd.diagnostico() == 1


def _registrar_na_visao_do_processo(
    registro: RegistroFalso, clsid: str, servidor: str, comando: str
) -> RegistroFalso:
    registro.definir(
        "HKCU",
        f"Software\\Classes\\CLSID\\{clsid}\\{servidor}",
        comando,
        visao=VISAO_DO_PROCESSO,
    )
    return registro


@pytest.mark.parametrize(
    ("clsid", "servidor", "comando", "esperado"),
    [
        (CLSID, "LocalServer32", TRYD_EXE, 1),
        (CLSID_TRYD7, "InprocServer32", "mscoree.dll", 0),
        (CLSID, "LocalServer32", PROFIT_EXE, 1),
    ],
    ids=["via_tryd8", "via_tryd7", "nenhuma_via"],
)
def test_a_classe_do_rtdtrading_so_conta_com_a_via_do_tryd8_ou_nenhuma(
    monkeypatch: pytest.MonkeyPatch, clsid: str, servidor: str, comando: str, esperado: int
) -> None:
    registro = _registrar_na_visao_do_processo(RegistroFalso(), clsid, servidor, comando)
    _preparar_diagnostico(monkeypatch, registro, faltas_da_classe=1)
    assert rtd.diagnostico() == esperado


def test_sem_nenhum_rtd_a_classe_do_rtdtrading_conta(monkeypatch: pytest.MonkeyPatch) -> None:
    _preparar_diagnostico(monkeypatch, RegistroFalso(), faltas_da_classe=1)
    assert rtd.diagnostico() == 1


def test_a_classe_do_rtdtrading_continua_sendo_impressa_com_a_via_do_tryd7(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registro = _registrar_na_visao_do_processo(
        RegistroFalso(), CLSID_TRYD7, "InprocServer32", "mscoree.dll"
    )
    chamadas: list[str] = []

    def classe() -> int:
        chamadas.append("classe")
        return 1

    _preparar_diagnostico(monkeypatch, registro, faltas_da_classe=1)
    monkeypatch.setattr(rtd, "_diagnosticar_classe", classe)
    assert rtd.diagnostico() == 0
    assert chamadas == ["classe"]

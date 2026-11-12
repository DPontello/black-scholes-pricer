"""As duas vias RTD e a escolha pelo registro — com um registro falso, nada toca o Windows."""

import pytest

from options_ponte import vias
from options_ponte.protocolo import CAMPOS_ATIVO, CAMPOS_OPCAO, CLSID
from options_ponte.vias import (
    CLSID_TRYD7,
    CODIGOS_TRYD7,
    MOTIVO_SEM_RTD,
    MOTIVO_SO_PROFIT,
    MOTIVO_TRYD7_OUTRA_VISAO,
    VIA_TRYD7,
    VIA_TRYD8,
    Raiz,
    Visao,
    dono_do_rtdtrading,
    escolher_via,
    executavel,
    servidor_do_clsid,
    tryd7_registrado,
    valor_da_classe,
)
from tests.ponte.registro_falso import RegistroFalso

TRYD_EXE = "C:\\Users\\Maria Silva\\AppData\\Roaming\\Tryd\\Tryd\\tryd.exe"
PROFIT_EXE = "C:\\Profit\\profitchart.exe -Embedding"
MSCOREE = "C:\\Windows\\System32\\mscoree.dll"


def _classe(
    registro: RegistroFalso,
    raiz: Raiz,
    clsid: str,
    servidor: str,
    comando: str,
    visao: Visao = 32,
) -> None:
    """Grava o padrão de ``CLSID\\{clsid}\\{servidor}`` onde a raiz o guarda (HKCR: sem prefixo)."""
    prefixo = "" if raiz == "HKCR" else "Software\\Classes\\"
    registro.definir(raiz, f"{prefixo}CLSID\\{clsid}\\{servidor}", comando, visao=visao)


def test_topico_do_tryd7_tem_tres_strings() -> None:
    assert VIA_TRYD7.topico("PETR4", "ULT") == ("COT", "PETR4", "ULT")


def test_topico_do_tryd8_continua_o_de_antes() -> None:
    assert VIA_TRYD8.topico("PETRK500", "OCP") == ("PETRK500_B_0", "OCP")


def test_tabela_cobre_todos_os_campos_que_o_app_pede() -> None:
    assert set(CAMPOS_ATIVO) | set(CAMPOS_OPCAO) <= set(CODIGOS_TRYD7)


def test_campo_sem_codigo_no_tryd7_e_erro_claro() -> None:
    with pytest.raises(ValueError, match="sem código no Tryd 7"):
        VIA_TRYD7.topico("PETR4", "XYZ")


@pytest.mark.parametrize(
    ("comando", "esperado"),
    [
        (f'"{TRYD_EXE}" /automation', "tryd.exe"),
        ("C:\\Profit\\profitchart.exe -Embedding", "profitchart.exe"),
        ("mscoree.dll", "mscoree.dll"),
        ("C:\\Windows\\System32\\MSCorEE.DLL", "mscoree.dll"),
        ("C:\\Program Files\\Tryd\\tryd.exe /automation", "tryd.exe"),
    ],
)
def test_executavel_do_comando(comando: str, esperado: str) -> None:
    assert executavel(comando) == esperado


@pytest.mark.parametrize("raiz", ["HKCR", "HKCU", "HKLM"])
def test_servidor_do_clsid_le_hkcr_hkcu_e_hklm(raiz: Raiz) -> None:
    registro = RegistroFalso()
    _classe(registro, raiz, CLSID, "LocalServer32", TRYD_EXE)
    assert servidor_do_clsid(registro, CLSID, 32) == TRYD_EXE
    assert servidor_do_clsid(registro, CLSID, 64) is None


def test_servidor_do_clsid_prefere_o_local_server_ao_inproc() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID, "InprocServer32", MSCOREE)
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE)
    assert servidor_do_clsid(registro, CLSID, 32) == PROFIT_EXE


def test_servidor_do_clsid_sem_nada_registrado_e_none() -> None:
    assert servidor_do_clsid(RegistroFalso(), CLSID, 32) is None


def test_escolhe_tryd8_quando_o_rtdtrading_e_do_tryd() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation')
    assert escolher_via(registro, 32) == VIA_TRYD8


def test_no_wine_o_rtdtrading_so_em_hkcu_ainda_da_tryd8() -> None:
    registro = RegistroFalso(hkcr_ve_hkcu=False)
    _classe(registro, "HKCU", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation')
    assert registro.ler("HKCR", f"CLSID\\{CLSID}\\LocalServer32", "", 32) is None
    assert escolher_via(registro, 32) == VIA_TRYD8


def test_tryd8_vence_quando_o_tryd7_tambem_esta_registrado() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation')
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "mscoree.dll")
    assert escolher_via(registro, 32) == VIA_TRYD8


def test_profit_no_rtdtrading_e_tryd7_registrado_da_tryd7() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE)
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "mscoree.dll")
    assert escolher_via(registro, 32) == VIA_TRYD7


@pytest.mark.parametrize("com_profit", [False, True])
def test_tryd7_so_na_outra_visao_diz_para_registrar(com_profit: bool) -> None:
    registro = RegistroFalso()
    if com_profit:
        _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE, visao=32)
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "mscoree.dll", visao=64)
    assert escolher_via(registro, 32) == MOTIVO_TRYD7_OUTRA_VISAO.format(outra=64, visao=32)


def test_tryd8_registrado_so_na_outra_visao_ainda_da_tryd8() -> None:
    """O ``LocalServer32`` é ativado atravessando as visões: o COM o acha mesmo assim."""
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation', visao=64)
    assert escolher_via(registro, 32) == VIA_TRYD8


def test_profit_registrado_so_na_outra_visao_sem_tryd7_diz_que_e_o_profit() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE, visao=64)
    assert escolher_via(registro, 32) == MOTIVO_SO_PROFIT


def test_o_rtdtrading_da_visao_do_processo_vence_o_da_outra() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE, visao=32)
    _classe(registro, "HKLM", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation', visao=64)
    assert escolher_via(registro, 32) == MOTIVO_SO_PROFIT


def test_tryd8_da_outra_visao_vence_o_tryd7_da_visao_do_processo() -> None:
    """A ordem da escolha não muda: o Tryd 8 vem antes, onde quer que o COM o ative."""
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation', visao=64)
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "mscoree.dll", visao=32)
    assert escolher_via(registro, 32) == VIA_TRYD8


def test_tryd7_com_outro_servidor_nao_conta_como_registrado() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "C:\\outro\\coisa.dll")
    assert escolher_via(registro, 32) == MOTIVO_SEM_RTD


def test_so_o_profit_diz_que_e_o_profit() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE)
    assert escolher_via(registro, 32) == MOTIVO_SO_PROFIT


def test_nada_registrado() -> None:
    assert escolher_via(RegistroFalso(), 32) == MOTIVO_SEM_RTD


# --------------------------------------------------------------------------- helpers do diagnóstico

INPROC_TRYD7 = f"CLSID\\{CLSID_TRYD7}\\InprocServer32"


@pytest.mark.parametrize("raiz", ["HKCR", "HKCU", "HKLM"])
def test_valor_da_classe_le_hkcr_hkcu_e_hklm(raiz: Raiz) -> None:
    registro = RegistroFalso()
    prefixo = "" if raiz == "HKCR" else "Software\\Classes\\"
    registro.definir(
        raiz, f"{prefixo}{INPROC_TRYD7}", "StRtd.Controlador.StRtdServer", nome="Class", visao=32
    )
    assert valor_da_classe(registro, INPROC_TRYD7, "Class", 32) == "StRtd.Controlador.StRtdServer"
    assert valor_da_classe(registro, INPROC_TRYD7, "Class", 64) is None


def test_valor_da_classe_acha_o_valor_no_hkcu_mesmo_com_o_hkcr_sem_enxergar_o_hkcu() -> None:
    """No Wine o HKCR não vê o HKCU: a leitura cai para ele."""
    registro = RegistroFalso(hkcr_ve_hkcu=False)
    registro.definir(
        "HKCU", f"Software\\Classes\\{INPROC_TRYD7}", "v2.0.50727", nome="RuntimeVersion", visao=32
    )
    assert registro.ler("HKCR", INPROC_TRYD7, "RuntimeVersion", 32) is None
    assert valor_da_classe(registro, INPROC_TRYD7, "RuntimeVersion", 32) == "v2.0.50727"


class RegistroQueAnota:
    """Só o ``ler``: anota onde foi procurado e devolve o que houver naquela raiz."""

    def __init__(self, valores: dict[Raiz, str]) -> None:
        self.valores = valores
        self.leituras: list[tuple[Raiz, str, str, Visao]] = []

    def ler(self, raiz: Raiz, caminho: str, nome: str, visao: Visao) -> str | None:
        self.leituras.append((raiz, caminho, nome, visao))
        return self.valores.get(raiz)

    def gravar(self, raiz: Raiz, caminho: str, nome: str, valor: str, visao: Visao) -> None:
        pytest.fail("a leitura não grava")

    def apagar_arvore(self, raiz: Raiz, caminho: str, visao: Visao) -> None:
        pytest.fail("a leitura não apaga")


@pytest.mark.parametrize(
    ("valores", "esperado", "raizes_lidas"),
    [
        ({"HKCR": "do-hkcr", "HKCU": "do-hkcu", "HKLM": "do-hklm"}, "do-hkcr", ["HKCR"]),
        ({"HKCU": "do-hkcu", "HKLM": "do-hklm"}, "do-hkcu", ["HKCR", "HKCU"]),
        ({"HKLM": "do-hklm"}, "do-hklm", ["HKCR", "HKCU", "HKLM"]),
        ({}, None, ["HKCR", "HKCU", "HKLM"]),
    ],
    ids=["hkcr", "hkcu", "hklm", "nenhum"],
)
def test_valor_da_classe_procura_em_hkcr_depois_hkcu_depois_hklm(
    valores: dict[Raiz, str], esperado: str | None, raizes_lidas: list[Raiz]
) -> None:
    registro = RegistroQueAnota(valores)
    assert valor_da_classe(registro, INPROC_TRYD7, "Assembly", 32) == esperado
    assert [leitura[0] for leitura in registro.leituras] == raizes_lidas
    assert registro.leituras[0] == ("HKCR", INPROC_TRYD7, "Assembly", 32)
    assert all(
        leitura[1] == f"Software\\Classes\\{INPROC_TRYD7}" for leitura in registro.leituras[1:]
    )


def test_valor_da_classe_ausente_ou_vazio_e_none() -> None:
    registro = RegistroFalso()
    assert valor_da_classe(registro, INPROC_TRYD7, "CodeBase", 32) is None
    registro.definir("HKCU", f"Software\\Classes\\{INPROC_TRYD7}", "", nome="CodeBase", visao=32)
    assert valor_da_classe(registro, INPROC_TRYD7, "CodeBase", 32) is None


def test_dono_do_rtdtrading_e_o_nome_do_executavel_em_minusculas() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation')
    assert dono_do_rtdtrading(registro, 32) == "tryd.exe"
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE)
    assert dono_do_rtdtrading(registro, 32) == "profitchart.exe"


def test_dono_do_rtdtrading_sem_nada_registrado_e_none() -> None:
    assert dono_do_rtdtrading(RegistroFalso(), 32) is None


def test_dono_do_rtdtrading_procura_na_outra_visao_se_nao_houver_na_do_processo() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation', visao=64)
    assert dono_do_rtdtrading(registro, 32) == "tryd.exe"


def test_o_dono_do_rtdtrading_na_visao_do_processo_vence_o_da_outra() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKLM", CLSID, "LocalServer32", PROFIT_EXE, visao=32)
    _classe(registro, "HKLM", CLSID, "LocalServer32", f'"{TRYD_EXE}" /automation', visao=64)
    assert dono_do_rtdtrading(registro, 32) == "profitchart.exe"


@pytest.mark.parametrize("raiz", ["HKCR", "HKCU", "HKLM"])
def test_tryd7_registrado_com_o_mscoree_em_qualquer_raiz(raiz: Raiz) -> None:
    registro = RegistroFalso()
    _classe(registro, raiz, CLSID_TRYD7, "InprocServer32", "C:\\Windows\\System32\\MSCorEE.DLL")
    assert tryd7_registrado(registro, 32)


def test_tryd7_registrado_depende_da_visao() -> None:
    registro = RegistroFalso()
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "mscoree.dll", visao=64)
    assert tryd7_registrado(registro, 64)
    assert not tryd7_registrado(registro, 32)


def test_tryd7_registrado_com_outro_servidor_ou_nenhum_e_falso() -> None:
    registro = RegistroFalso()
    assert not tryd7_registrado(registro, 32)
    _classe(registro, "HKCU", CLSID_TRYD7, "InprocServer32", "C:\\outro\\coisa.dll")
    assert not tryd7_registrado(registro, 32)


def test_a_escolha_usa_o_mesmo_predicado_do_tryd7_registrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A escolha chama ``tryd7_registrado``: se a regra mudar, ela e o diagnóstico mudam juntos."""
    monkeypatch.setattr(vias, "tryd7_registrado", lambda registro, visao: visao == 32)
    assert escolher_via(RegistroFalso(), 32) == VIA_TRYD7

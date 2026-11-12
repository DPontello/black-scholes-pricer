"""O ``RegistroFalso`` dos testes da ponte — o que as Tasks seguintes assumem dele."""

from tests.ponte.registro_falso import RegistroFalso


def test_caminho_e_nome_do_valor_nao_diferenciam_maiuscula() -> None:
    registro = RegistroFalso()
    registro.gravar("HKCU", "Software\\Classes\\Tryd.RtdServer\\CLSID", "CodeBase", "x", 64)
    assert registro.ler("HKCU", "SOFTWARE\\classes\\tryd.rtdserver\\clsid", "CODEBASE", 64) == "x"
    registro.gravar("HKCU", "software\\classes\\tryd.rtdserver\\clsid", "codebase", "y", 64)
    chave = "software\\classes\\tryd.rtdserver\\clsid"
    assert registro.gravado("HKCU", 64) == {chave: {"codebase": "y"}}


def test_cada_visao_e_um_registro_a_parte() -> None:
    registro = RegistroFalso()
    registro.definir("HKCU", "A\\B", "x", visao=32)
    assert registro.ler("HKCU", "A\\B", "", 32) == "x"
    assert registro.ler("HKCU", "A\\B", "", 64) is None
    assert registro.gravado("HKCU", 64) == {}


def test_apagar_arvore_leva_as_subchaves_e_poupa_as_irmas() -> None:
    registro = RegistroFalso()
    for caminho in ("A\\B", "A\\B\\C", "A\\B\\C\\D", "A\\BB", "A"):
        registro.definir("HKCU", caminho, "x")
    registro.apagar_arvore("HKCU", "a\\b", 64)
    assert sorted(registro.gravado("HKCU", 64)) == ["a", "a\\bb"]
    registro.apagar_arvore("HKCU", "nao\\existe", 64)  # ausente não é erro


def test_hkcr_junta_hkcu_hklm_e_o_gravado_direto_nessa_ordem() -> None:
    registro = RegistroFalso()
    registro.definir("HKCR", "CLSID\\X", "direto")
    assert registro.ler("HKCR", "CLSID\\X", "", 64) == "direto"
    registro.definir("HKLM", "Software\\Classes\\CLSID\\X", "hklm")
    assert registro.ler("HKCR", "CLSID\\X", "", 64) == "hklm"
    registro.definir("HKCU", "Software\\Classes\\CLSID\\X", "hkcu")
    assert registro.ler("HKCR", "CLSID\\X", "", 64) == "hkcu"


def test_hkcr_nao_enxerga_o_hkcu_com_a_opcao_do_wine() -> None:
    registro = RegistroFalso(hkcr_ve_hkcu=False)
    registro.definir("HKCU", "Software\\Classes\\CLSID\\X", "hkcu")
    assert registro.ler("HKCR", "CLSID\\X", "", 64) is None
    registro.definir("HKLM", "Software\\Classes\\CLSID\\X", "hklm")
    assert registro.ler("HKCR", "CLSID\\X", "", 64) == "hklm"

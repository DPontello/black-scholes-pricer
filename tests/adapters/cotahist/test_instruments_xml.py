"""Cadastro no XML da "Pesquisa por pregão" (BVBG.028) convertido no CSV que o app já lê."""

from datetime import date
from pathlib import Path

import pytest

from options_engine.adapters.outbound.cotahist.errors import InstrumentsFileError
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo, load_instruments
from options_engine.adapters.outbound.cotahist.instruments_xml import (
    instruments_csv_from_xml_package,
    is_instruments_xml_package,
)
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from tests.adapters.cotahist._bvbg import acao, opcao, pacote, xml_cadastro, zip_de

_PETR4 = "200003061028"
_PETR3 = "200003060884"


def _petr() -> bytes:
    return xml_cadastro(
        [
            acao(_PETR3, "PETR3", "PETR"),
            acao(_PETR4, "PETR4", "PETR"),
            opcao(
                "200002749212",
                "PETRC512",
                "PETR",
                tipo="CALL",
                strike="49.44",
                estilo="AMER",
                vencimento="2027-03-19",
                objeto_id=_PETR4,
            ),
            opcao(
                "200002749300",
                "PETRO480",
                "PETR",
                tipo="PUTT",
                strike="48.00",
                estilo="EURO",
                vencimento="2026-11-19",
                objeto_id=_PETR3,
            ),
        ]
    )


def _converter(tmp_path: Path, conteudo: bytes) -> tuple[date | None, dict[str, InstrumentInfo]]:
    origem = tmp_path / "pesquisa-pregao.zip"
    origem.write_bytes(conteudo)
    data, texto = instruments_csv_from_xml_package(origem)
    csv = tmp_path / "convertido.csv"
    csv.write_text(texto, encoding="utf-8")
    return data, load_instruments(csv)


def test_opcao_do_xml_vira_serie_do_cadastro_com_o_ativo_objeto_pelo_id(tmp_path: Path) -> None:
    _, cadastro = _converter(tmp_path, pacote({"IN261103.zip": _petr()}))
    assert cadastro["PETRC512"] == InstrumentInfo(
        "PETRC512",
        ExerciseStyle.AMERICAN,
        "PETR4",
        option_type=OptionType.CALL,
        strike=49.44,
        expiry=date(2027, 3, 19),
        lot=100,
    )
    assert cadastro["PETRO480"] == InstrumentInfo(
        "PETRO480",
        ExerciseStyle.EUROPEAN,
        "PETR3",
        option_type=OptionType.PUT,
        strike=48.0,
        expiry=date(2026, 11, 19),
        lot=100,
    )


def test_acao_entra_sem_termos_de_opcao(tmp_path: Path) -> None:
    _, cadastro = _converter(tmp_path, pacote({"IN261103.zip": _petr()}))
    assert cadastro["PETR4"] == InstrumentInfo("PETR4", None, None, lot=1)


def test_data_de_referencia_vem_do_xml(tmp_path: Path) -> None:
    data, _ = _converter(tmp_path, pacote({"IN261103.zip": _petr()}))
    assert data == date(2026, 11, 3)


def test_ativo_objeto_fora_do_arquivo_fica_vazio(tmp_path: Path) -> None:
    xml = xml_cadastro(
        [
            opcao(
                "1",
                "VALEK600",
                "VALE",
                tipo="CALL",
                strike="60.00",
                estilo="AMER",
                vencimento="2026-11-19",
                objeto_id="999",
            )
        ]
    )
    _, cadastro = _converter(tmp_path, pacote({"IN261103.zip": xml}))
    assert cadastro["VALEK600"].underlying_symbol is None


def test_outros_instrumentos_ficam_de_fora(tmp_path: Path) -> None:
    futuro = (
        "<Instrm><FinInstrmId><OthrId><Id>5</Id></OthrId></FinInstrmId>"
        "<InstrmInf><FutrCtrctsInf><TckrSymb>DOLX26</TckrSymb></FutrCtrctsInf></InstrmInf></Instrm>"
    )
    _, cadastro = _converter(
        tmp_path, pacote({"IN261103.zip": xml_cadastro([futuro, acao(_PETR4, "PETR4", "PETR")])})
    )
    assert set(cadastro) == {"PETR4"}


def test_pacote_com_varios_pregoes_usa_o_mais_recente(tmp_path: Path) -> None:
    antigo = xml_cadastro([acao(_PETR4, "PETR4", "PETR", data=date(2026, 10, 30))])
    data, _ = _converter(tmp_path, pacote({"IN261103.zip": _petr(), "IN261030.zip": antigo}))
    assert data == date(2026, 11, 3)


def test_zip_com_o_xml_direto_tambem_vale(tmp_path: Path) -> None:
    conteudo = zip_de({"BVBG.028.02_BV000327.xml": _petr()})
    assert is_instruments_xml_package(conteudo)
    _, cadastro = _converter(tmp_path, conteudo)
    assert cadastro["PETRC512"].underlying_symbol == "PETR4"


def test_reconhece_o_pacote_da_pesquisa_por_pregao() -> None:
    assert is_instruments_xml_package(pacote({"IN261103.zip": _petr()}))


@pytest.mark.parametrize(
    "conteudo",
    [
        zip_de({}),  # o ZIP vazio de 22 bytes de um download que falhou
        zip_de({"COTAHIST_D30102026.TXT": b"00COTAHIST.2026BOVESPA"}),
        zip_de({"IN261103.zip": zip_de({"outro.xml": b"<?xml version='1.0'?><Document/>"})}),
        zip_de({"outro.xml": b"<?xml version='1.0'?><Document/>"}),
        zip_de({"IN261103.zip": b"nao e zip"}),
        b"nao e zip",
    ],
)
def test_outros_arquivos_nao_sao_o_pacote(conteudo: bytes) -> None:
    assert not is_instruments_xml_package(conteudo)


def test_outros_membros_do_pacote_sao_ignorados(tmp_path: Path) -> None:
    conteudo = zip_de({"LEIAME.txt": b"x", "IN261103.zip": zip_de({"a.xml": _petr()})})
    _, cadastro = _converter(tmp_path, conteudo)
    assert "PETRC512" in cadastro


def test_instrumento_sem_ticker_fica_de_fora(tmp_path: Path) -> None:
    xml = xml_cadastro([acao("1", "", "PETR"), acao(_PETR4, "PETR4", "PETR")])
    _, cadastro = _converter(tmp_path, pacote({"IN261103.zip": xml}))
    assert set(cadastro) == {"PETR4"}


@pytest.mark.parametrize(
    ("conteudo", "trecho"),
    [
        (zip_de({"LEIAME.txt": b"x"}), "nenhum XML BVBG.028"),
        (b"nao e zip", "ZIP ilegível"),
    ],
)
def test_pacote_sem_o_cadastro_e_erro_de_arquivo(
    tmp_path: Path, conteudo: bytes, trecho: str
) -> None:
    with pytest.raises(InstrumentsFileError, match=trecho):
        _converter(tmp_path, conteudo)


def test_arquivo_que_nao_abre_e_erro_de_arquivo(tmp_path: Path) -> None:
    with pytest.raises(InstrumentsFileError, match="não foi possível ler"):
        instruments_csv_from_xml_package(tmp_path / "sumiu.zip")


def test_xml_truncado_e_erro_de_arquivo(tmp_path: Path) -> None:
    truncado = _petr()[:-200]
    with pytest.raises(InstrumentsFileError, match="XML"):
        _converter(tmp_path, pacote({"IN261103.zip": truncado}))

"""Cadastro de Instrumentos — preâmbulo, delimitador, encoding e mapeamento do OptnStyle."""

from datetime import date
from pathlib import Path

import pytest

from options_engine.adapters.outbound.cotahist.errors import InstrumentsFileError
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo, load_instruments
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from tests.data.cotahist.build_fixture import INSTRUMENTS_NAME

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "cotahist"


def _gravar(tmp_path: Path, linhas: list[str], encoding: str = "utf-8-sig") -> Path:
    caminho = tmp_path / "InstrumentsConsolidatedFile_20261023.csv"
    caminho.write_bytes("\r\n".join(linhas).encode(encoding))
    return caminho


def test_preambulo_e_ponto_e_virgula(tmp_path: Path) -> None:
    caminho = _gravar(
        tmp_path,
        [
            "Cadastro de Instrumentos",
            "Data;2026-10-23",
            "TckrSymb;Asst;OptnStyle;UndrlygTckrSymb1",
            "PETRK300;PETR;AMER;",
            "PETRW300;PETR;EURO;PETR4",
        ],
    )
    instrumentos = load_instruments(caminho)
    assert instrumentos["PETRK300"] == InstrumentInfo("PETRK300", ExerciseStyle.AMERICAN, None)
    assert instrumentos["PETRW300"] == InstrumentInfo("PETRW300", ExerciseStyle.EUROPEAN, "PETR4")


def test_ativo_objeto_da_opcao_vem_do_asst_quando_a_coluna_propria_vem_vazia(
    tmp_path: Path,
) -> None:
    """Como no Cadastro real de 28/10/2026: ``UndrlygTckrSymb1`` vazio em todas as opções, e
    ``Asst`` com o ticker do ativo-objeto na opção e só a raiz no à vista."""
    caminho = _gravar(
        tmp_path,
        [
            "TckrSymb;Asst;OptnTp;OptnStyle;UndrlygTckrSymb1",
            "PETR4;PETR;;;",
            "PETRK526;PETR4;Call;EURO;",
            "PETRA290;PETR3;Call;AMER;",
            "BOVAK170;BOVA11;Call;EURO;",
            "B3SAK130;B3SA3;Call;AMER;",
            "M1TAK400;M1TA34;Call;AMER;",
            "IBOVR205;IBOV;Call;EURO;",
            "VALEK600;VALE3;Call;AMER;VALE5",
        ],
    )
    objetos = {s: i.underlying_symbol for s, i in load_instruments(caminho).items()}
    assert objetos == {
        "PETR4": None,
        "PETRK526": "PETR4",
        "PETRA290": "PETR3",
        "BOVAK170": "BOVA11",
        "B3SAK130": "B3SA3",
        "M1TAK400": "M1TA34",
        "IBOVR205": None,
        "VALEK600": "VALE5",
    }


def test_virgula_sem_preambulo_e_sem_coluna_de_ativo_objeto(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, ["TckrSymb,OptnStyle", "PETRK300,EURO"])
    assert load_instruments(caminho)["PETRK300"].underlying_symbol is None


def test_cp1252_quando_nao_e_utf8(tmp_path: Path) -> None:
    caminho = _gravar(
        tmp_path,
        ["Cadastro sintético de opções", "TckrSymb;OptnStyle", "PETRK300;AMER"],
        encoding="cp1252",
    )
    assert load_instruments(caminho)["PETRK300"].exercise_style is ExerciseStyle.AMERICAN


@pytest.mark.parametrize(
    ("bruto", "esperado"),
    [
        ("AMER", ExerciseStyle.AMERICAN),
        ("American", ExerciseStyle.AMERICAN),
        ("amer ", ExerciseStyle.AMERICAN),
        ("EURO", ExerciseStyle.EUROPEAN),
        ("Europeu", ExerciseStyle.EUROPEAN),
        ("", None),
        ("BERM", None),
    ],
)
def test_estilo_por_prefixo_sem_distinguir_maiusculas(
    tmp_path: Path, bruto: str, esperado: ExerciseStyle | None
) -> None:
    """Vazio ou desconhecido é ``None`` — nunca EUROPEAN por omissão (ADR-0006)."""
    caminho = _gravar(tmp_path, ["TckrSymb;OptnStyle", f"PETRK300;{bruto}"])
    assert load_instruments(caminho)["PETRK300"].exercise_style is esperado


def test_ticker_repetido_com_estilos_divergentes_vira_desconhecido(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, ["TckrSymb;OptnStyle", "PETRK300;AMER", "PETRK300;EURO"])
    assert load_instruments(caminho)["PETRK300"].exercise_style is None


def test_ticker_repetido_identico_e_aceito(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, ["TckrSymb;OptnStyle", "PETRK300;AMER", "PETRK300;AMER"])
    assert load_instruments(caminho)["PETRK300"].exercise_style is ExerciseStyle.AMERICAN


def test_linhas_curtas_e_ticker_vazio_sao_ignorados(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, ["TckrSymb;OptnStyle", "", ";AMER", "PETRK300;AMER", "solta"])
    assert list(load_instruments(caminho)) == ["PETRK300"]


def test_sem_cabecalho_reconhecivel(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, ["Ticker;Estilo", "PETRK300;AMER"])
    with pytest.raises(InstrumentsFileError, match="OptnStyle"):
        load_instruments(caminho)


def test_arquivo_ausente_e_erro_de_arquivo(tmp_path: Path) -> None:
    with pytest.raises(InstrumentsFileError, match="não foi possível ler"):
        load_instruments(tmp_path / "nao_existe.csv")


def test_encoding_irreconhecivel(tmp_path: Path) -> None:
    caminho = tmp_path / "ruim.csv"
    caminho.write_bytes(b"TckrSymb;OptnStyle\r\n\x81\x8d\x8f\x90\x9d;AMER")
    with pytest.raises(InstrumentsFileError, match="encoding"):
        load_instruments(caminho)


def test_cadastro_traz_tipo_strike_e_vencimento() -> None:
    info = load_instruments(FIXTURE / INSTRUMENTS_NAME)["PETRK280"]
    assert (info.option_type, info.strike, info.expiry, info.exercise_style) == (
        OptionType.CALL,
        28.0,
        date(2026, 11, 19),
        ExerciseStyle.AMERICAN,
    )


def test_formatos_alternativos_e_lixo(tmp_path: Path) -> None:
    caminho = _gravar(
        tmp_path,
        [
            "TckrSymb;OptnStyle;OptnTp;ExrcPric;XprtnDt",
            "PETRW285;EURO;Put;28,50;19/11/2026",
            "PETRX999;EURO;???;abc;amanhã",
        ],
    )
    dados = load_instruments(caminho)
    assert (dados["PETRW285"].option_type, dados["PETRW285"].strike, dados["PETRW285"].expiry) == (
        OptionType.PUT,
        28.5,
        date(2026, 11, 19),
    )
    assert (dados["PETRX999"].option_type, dados["PETRX999"].strike, dados["PETRX999"].expiry) == (
        None,
        None,
        None,
    )


def test_colunas_opcionais_ausentes_deixam_os_termos_vazios(tmp_path: Path) -> None:
    caminho = _gravar(tmp_path, ["TckrSymb;OptnStyle", "PETRK300;AMER"])
    info = load_instruments(caminho)["PETRK300"]
    assert (info.option_type, info.strike, info.expiry) == (None, None, None)


@pytest.mark.parametrize("bruto", ["", "0", "-1", "nan", "inf"])
def test_strike_nao_positivo_ou_nao_finito_vira_none(tmp_path: Path, bruto: str) -> None:
    caminho = _gravar(tmp_path, ["TckrSymb;OptnStyle;ExrcPric", f"PETRK300;AMER;{bruto}"])
    assert load_instruments(caminho)["PETRK300"].strike is None


def test_duplicata_com_termos_divergentes_zera_todos_os_campos_opcionais(
    tmp_path: Path,
) -> None:
    caminho = _gravar(
        tmp_path,
        [
            "TckrSymb;OptnStyle;OptnTp;ExrcPric;XprtnDt;UndrlygTckrSymb1",
            "PETRK300;AMER;CALL;30.00;2026-11-19;PETR4",
            "PETRK300;AMER;CALL;31.00;2026-11-19;PETR4",
        ],
    )
    info = load_instruments(caminho)["PETRK300"]
    assert info == InstrumentInfo("PETRK300", None, None)
    assert (info.option_type, info.strike, info.expiry) == (None, None, None)

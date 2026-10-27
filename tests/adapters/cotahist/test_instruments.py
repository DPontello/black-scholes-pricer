"""Cadastro de Instrumentos — preâmbulo, delimitador, encoding e mapeamento do OptnStyle."""

from pathlib import Path

import pytest

from options_engine.adapters.outbound.cotahist.errors import InstrumentsFileError
from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo, load_instruments
from options_engine.domain.model.enums import ExerciseStyle


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

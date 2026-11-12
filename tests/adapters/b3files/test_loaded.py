"""``LibraryLoader``: o lote e os termos de cada série vêm do Cadastro importado."""

from pathlib import Path

from options_engine.adapters.outbound.b3files.loaded import LibraryLoader, LoadedLibrary
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from tests.adapters._mercado import biblioteca


def _cadastro_com_lote() -> bytes:
    linhas = [
        "TckrSymb;Asst;XprtnDt;ExrcPric;OptnStyle;OptnTp;UndrlygTckrSymb1;AllcnRndLot",
        "PETR4;PETR;;;;;;100",
        "PETRK300;PETR4;2026-11-19;30.00;AMER;CALL;PETR4;100",
        "BOVAK170;BOVA11;2026-11-19;170.00;EURO;CALL;BOVA11;1",
    ]
    return "\r\n".join(linhas).encode("utf-8-sig")


def test_lote_da_serie_vem_do_cadastro_e_ticker_desconhecido_e_none(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "mercado", cadastro=_cadastro_com_lote())
    loaded = LibraryLoader(lib).load()
    assert isinstance(loaded, LoadedLibrary)
    assert (loaded.lot("PETRK300"), loaded.lot("BOVAK170")) == (100, 1)
    assert loaded.lot("VALEK600") is None


def test_termos_da_serie_vem_do_cadastro_com_o_ativo_da_operacao_de_reserva(tmp_path: Path) -> None:
    linhas = [
        "TckrSymb;Asst;XprtnDt;ExrcPric;OptnStyle;OptnTp;UndrlygTckrSymb1;AllcnRndLot",
        "PETRK300;PETR4;2026-11-19;30.00;AMER;CALL;PETR4;100",
        "PETRW280;PETR4;2026-11-19;28.00;EURO;PUT;;100",
        "PETRK340;PETR4;2026-11-19;34.00;;CALL;PETR4;100",
    ]
    lib = biblioteca(tmp_path / "mercado", cadastro="\r\n".join(linhas).encode("utf-8-sig"))
    loaded = LibraryLoader(lib).load()
    assert isinstance(loaded, LoadedLibrary)
    call = loaded.option_terms("PETRK300", "XXXX3")
    assert not isinstance(call, str)
    assert (call.underlying, call.strike, call.option_type, call.exercise_style) == (
        "PETR4",
        30.0,
        OptionType.CALL,
        ExerciseStyle.AMERICAN,
    )
    put = loaded.option_terms("PETRW280", "PETR4")
    assert not isinstance(put, str) and put.underlying == "PETR4"
    assert (
        loaded.option_terms("PETRK340", "PETR4") == "PETRK340: sem estilo de exercício no cadastro"
    )
    assert loaded.option_terms("VALEK600", "VALE3") == (
        "VALEK600: série não encontrada no Cadastro da B3. Confira o código na nota da corretora;"
        " se a série for nova, importe o Cadastro mais recente em Arquivos B3."
    )

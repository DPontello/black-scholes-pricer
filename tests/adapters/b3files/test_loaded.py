"""``LibraryLoader``: o lote de cada série vem do Cadastro importado."""

from pathlib import Path

from options_engine.adapters.outbound.b3files.loaded import LibraryLoader, LoadedLibrary
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

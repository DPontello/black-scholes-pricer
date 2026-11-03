"""Histórico de IV de 30 dias úteis e HV de 21 pelos COTAHIST da biblioteca, com cache sqlite."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing
from datetime import date
from math import log
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import StaticHolidayCalendar
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.b3files.loaded import (
    NO_CADASTRO_REASON,
    NO_COTAHIST_REASON,
    LibraryLoader,
)
from options_engine.adapters.outbound.cotahist import vol_history
from options_engine.adapters.outbound.cotahist.adapter import CotahistOptionChainAdapter
from options_engine.adapters.outbound.cotahist.parser import CotahistRecord, iter_cotahist
from options_engine.adapters.outbound.cotahist.vol_history import (
    VOL_HISTORY_CACHE_NAME,
    CotahistVolHistory,
)
from options_engine.adapters.outbound.cotahist.volatility import realized_volatility
from options_engine.application.ports.outbound import VolHistoryPort
from options_engine.domain.analytics.volatility import DailyVol, ExpiryVol, iv_at_horizon
from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.model.conventions import Compounding, RiskFreeRate, TimeToExpiry
from options_engine.domain.pricing.smile import SeriesMarket, build_smile
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.adapters._mercado import CDI, FIXTURE, biblioteca, relogio
from tests.adapters.cotahist._layout import arquivo, registro
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME, REFERENCE_SESSION

_CALENDARIO = StaticHolidayCalendar.from_packaged_data()
_NOVEMBRO, _DEZEMBRO = date(2026, 11, 19), date(2026, 12, 18)
_PREGOES = (date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 23))
_CADASTRO_MINIMO = (
    "TckrSymb;Asst;XprtnDt;ExrcPric;OptnStyle;OptnTp;UndrlygTckrSymb1\r\nPETR4;PETR;;;;;\r\n"
)


def _historico(lib: B3FileLibrary, cdi: float = CDI) -> CotahistVolHistory:
    return CotahistVolHistory(LibraryLoader(lib), _CALENDARIO, lambda: cdi)


def _linhas_do_pregao(dia: date, spot: float, vol: float) -> list[str]:
    """PETR4 e calls e puts de 28 a 32 em novembro e dezembro, ao preço de BS com vol plana."""
    linhas = [
        registro(
            pregao=dia,
            simbolo="PETR4",
            mercado=10,
            especificacao="PN      N2",
            ultimo=spot,
            oferta_compra=spot - 0.01,
            oferta_venda=spot + 0.01,
            negocios=5000,
        )
    ]
    for vencimento, letra_call, letra_put in ((_NOVEMBRO, "K", "W"), (_DEZEMBRO, "L", "X")):
        tau = _CALENDARIO.business_days_between(dia, vencimento) / 252.0
        for strike in (28.0, 29.0, 30.0, 31.0, 32.0):
            for mercado, letra in ((70, letra_call), (80, letra_put)):
                preco = bs_price(spot, strike, tau, log(1.0 + CDI), vol, is_call=mercado == 70)
                meio = max(round(preco, 2), 0.02)
                linhas.append(
                    registro(
                        pregao=dia,
                        simbolo=f"PETR{letra}{int(strike * 10)}",
                        mercado=mercado,
                        especificacao="PN",
                        ultimo=meio,
                        oferta_compra=meio - 0.01,
                        oferta_venda=meio + 0.01,
                        negocios=10,
                        strike=strike,
                        vencimento=vencimento,
                    )
                )
    return linhas


def _cotahist(pregoes: Sequence[date], extras: Sequence[str] = ()) -> bytes:
    linhas = [linha for dia in pregoes for linha in _linhas_do_pregao(dia, 30.0, 0.30)]
    return arquivo([*linhas, *extras], geracao=pregoes[-1], ano=2026).encode("cp1252")


def _biblioteca(raiz: Path, arquivos: dict[str, bytes]) -> B3FileLibrary:
    lib = B3FileLibrary(raiz, relogio())
    for nome, conteudo in arquivos.items():
        lib.import_file(nome, conteudo)
    lib.import_file("InstrumentsConsolidatedFile_20261023_1.csv", _CADASTRO_MINIMO.encode())
    return lib


def _do_pregao(historico: tuple[DailyVol, ...] | str, dia: date) -> DailyVol:
    assert not isinstance(historico, str), historico
    (linha,) = [d for d in historico if d.session == dia]
    return linha


def _iv30_pela_cadeia_do_adapter(symbol: str) -> float:
    """O mesmo cálculo a partir da cadeia de fim de dia do adapter COTAHIST do pregão."""
    taxa = RiskFreeRate(CDI, Compounding.BUSINESS_DAILY_252)
    cadeia = CotahistOptionChainAdapter(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
        risk_free_rate=taxa,
    ).get_chain(symbol)
    spot = cadeia.underlying.spot
    pontos = []
    for vencimento in sorted({q.contract.terms.expiry for q in cadeia.quotes}):
        du = _CALENDARIO.business_days_between(REFERENCE_SESSION, vencimento)
        mercado = SeriesMarket(spot, taxa.as_continuous(), TimeToExpiry.from_days(du).year_fraction)
        vol = build_smile(vencimento, cadeia.quotes, mercado).vol_at(spot)
        if vol is not None and du >= 5:
            pontos.append(ExpiryVol(du, vol))
    resultado = iv_at_horizon(pontos)
    assert resultado is not None
    return resultado.vol


def test_e_um_vol_history_port(tmp_path: Path) -> None:
    assert isinstance(_historico(biblioteca(tmp_path / "m")), VolHistoryPort)


def test_iv30_do_pregao_bate_com_o_smile_da_cadeia_do_adapter(tmp_path: Path) -> None:
    linha = _do_pregao(_historico(biblioteca(tmp_path / "m")).history("PETR4"), REFERENCE_SESSION)
    assert linha.iv30 is not None
    assert linha.extrapolated is False
    esperado = _iv30_pela_cadeia_do_adapter("PETR4")
    assert_close(linha.iv30, esperado, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="IV 30")


def test_fechamentos_e_hv21_pela_vol_realizada_existente(tmp_path: Path) -> None:
    historico = _historico(biblioteca(tmp_path / "m")).history("PETR4")
    assert not isinstance(historico, str)
    assert [d.session for d in historico] == sorted(d.session for d in historico)
    fechamentos = [d.close for d in historico]
    for i, dia in enumerate(historico):
        hv = realized_volatility(fechamentos[: i + 1], 21)
        assert dia.hv21 == (None if isinstance(hv, str) else hv.value)
    assert historico[0].hv21 is None and historico[-1].hv21 is not None
    assert all(d.iv30 is None for d in historico[:-1])


def test_vol_plana_no_book_da_iv30_perto_da_vol(tmp_path: Path) -> None:
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_A2026.TXT": _cotahist(_PREGOES)})
    historico = _historico(lib).history("PETR4")
    assert not isinstance(historico, str)
    assert [d.session for d in historico] == list(_PREGOES)
    for dia in historico:
        assert dia.iv30 is not None
        assert abs(dia.iv30 - 0.30) < 0.005  # prêmios arredondados ao centavo no arquivo


def test_series_rejeitadas_no_adapter_ficam_fora(tmp_path: Path) -> None:
    """No strike do spot e com ticker menor (que venceria no smile), três séries absurdas:
    strike corrigido por índice, book cruzado e ticker com registros divergentes no pregão."""
    dia = _PREGOES[-1]
    absurdas = [
        registro(
            pregao=dia,
            simbolo=simbolo,
            mercado=70,
            especificacao="PN",
            ultimo=6.0,
            oferta_compra=compra,
            oferta_venda=venda,
            negocios=10,
            strike=30.0,
            indopc=indopc,
            vencimento=_NOVEMBRO,
        )
        for simbolo, compra, venda, indopc in (
            ("PETRK2AA", 5.99, 6.01, 1),
            ("PETRK2AB", 6.50, 5.50, 0),
            ("PETRK2AC", 5.99, 6.01, 0),
            ("PETRK2AC", 6.99, 7.01, 0),
        )
    ]
    limpa = _historico(_biblioteca(tmp_path / "a", {"COTAHIST_D.TXT": _cotahist([dia])}))
    suja = _historico(_biblioteca(tmp_path / "b", {"COTAHIST_D.TXT": _cotahist([dia], absurdas)}))
    assert _do_pregao(suja.history("PETR4"), dia) == _do_pregao(limpa.history("PETR4"), dia)


def _leituras(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    lidos: list[Path] = []

    def registrando(path: Path) -> Iterator[CotahistRecord]:
        lidos.append(path)
        return iter_cotahist(path)

    monkeypatch.setattr(vol_history, "iter_cotahist", registrando)
    return lidos


def test_segunda_leitura_sai_do_cache_sem_reler_o_arquivo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_A2026.TXT": _cotahist(_PREGOES[:2])})
    primeira = _historico(lib).history("PETR4")
    lidos = _leituras(monkeypatch)
    assert _historico(lib).history("PETR4") == primeira
    assert lidos == []
    assert (tmp_path / "m" / VOL_HISTORY_CACHE_NAME).is_file()


def test_diario_novo_calcula_so_o_pregao_novo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_A2026.TXT": _cotahist(_PREGOES[:2])})
    antes = _historico(lib).history("PETR4")
    diario = lib.import_file("COTAHIST_D23102026.TXT", _cotahist(_PREGOES[2:]))
    lidos = _leituras(monkeypatch)
    depois = _historico(lib).history("PETR4")
    assert lidos == [diario.path]
    assert not isinstance(antes, str) and not isinstance(depois, str)
    assert [d.session for d in depois] == list(_PREGOES)
    assert depois[:2] == antes


def test_trocar_o_cdi_recalcula(tmp_path: Path) -> None:
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_D.TXT": _cotahist(_PREGOES[-1:])})
    com_15 = _do_pregao(_historico(lib, 0.15).history("PETR4"), _PREGOES[-1])
    com_10 = _do_pregao(_historico(lib, 0.10).history("PETR4"), _PREGOES[-1])
    assert com_15.iv30 is not None and com_10.iv30 is not None
    assert com_15.iv30 != com_10.iv30


def test_cache_que_nao_e_sqlite_nao_e_sobrescrito(tmp_path: Path) -> None:
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_D.TXT": _cotahist(_PREGOES[-1:])})
    cache = tmp_path / "m" / VOL_HISTORY_CACHE_NAME
    cache.write_bytes(b"isto nao e um banco sqlite")
    historico = _historico(lib).history("PETR4")
    assert not isinstance(historico, str) and historico[0].iv30 is not None
    assert cache.read_bytes() == b"isto nao e um banco sqlite"


def test_sem_cotahist_o_motivo(tmp_path: Path) -> None:
    assert _historico(biblioteca(tmp_path / "m", com_cotahist=False)).history("PETR4") == (
        NO_COTAHIST_REASON
    )


def test_sem_cadastro_o_motivo_da_biblioteca(tmp_path: Path) -> None:
    lib = biblioteca(tmp_path / "m", com_cadastro=False)
    assert _historico(lib).history("PETR4") == NO_CADASTRO_REASON


def test_ativo_sem_fechamento_nos_arquivos(tmp_path: Path) -> None:
    motivo = _historico(biblioteca(tmp_path / "m")).history("XPTO3")
    assert motivo == "XPTO3: sem fechamento nos COTAHIST da biblioteca"


def test_arquivo_estragado_depois_de_lido_vira_motivo(tmp_path: Path) -> None:
    """A biblioteca já foi lida (e segue em cache) quando o COTAHIST estraga no disco."""
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_D.TXT": _cotahist(_PREGOES[-1:])})
    historico = _historico(lib)
    assert not isinstance(historico.history("PETR4"), str)
    (arquivo_importado,) = lib.cotahist_paths()
    arquivo_importado.write_bytes(b"00COTAHIST.2026 truncado\r\n")
    motivo = historico.history("PETR4")
    assert isinstance(motivo, str) and motivo.startswith("arquivos da B3 ilegíveis")


def _serie(dia: date, simbolo: str, strike: float, vencimento: date, meio: float) -> str:
    return registro(
        pregao=dia,
        simbolo=simbolo,
        mercado=70,
        especificacao="PN",
        ultimo=meio,
        oferta_compra=meio - 0.01,
        oferta_venda=meio + 0.01,
        negocios=10,
        strike=strike,
        vencimento=vencimento,
    )


def test_vencimento_fora_do_calendario_nao_derruba_o_pregao(tmp_path: Path) -> None:
    """Série de 2028, além do calendário empacotado: fica fora, e o resto do pregão segue."""
    dia = _PREGOES[-1]
    de_2028 = [_serie(dia, "PETRA300", 30.0, date(2028, 1, 21), 9.0)]
    base = _historico(_biblioteca(tmp_path / "a", {"COTAHIST_D.TXT": _cotahist([dia])}))
    com_2028 = _historico(
        _biblioteca(tmp_path / "b", {"COTAHIST_D.TXT": _cotahist([dia], de_2028)})
    )
    assert _do_pregao(com_2028.history("PETR4"), dia) == _do_pregao(base.history("PETR4"), dia)


def test_vencimento_mais_perto_sem_book_no_spot_cede_ao_seguinte(tmp_path: Path) -> None:
    """Vencimento de 04/12 (perto de 30 du) só com séries longe do spot: sem vol no spot, a
    interpolação usa o vencimento seguinte daquele lado, como se o de 04/12 não existisse."""
    dia = _PREGOES[-1]
    longe_do_spot = [
        _serie(dia, "PETRL340", 34.0, date(2026, 12, 4), 0.20),
        _serie(dia, "PETRL350", 35.0, date(2026, 12, 4), 0.10),
    ]
    base = _historico(_biblioteca(tmp_path / "a", {"COTAHIST_D.TXT": _cotahist([dia])}))
    com_semanal = _historico(
        _biblioteca(tmp_path / "b", {"COTAHIST_D.TXT": _cotahist([dia], longe_do_spot)})
    )
    assert _do_pregao(com_semanal.history("PETR4"), dia) == _do_pregao(base.history("PETR4"), dia)


def test_ativo_com_registros_divergentes_no_pregao_fica_sem_esse_pregao(tmp_path: Path) -> None:
    divergente = registro(
        pregao=_PREGOES[-1], simbolo="PETR4", mercado=10, especificacao="PN      N2", ultimo=31.0
    )
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_A.TXT": _cotahist(_PREGOES, [divergente])})
    historico = _historico(lib).history("PETR4")
    assert not isinstance(historico, str)
    assert [d.session for d in historico] == list(_PREGOES[:2])


def test_conteudo_corrompido_no_cache_e_recalculado(tmp_path: Path) -> None:
    lib = _biblioteca(tmp_path / "m", {"COTAHIST_D.TXT": _cotahist(_PREGOES[-1:])})
    primeira = _historico(lib).history("PETR4")
    with closing(sqlite3.connect(tmp_path / "m" / VOL_HISTORY_CACHE_NAME)) as conexao, conexao:
        conexao.execute("UPDATE historicos SET payload = 'nao e json'")
    assert _historico(lib).history("PETR4") == primeira

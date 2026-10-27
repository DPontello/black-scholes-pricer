"""``CotahistOptionChainAdapter`` sobre a fixture sintética — contrato do port e regras da cadeia.

A fixture (``tests/data/cotahist/``) é gerada por ``build_fixture.py``; o
primeiro teste garante que os arquivos versionados são exatamente o que o
gerador produz.
"""

import itertools
import math
import statistics
import zipfile
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.cotahist import (
    CotahistFormatError,
    CotahistOptionChainAdapter,
)
from options_engine.adapters.outbound.cotahist.parser import MARKET_SPOT, parse_cotahist
from options_engine.domain.model.chain import OptionChain, OptionQuote
from options_engine.domain.model.conventions import Compounding, DayCountConvention, RiskFreeRate
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import UnderlyingUnavailableError, UnknownSymbolError
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.adapters.cotahist._layout import arquivo, registro
from tests.data.cotahist.build_fixture import (
    COTAHIST_NAME,
    INSTRUMENTS_NAME,
    REFERENCE_SESSION,
    render,
)

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "cotahist"
COTAHIST = FIXTURE / COTAHIST_NAME
CADASTRO = FIXTURE / INSTRUMENTS_NAME
CDI = RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252)


def _adapter(**overrides: object) -> CotahistOptionChainAdapter:
    campos: dict[str, object] = {
        "session_date": REFERENCE_SESSION,
        "cotahist_paths": [COTAHIST],
        "instruments_path": CADASTRO,
        "risk_free_rate": CDI,
    }
    campos.update(overrides)
    return CotahistOptionChainAdapter(**campos)  # type: ignore[arg-type]  # justificativa: kwargs de teste


@pytest.fixture(scope="module")
def petr4() -> OptionChain:
    return _adapter().get_chain("PETR4")


def _por_simbolo(chain: OptionChain) -> dict[str, OptionQuote]:
    return {q.contract.symbol: q for q in chain.quotes}


def _rejeitadas(chain: OptionChain) -> dict[str, str]:
    return {r.symbol: r.reason for r in chain.rejected_series}


def test_fixture_versionada_e_a_que_o_gerador_produz() -> None:
    cotahist, cadastro = render()
    assert COTAHIST.read_bytes() == cotahist
    assert CADASTRO.read_bytes() == cadastro


# ---------------------------------------------------------------------------
# Ativo-objeto
# ---------------------------------------------------------------------------


def test_snapshot_com_book_observado(petr4: OptionChain) -> None:
    u = petr4.underlying
    assert (u.spot, u.bid, u.ask) == (30.0, 29.99, 30.01)
    assert_close(u.mid, 30.0, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="mid = média das ofertas")
    assert u.risk_free_rate == CDI
    assert petr4.underlying_book_available is True


def test_ativo_sem_ofertas_usa_o_fechamento_e_marca_a_cadeia() -> None:
    """Decisão da mesa (ADR-0004): VALE3 continua no painel, com bid = ask = mid = spot."""
    vale = _adapter().get_chain("VALE3")
    u = vale.underlying
    assert (u.bid, u.ask, u.mid) == (u.spot, u.spot, u.spot) == (60.0, 60.0, 60.0)
    assert vale.underlying_book_available is False
    assert len(vale.quotes) > 0


def test_vol_realizada_bate_com_o_calculo_manual() -> None:
    """Desvio-padrão amostral dos 21 últimos log-retornos x sqrt(252), à mão sobre o arquivo."""
    fechamentos = [
        r.last
        for r in sorted(parse_cotahist(COTAHIST), key=lambda r: r.session)
        if r.market == MARKET_SPOT and r.symbol == "PETR4"
    ][-22:]
    retornos = [math.log(b / a) for a, b in itertools.pairwise(fechamentos)]
    media = sum(retornos) / len(retornos)
    variancia = sum((x - media) ** 2 for x in retornos) / (len(retornos) - 1)
    esperada = math.sqrt(variancia) * math.sqrt(252.0)
    vol = _adapter().get_chain("PETR4").underlying.volatility
    assert vol.annualization_base is DayCountConvention.BUSINESS_252
    assert_close(vol.value, esperada, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="vol realizada")
    assert_close(statistics.stdev(retornos) * math.sqrt(252.0), esperada, rel=1e-12, abs_=0.0)


def test_janela_menor_exige_menos_historico() -> None:
    """ITUB4 tem 5 pregões: indisponível com 21 retornos, disponível com 4."""
    with pytest.raises(UnderlyingUnavailableError, match=r"histórico insuficiente.*mínimo 22"):
        _adapter().get_chain("ITUB4")
    assert _adapter(realized_vol_window=4).get_chain("ITUB4").underlying.volatility.value > 0.0


def test_sem_fechamento_no_pregao() -> None:
    with pytest.raises(UnderlyingUnavailableError, match="BBAS3 em 2026-10-23: sem fechamento"):
        _adapter().get_chain("BBAS3")


def test_simbolo_ausente_de_todos_os_arquivos_e_desconhecido() -> None:
    with pytest.raises(UnknownSymbolError, match="XXXX99"):
        _adapter().get_chain("XXXX99")


@pytest.mark.parametrize("janela", [0, 1])
def test_janela_de_vol_invalida(janela: int) -> None:
    with pytest.raises(ValueError, match="realized_vol_window"):
        _adapter(realized_vol_window=janela)


def test_sem_arquivos_cotahist() -> None:
    with pytest.raises(ValueError, match="ao menos um arquivo"):
        _adapter(cotahist_paths=[])


def test_arquivo_ausente_falha_na_carga(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        _adapter(cotahist_paths=[tmp_path / "nao_existe.TXT"])


# ---------------------------------------------------------------------------
# Séries
# ---------------------------------------------------------------------------


def test_zero_da_fonte_chega_como_none(petr4: OptionChain) -> None:
    """Critério de aceite: campo zerado na fonte chega ao domínio como None, nunca 0.0."""
    series = _por_simbolo(petr4)
    so_bid, so_ask = series["PETRK320"], series["PETRK330"]
    vazio_com, vazio_sem = series["PETRW260"], series["PETRW270"]
    assert so_bid.ask is None and so_bid.bid is not None
    assert so_ask.bid is None and so_ask.ask is not None
    assert vazio_com.bid is None and vazio_com.ask is None
    assert vazio_com.last is not None and vazio_com.trades == 3
    assert (vazio_sem.bid, vazio_sem.ask, vazio_sem.last, vazio_sem.trades) == (
        None,
        None,
        None,
        0,
    )
    assert vazio_sem.is_theoretical_eligible


def test_termos_vem_do_arquivo_e_o_estilo_do_cadastro(petr4: OptionChain) -> None:
    series = _por_simbolo(petr4)
    call_americana = series["PETRK310"].contract.terms
    assert (call_americana.strike, call_americana.expiry) == (31.0, date(2026, 11, 19))
    assert call_americana.option_type is OptionType.CALL
    assert call_americana.exercise_style is ExerciseStyle.AMERICAN
    assert call_americana.underlying == "PETR4"
    put_europeia = series["PETRX310"].contract.terms
    assert (put_europeia.option_type, put_europeia.exercise_style) == (
        OptionType.PUT,
        ExerciseStyle.EUROPEAN,
    )
    assert put_europeia.expiry == date(2026, 12, 18)
    assert series["PETRX300"].contract.terms.exercise_style is ExerciseStyle.AMERICAN


def test_volume_financeiro_e_negocios(petr4: OptionChain) -> None:
    quote = _por_simbolo(petr4)["PETRK300"]
    assert quote.trades > 0
    assert quote.last is not None
    assert_close(
        quote.volume,
        quote.trades * 100 * quote.last,
        rel=REL_SELF,
        abs_=0.005,
        label="volume financeiro (gerador: negócios x 100 x último, ao centavo)",
    )


def test_timestamp_marca_o_fim_do_pregao_no_fuso_da_b3(petr4: OptionChain) -> None:
    esperado = datetime.combine(REFERENCE_SESSION, time(18, 0), tzinfo=B3_UTC_OFFSET)
    assert petr4.underlying.timestamp == esperado
    assert all(q.timestamp == esperado for q in petr4.quotes)
    assert esperado.astimezone(UTC).hour == 21


def test_series_ordenadas_por_vencimento_tipo_e_strike(petr4: OptionChain) -> None:
    chaves = [
        (q.contract.terms.expiry, q.contract.terms.option_type.value, q.contract.terms.strike)
        for q in petr4.quotes
    ]
    assert chaves == sorted(chaves)


@pytest.mark.parametrize(
    ("simbolo", "motivo"),
    [
        ("PETRK340", "sem estilo de exercício no cadastro"),
        ("PETRK350", "ausente do cadastro"),
        ("PETRW250", "strike corrigido por índice (INDOPC=1)"),
        ("PETRK285", "book cruzado na fonte"),
        ("PETRW315", "registros divergentes do ticker"),
        ("PETRJ300", "vencimento 2026-10-16 anterior ao pregão"),
        ("PETRK360", "vínculo com o ativo-objeto ambíguo"),
    ],
)
def test_series_rejeitadas_com_motivo(petr4: OptionChain, simbolo: str, motivo: str) -> None:
    rejeitadas = _rejeitadas(petr4)
    assert motivo in rejeitadas[simbolo]
    assert simbolo not in _por_simbolo(petr4)


def test_vinculo_ambiguo_aparece_nas_duas_cadeias_da_raiz() -> None:
    adapter = _adapter()
    assert "PETRK360" in _rejeitadas(adapter.get_chain("PETR3"))
    assert "PETRK360" in _rejeitadas(adapter.get_chain("PETR4"))


def test_classe_do_especi_separa_petr3_de_petr4() -> None:
    petr3 = _adapter().get_chain("PETR3")
    assert sorted(_por_simbolo(petr3)) == ["PETRK312", "PETRK322", "PETRK332"]
    assert all(q.contract.terms.underlying == "PETR3" for q in petr3.quotes)


def test_ativo_objeto_do_cadastro_prevalece_sobre_o_especi(petr4: OptionChain) -> None:
    """PETRK305 tem ESPECI ON (iria para PETR3), mas o cadastro diz PETR4."""
    assert "PETRK305" in _por_simbolo(petr4)
    assert "PETRK305" not in _por_simbolo(_adapter().get_chain("PETR3"))


def test_le_o_mesmo_pregao_de_um_zip(tmp_path: Path, petr4: OptionChain) -> None:
    zip_path = tmp_path / "COTAHIST_A2026.ZIP"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(COTAHIST, arcname=COTAHIST_NAME)
    assert _adapter(cotahist_paths=[zip_path]).get_chain("PETR4") == petr4


def test_arquivos_sobrepostos_nao_duplicam_series(tmp_path: Path, petr4: OptionChain) -> None:
    """Anual + diário com o mesmo pregão: registros idênticos colapsam."""
    copia = tmp_path / "COTAHIST_D23102026.TXT"
    copia.write_bytes(COTAHIST.read_bytes())
    assert _adapter(cotahist_paths=[COTAHIST, copia]).get_chain("PETR4") == petr4


def test_cache_por_pregao(tmp_path: Path, petr4: OptionChain) -> None:
    cache = tmp_path / "pregoes.sqlite"
    primeiro = _adapter(cache_path=cache)
    segundo = _adapter(cache_path=cache)
    assert (primeiro.loaded_from_cache, segundo.loaded_from_cache) == (False, True)
    assert segundo.get_chain("PETR4") == petr4
    assert segundo.session_data == primeiro.session_data


# ---------------------------------------------------------------------------
# Casos montados à mão em tmp_path
# ---------------------------------------------------------------------------


def _mini(tmp_path: Path, registros: list[str], cadastro: list[str] | None = None) -> Path:
    """Grava um COTAHIST mínimo e um cadastro; devolve o diretório."""
    (tmp_path / "C.TXT").write_bytes(
        arquivo(registros, geracao=REFERENCE_SESSION, ano=2026).encode("cp1252")
    )
    linhas = ["TckrSymb;OptnStyle", *(cadastro or [])]
    (tmp_path / "I.csv").write_bytes("\r\n".join(linhas).encode("utf-8"))
    return tmp_path


def _mini_adapter(diretorio: Path, **overrides: object) -> CotahistOptionChainAdapter:
    return _adapter(
        cotahist_paths=[diretorio / "C.TXT"], instruments_path=diretorio / "I.csv", **overrides
    )


def _historico(simbolo: str, fechamentos: list[float]) -> list[str]:
    dias = sorted(REFERENCE_SESSION - timedelta(days=i) for i in range(len(fechamentos)))
    return [
        registro(pregao=dia, simbolo=simbolo, mercado=MARKET_SPOT, ultimo=valor)
        for dia, valor in zip(dias, fechamentos, strict=True)
    ]


def test_vol_realizada_zero_deixa_o_ativo_indisponivel(tmp_path: Path) -> None:
    diretorio = _mini(tmp_path, _historico("ABCD3", [10.0] * 5))
    with pytest.raises(UnderlyingUnavailableError, match="vol realizada zero"):
        _mini_adapter(diretorio, realized_vol_window=4).get_chain("ABCD3")


def test_registros_divergentes_do_ativo_objeto_no_pregao(tmp_path: Path) -> None:
    linhas = [
        *_historico("ABCD3", [10.0, 10.2, 9.9, 10.1, 10.0]),
        registro(pregao=REFERENCE_SESSION, simbolo="ABCD3", mercado=MARKET_SPOT, ultimo=10.3),
    ]
    diretorio = _mini(tmp_path, linhas)
    with pytest.raises(UnderlyingUnavailableError, match="registros divergentes do ativo-objeto"):
        _mini_adapter(diretorio, realized_vol_window=4).get_chain("ABCD3")


def test_serie_com_strike_zero_na_fonte_e_rejeitada(tmp_path: Path) -> None:
    linhas = [
        *_historico("ABCD3", [10.0, 10.2, 9.9, 10.1, 10.0]),
        registro(
            pregao=REFERENCE_SESSION,
            simbolo="ABCDK100",
            mercado=70,
            ultimo=0.5,
            strike=0.0,
            vencimento=date(2026, 11, 19),
        ),
    ]
    diretorio = _mini(tmp_path, linhas, ["ABCDK100;AMER"])
    chain = _mini_adapter(diretorio, realized_vol_window=4).get_chain("ABCD3")
    assert _rejeitadas(chain) == {"ABCDK100": "strike zero na fonte"}


def test_zip_com_crc_corrompido_e_erro_de_formato(tmp_path: Path) -> None:
    zip_path = tmp_path / "C.ZIP"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("C.TXT", COTAHIST.read_text(encoding="cp1252"))
    bruto = bytearray(zip_path.read_bytes())
    bruto[200] ^= 0xFF  # dentro dos dados do membro: CRC não confere
    zip_path.write_bytes(bytes(bruto))
    with pytest.raises(CotahistFormatError, match="ZIP corrompido"):
        _adapter(cotahist_paths=[zip_path])

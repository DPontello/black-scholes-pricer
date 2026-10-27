"""Mescla de arquivos por pregão e cache sqlite — hit, miss, invalidação e banco corrompido."""

import os
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import date
from pathlib import Path

from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_CALL,
    MARKET_SPOT,
    CotahistRecord,
)
from options_engine.adapters.outbound.cotahist.session import build_session_data, load_session_data
from tests.adapters.cotahist._layout import arquivo, registro

PREGAO = date(2026, 10, 23)
ANTERIOR = date(2026, 10, 22)
POSTERIOR = date(2026, 10, 26)


def _rec(symbol: str, session: date, last: float, market: int = MARKET_SPOT) -> CotahistRecord:
    return CotahistRecord(
        session=session,
        bdi_code="02",
        symbol=symbol,
        market=market,
        short_name=symbol[:4],
        specification="PN",
        last=last,
        best_bid=0.0,
        best_ask=0.0,
        trades=1,
        quantity=100,
        volume=last * 100,
        strike=0.0,
        strike_correction=0,
        expiry=date(9999, 12, 31),
        quote_factor=1,
    )


def test_registros_identicos_de_arquivos_sobrepostos_colapsam() -> None:
    """O anual contém o diário: o mesmo registro em dois arquivos é um só."""
    dados = build_session_data(
        [[_rec("PETR4", PREGAO, 30.0)], [_rec("PETR4", PREGAO, 30.0)]], PREGAO
    )
    assert [r.symbol for r in dados.records] == ["PETR4"]
    assert dados.divergent_symbols == frozenset()


def test_registros_divergentes_no_pregao_marcam_o_ticker() -> None:
    dados = build_session_data(
        [[_rec("PETR4", PREGAO, 30.0)], [_rec("PETR4", PREGAO, 31.0)]], PREGAO
    )
    assert dados.divergent_symbols == frozenset({"PETR4"})


def test_historico_ate_o_pregao_com_primeiro_arquivo_valendo() -> None:
    primeiro = [_rec("PETR4", ANTERIOR, 29.5), _rec("PETR4", PREGAO, 30.0)]
    segundo = [_rec("PETR4", ANTERIOR, 29.9), _rec("PETR4", POSTERIOR, 31.0)]
    dados = build_session_data([primeiro, segundo], PREGAO)
    assert dados.closes["PETR4"] == ((ANTERIOR, 29.5), (PREGAO, 30.0))


def test_fechamento_zero_fica_fora_do_historico_e_opcao_nao_entra() -> None:
    dados = build_session_data(
        [
            [
                _rec("PETR4", ANTERIOR, 0.0),
                _rec("PETR4", PREGAO, 30.0),
                _rec("PETRK300", PREGAO, 1.0, MARKET_CALL),
            ]
        ],
        PREGAO,
    )
    assert dados.closes == {"PETR4": ((PREGAO, 30.0),)}
    assert {r.symbol for r in dados.records} == {"PETR4", "PETRK300"}


def test_ticker_conhecido_mesmo_sem_registro_no_pregao() -> None:
    dados = build_session_data(
        [[_rec("BBAS3", ANTERIOR, 28.0), _rec("ITUB4", POSTERIOR, 35.0)]], PREGAO
    )
    assert dados.known_spot_symbols == frozenset({"BBAS3", "ITUB4"})
    assert dados.records == ()


# ---------------------------------------------------------------------------
# Cache sqlite
# ---------------------------------------------------------------------------


def _cotahist(tmp_path: Path, nome: str = "COTAHIST.TXT", ultimo: float = 30.0) -> Path:
    linhas = [
        registro(pregao=ANTERIOR, simbolo="PETR4", mercado=MARKET_SPOT, ultimo=29.5),
        registro(pregao=PREGAO, simbolo="PETR4", mercado=MARKET_SPOT, ultimo=ultimo),
    ]
    caminho = tmp_path / nome
    caminho.write_bytes(arquivo(linhas, geracao=PREGAO, ano=2026).encode("cp1252"))
    return caminho


def test_primeira_carga_e_miss_e_a_segunda_e_hit_com_os_mesmos_dados(tmp_path: Path) -> None:
    fonte, cache = _cotahist(tmp_path), tmp_path / "cache.sqlite"
    dados, do_cache = load_session_data([fonte], PREGAO, cache)
    assert do_cache is False
    assert cache.exists()
    de_novo, do_cache = load_session_data([fonte], PREGAO, cache)
    assert do_cache is True
    assert de_novo == dados


def test_sem_caminho_de_cache_nada_e_gravado(tmp_path: Path) -> None:
    fonte = _cotahist(tmp_path)
    _, do_cache = load_session_data([fonte], PREGAO, None)
    assert do_cache is False
    assert sorted(p.name for p in tmp_path.iterdir()) == ["COTAHIST.TXT"]


def test_arquivo_alterado_invalida_o_cache(tmp_path: Path) -> None:
    fonte, cache = _cotahist(tmp_path), tmp_path / "cache.sqlite"
    load_session_data([fonte], PREGAO, cache)
    _cotahist(tmp_path, ultimo=30.5)  # mesmo caminho, conteúdo e mtime novos
    status = fonte.stat()
    os.utime(fonte, ns=(status.st_atime_ns, status.st_mtime_ns + 1_000_000_000))
    dados, do_cache = load_session_data([fonte], PREGAO, cache)
    assert do_cache is False
    assert dados.closes["PETR4"][-1] == (PREGAO, 30.5)


def test_outro_pregao_ou_outro_conjunto_de_arquivos_e_miss(tmp_path: Path) -> None:
    fonte, cache = _cotahist(tmp_path), tmp_path / "cache.sqlite"
    load_session_data([fonte], PREGAO, cache)
    assert load_session_data([fonte], ANTERIOR, cache)[1] is False
    outro = _cotahist(tmp_path, nome="OUTRO.TXT")
    assert load_session_data([fonte, outro], PREGAO, cache)[1] is False


def test_arquivo_de_cache_que_nao_e_sqlite_nunca_e_apagado(tmp_path: Path) -> None:
    """Caminho errado apontando para um arquivo do usuário: reparse, sem tocar nele."""
    fonte, cache = _cotahist(tmp_path), tmp_path / "importante.txt"
    cache.write_bytes(b"conteudo do usuario que nao e um banco sqlite" * 10)
    original = cache.read_bytes()
    dados, do_cache = load_session_data([fonte], PREGAO, cache)
    assert do_cache is False
    assert dados.closes["PETR4"][-1] == (PREGAO, 30.0)
    assert cache.read_bytes() == original


def test_payload_ilegivel_vira_reparse_e_e_regravado(tmp_path: Path) -> None:
    fonte, cache = _cotahist(tmp_path), tmp_path / "cache.sqlite"
    load_session_data([fonte], PREGAO, cache)
    with closing(sqlite3.connect(cache)) as conexao, conexao:
        conexao.execute("UPDATE pregoes SET payload = '{nao e json'")
    dados, do_cache = load_session_data([fonte], PREGAO, cache)
    assert do_cache is False
    assert load_session_data([fonte], PREGAO, cache) == (dados, True)


def test_cache_preserva_todos_os_campos_do_registro(tmp_path: Path) -> None:
    fonte, cache = _cotahist(tmp_path), tmp_path / "cache.sqlite"
    dados, _ = load_session_data([fonte], PREGAO, cache)
    em_cache, _ = load_session_data([fonte], PREGAO, cache)
    assert em_cache.records == dados.records
    assert em_cache.records[0] == replace(dados.records[0])

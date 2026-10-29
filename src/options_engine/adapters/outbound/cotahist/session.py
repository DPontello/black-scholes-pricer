"""Dados de UM pregão extraídos dos arquivos COTAHIST, com cache ``sqlite3`` opcional.

Vários arquivos (diário, mensal, anual) são mesclados: o pregão de
referência dá os registros da cadeia, e todos os pregões até ele dão o
histórico de fechamentos para a vol realizada. Arquivos sobrepostos são o
caso normal (o anual contém o diário):

- registros IDÊNTICOS do mesmo ticker no pregão colapsam em um;
- registros DIVERGENTES do mesmo ticker no pregão marcam o ticker
  (``divergent_symbols``) — a montagem da cadeia o rejeita com motivo;
- no histórico de fechamentos, vale o primeiro arquivo da lista em cada
  (ticker, pregão).

Cache: chave = formato do cache + pregão + impressão digital de cada
arquivo (caminho absoluto, tamanho, mtime). Chave ausente, payload ilegível
ou banco corrompido -> reparse. O cache é otimização: falha de escrita não
derruba a carga, e um arquivo que não é banco sqlite NUNCA é apagado nem
sobrescrito — só o caminho dado é tocado, e só via sqlite.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import astuple, dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any, Final

from options_engine.adapters.outbound.cotahist.parser import (
    MARKET_SPOT,
    CotahistRecord,
    iter_cotahist,
)

__all__ = ["SessionData", "build_session_data", "load_session_data"]

_CACHE_FORMAT: Final = 1
_DATE_FIELDS: Final = frozenset({"session", "expiry"})


@dataclass(frozen=True, slots=True)
class SessionData:
    """Tudo o que a cadeia de um pregão precisa, já mesclado entre arquivos.

    ``records``: um registro por ticker no pregão (à vista, call, put), na
    ordem dos arquivos. ``closes``: fechamentos > 0 do à vista até o pregão
    (inclusive), por ticker, em ordem de data. ``known_spot_symbols``: todo
    ticker à vista visto em qualquer pregão de qualquer arquivo — é o que
    separa "desconhecido" de "sem preço no pregão".
    """

    session: date
    records: tuple[CotahistRecord, ...]
    divergent_symbols: frozenset[str]
    closes: Mapping[str, tuple[tuple[date, float], ...]]
    known_spot_symbols: frozenset[str]


def build_session_data(
    records_per_file: Iterable[Iterable[CotahistRecord]], session: date
) -> SessionData:
    """Mescla os registros de vários arquivos para o pregão ``session``."""
    do_pregao: dict[str, CotahistRecord] = {}
    divergentes: set[str] = set()
    fechamentos: dict[str, dict[date, float]] = {}
    conhecidos: set[str] = set()
    for registros in records_per_file:
        for registro in registros:
            if registro.market == MARKET_SPOT:
                conhecidos.add(registro.symbol)
                if registro.session <= session and registro.last > 0.0:
                    fechamentos.setdefault(registro.symbol, {}).setdefault(
                        registro.session, registro.last
                    )
            if registro.session != session:
                continue
            anterior = do_pregao.setdefault(registro.symbol, registro)
            if anterior != registro:
                divergentes.add(registro.symbol)
    return SessionData(
        session=session,
        records=tuple(do_pregao.values()),
        divergent_symbols=frozenset(divergentes),
        closes={
            simbolo: tuple(sorted(por_data.items())) for simbolo, por_data in fechamentos.items()
        },
        known_spot_symbols=frozenset(conhecidos),
    )


# ---------------------------------------------------------------------------
# Serialização para o cache
# ---------------------------------------------------------------------------

_RECORD_FIELDS: Final = tuple(campo.name for campo in fields(CotahistRecord))


def _serializar(dados: SessionData) -> str:
    def registro(r: CotahistRecord) -> list[Any]:
        return [
            valor.isoformat() if nome in _DATE_FIELDS else valor
            for nome, valor in zip(_RECORD_FIELDS, astuple(r), strict=True)
        ]

    return json.dumps(
        {
            "session": dados.session.isoformat(),
            "records": [registro(r) for r in dados.records],
            "divergent": sorted(dados.divergent_symbols),
            "closes": {
                s: [[d.isoformat(), v] for d, v in serie] for s, serie in dados.closes.items()
            },
            "known": sorted(dados.known_spot_symbols),
        }
    )


def _desserializar(payload: str) -> SessionData:
    bruto = json.loads(payload)

    def registro(valores: list[Any]) -> CotahistRecord:
        campos: dict[str, Any] = {
            nome: date.fromisoformat(valor) if nome in _DATE_FIELDS else valor
            for nome, valor in zip(_RECORD_FIELDS, valores, strict=True)
        }
        return CotahistRecord(**campos)

    return SessionData(
        session=date.fromisoformat(bruto["session"]),
        records=tuple(registro(r) for r in bruto["records"]),
        divergent_symbols=frozenset(bruto["divergent"]),
        closes={
            s: tuple((date.fromisoformat(d), float(v)) for d, v in serie)
            for s, serie in bruto["closes"].items()
        },
        known_spot_symbols=frozenset(bruto["known"]),
    )


def _chave(paths: Sequence[Path], session: date) -> str:
    impressoes = []
    for path in paths:
        status = path.stat()
        impressoes.append([str(path.resolve()), status.st_size, status.st_mtime_ns])
    bruto = json.dumps(
        {"formato": _CACHE_FORMAT, "pregao": session.isoformat(), "arquivos": impressoes}
    )
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


def _ler_cache(cache_path: Path, chave: str) -> SessionData | None:
    if not cache_path.exists():
        return None
    try:
        with closing(sqlite3.connect(cache_path)) as conexao:
            linha = conexao.execute(
                "SELECT payload FROM pregoes WHERE chave = ?", (chave,)
            ).fetchone()
    except sqlite3.Error:
        return None
    if linha is None:
        return None
    try:
        return _desserializar(linha[0])
    except (ValueError, KeyError, TypeError):
        return None


def _gravar_cache(cache_path: Path, chave: str, dados: SessionData) -> None:
    try:
        with closing(sqlite3.connect(cache_path)) as conexao, conexao:
            conexao.execute(
                "CREATE TABLE IF NOT EXISTS pregoes (chave TEXT PRIMARY KEY, payload TEXT NOT NULL)"
            )
            conexao.execute(
                "INSERT OR REPLACE INTO pregoes (chave, payload) VALUES (?, ?)",
                (chave, _serializar(dados)),
            )
    except sqlite3.Error:
        return


def load_session_data(
    paths: Sequence[Path], session: date, cache_path: Path | None = None
) -> tuple[SessionData, bool]:
    """Dados do pregão e se vieram do cache (``True``) ou de um parse novo.

    Arquivo ausente propaga ``OSError``; arquivo fora do layout,
    ``CotahistFormatError`` — os dois na carga, nunca na consulta ao port.
    """
    chave = _chave(paths, session)
    if cache_path is not None:
        em_cache = _ler_cache(cache_path, chave)
        if em_cache is not None:
            return em_cache, True

    # Do anual só interessam o à vista (histórico) e o pregão: o resto não vira registro.
    def usados(pregao: date, mercado: int) -> bool:
        return mercado == MARKET_SPOT or pregao == session

    dados = build_session_data((iter_cotahist(path, usados) for path in paths), session)
    if cache_path is not None:
        _gravar_cache(cache_path, chave, dados)
    return dados, False

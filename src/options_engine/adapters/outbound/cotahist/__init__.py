"""Adapter COTAHIST da B3 — cadeia de opções de fim de dia a partir de arquivos locais.

Só stdlib (``zipfile``, ``sqlite3``, ``csv``, ``statistics``): parser de
largura fixa (``parser``), cadastro de instrumentos (``instruments``),
mesclagem de arquivos por pregão com cache (``session``) e o port
(``adapter``). ADR-0006.
"""

from options_engine.adapters.outbound.cotahist.adapter import CotahistOptionChainAdapter
from options_engine.adapters.outbound.cotahist.errors import (
    CotahistFormatError,
    InstrumentsFileError,
    SourceFileError,
)

__all__ = [
    "CotahistFormatError",
    "CotahistOptionChainAdapter",
    "InstrumentsFileError",
    "SourceFileError",
]

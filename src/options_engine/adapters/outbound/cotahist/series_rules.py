"""Regras de série do COTAHIST compartilhadas pela cadeia de fim de dia e pelo histórico de IV.

Vínculo com o ativo-objeto: o cadastro (``UndrlygTckrSymb1`` ou o ``Asst`` da opção), senão a
raiz única entre os ativos à vista do pregão, senão a classe do ESPECI (``"PN N2"`` -> ``"PN"``).
Raiz dividida sem desempate -> série rejeitada com o motivo.
"""

from collections.abc import Mapping
from datetime import date
from typing import Final

from options_engine.adapters.outbound.cotahist.instruments import InstrumentInfo
from options_engine.adapters.outbound.cotahist.parser import CotahistRecord
from options_engine.domain.model.chain import RejectedSeries

__all__ = ["link_underlying", "record_rejection", "series_root", "specification_class"]

_ROOT_LENGTH: Final = 4


def series_root(symbol: str) -> str:
    return symbol[:_ROOT_LENGTH]


def specification_class(specification: str) -> str:
    termos = specification.split()
    return termos[0].upper() if termos else ""


def link_underlying(
    record: CotahistRecord,
    spot_records: Mapping[str, CotahistRecord],
    instruments: Mapping[str, InstrumentInfo],
) -> str | RejectedSeries:
    """Ativo-objeto da série; ``spot_records`` são os registros à vista do mesmo pregão."""
    info = instruments.get(record.symbol)
    if info is not None and info.underlying_symbol is not None:
        return info.underlying_symbol
    raiz = series_root(record.symbol)
    candidatos = sorted(s for s in spot_records if series_root(s) == raiz)
    if len(candidatos) == 1:
        return candidatos[0]
    classe = specification_class(record.specification)
    mesma_classe = [
        c for c in candidatos if specification_class(spot_records[c].specification) == classe
    ]
    if len(mesma_classe) == 1:
        return mesma_classe[0]
    return RejectedSeries(
        record.symbol,
        f"vínculo com o ativo-objeto ambíguo: raiz {raiz!r} em {candidatos!r} e "
        f"especificação {record.specification!r}",
    )


def record_rejection(record: CotahistRecord, session: date) -> str | None:
    """Motivo de rejeição que só depende do registro, ou ``None`` se a série é utilizável."""
    if record.strike_correction != 0:
        return f"strike corrigido por índice (INDOPC={record.strike_correction})"
    if record.expiry < session:
        return f"vencimento {record.expiry.isoformat()} anterior ao pregão"
    if record.best_bid > 0.0 and record.best_ask > 0.0 and record.best_bid > record.best_ask:
        return (
            f"book cruzado na fonte: oferta de compra {record.best_bid} > venda {record.best_ask}"
        )
    if record.strike <= 0.0:
        return "strike zero na fonte"
    return None

"""Rótulo da fonte de uma consulta que leu a saúde antes e depois: vale a menos fresca."""

from typing import Final

from options_engine.domain.model.quotes import DataSource

__all__ = ["least_fresh"]

_FRESHNESS: Final = {DataSource.AO_VIVO: 2, DataSource.ATRASADO: 1, DataSource.FIM_DE_DIA: 0}


def least_fresh(first: DataSource, second: DataSource) -> DataSource:
    return first if _FRESHNESS[first] <= _FRESHNESS[second] else second

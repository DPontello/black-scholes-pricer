"""Quando o strike do Cadastro da B3 difere do strike em vigor na Carteira (tarefa 1.5).

Decisão do autor (16/11): queda de até 15% é provento em dinheiro e se aplica sozinha. Alta, ou
queda maior, costuma ser desdobramento, grupamento ou bonificação, que mudam também a quantidade:
não se aplica e vira o alerta "confira". O app não tem dados de proventos para distinguir; a
bonificação de 10% cai na faixa do provento (custo aceito na decisão).
"""

from enum import StrEnum
from math import isfinite
from typing import Final

from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["MAX_PROVENTO_DROP", "StrikeChange", "strike_change"]

MAX_PROVENTO_DROP: Final = 0.15
# Strikes da B3 têm duas casas: meio centavo separa ruído de arredondamento de mudança.
_MEIO_CENTAVO: Final = 0.005


class StrikeChange(StrEnum):
    SAME = "igual"
    APPLY = "aplicar"
    CHECK = "conferir"


def strike_change(current: float, listed: float) -> StrikeChange:
    """O que fazer com o strike ``listed`` do Cadastro diante do ``current`` em vigor."""
    for nome, valor in (("em vigor", current), ("do Cadastro", listed)):
        if not (isfinite(valor) and valor > 0.0):
            raise InvalidDomainValueError(f"strike {nome} inválido: {valor!r}")
    if abs(listed - current) < _MEIO_CENTAVO:
        return StrikeChange.SAME
    if listed < current and listed >= current * (1.0 - MAX_PROVENTO_DROP) - _MEIO_CENTAVO:
        return StrikeChange.APPLY
    return StrikeChange.CHECK

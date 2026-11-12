"""Perna de opção depois do pregão do vencimento: pó, exercício a registrar ou à espera."""

from enum import Enum, unique

from options_engine.domain.model.enums import OptionType

__all__ = ["ExpiryOutcome", "expiry_outcome"]


@unique
class ExpiryOutcome(Enum):
    PO = "po"
    REGISTRAR_EXERCICIO = "registrar_exercicio"
    AGUARDANDO_FECHAMENTO = "aguardando_fechamento"


def expiry_outcome(option_type: OptionType, strike: float, close: float | None) -> ExpiryOutcome:
    """Pó só fora do dinheiro estrito pelo fechamento do pregão do vencimento (decisão do autor,
    31/10); no dinheiro ou dentro, quem registra o que houve é o usuário."""
    if close is None:
        return ExpiryOutcome.AGUARDANDO_FECHAMENTO
    fora = close < strike if option_type is OptionType.CALL else close > strike
    return ExpiryOutcome.PO if fora else ExpiryOutcome.REGISTRAR_EXERCICIO

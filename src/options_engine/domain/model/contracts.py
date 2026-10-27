"""Termos econômicos (VO) e contrato listado (Entity).

A separação é o critério tático do ARCHITECTURE §2: ``OptionTerms`` tem
igualdade estrutural (dois conjuntos de termos idênticos são economicamente
intercambiáveis); ``OptionContract`` tem igualdade por identidade (tickers
distintos são instrumentos distintos, com books separados — mesmo que os
termos coincidam).
"""

from dataclasses import dataclass
from datetime import date
from math import isfinite

from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = ["OptionContract", "OptionTerms"]


@dataclass(frozen=True, slots=True)
class OptionTerms:
    """Termos econômicos de uma opção, SEM o ticker.

    ``underlying`` é o símbolo do ativo-objeto (ex.: PETR4) — é informação
    econômica, não identidade: termos de subjacentes diferentes nunca são
    intercambiáveis, e o agregado ``Strategy`` valida "mesmo subjacente"
    (decisão nº 6) lendo daqui. A identidade do instrumento listado (ticker,
    ex.: PETRA250) pertence à Entity ``OptionContract``.

    ``exercise_style`` tem default EUROPEAN por ser o escopo ratificado do
    MVP (decisão nº 2). AMERICAN é construível (legal no domínio): nos
    caminhos de precificação, a call americana vira aproximação europeia
    marcada (ADR-0002) e a put americana é rejeitada. Aceitar ou rejeitar
    é decisão do modelo (``supports()``), nunca da construção dos termos.
    """

    underlying: str
    strike: float
    expiry: date
    option_type: OptionType
    exercise_style: ExerciseStyle = ExerciseStyle.EUROPEAN

    def __post_init__(self) -> None:
        if not self.underlying:
            raise InvalidDomainValueError("underlying não pode ser vazio")
        if not (isfinite(self.strike) and self.strike > 0.0):
            raise InvalidDomainValueError(f"strike deve ser finito e > 0; recebido {self.strike!r}")


@dataclass(frozen=True, slots=True, eq=False)
class OptionContract:
    """Instrumento listado — Entity com identidade = ticker (ex.: PETRA250).

    Igualdade e hash exclusivamente pelo ``symbol``: termos idênticos com
    tickers distintos são instrumentos distintos, com books separados.
    Atributos imutáveis pós-listagem — o que autoriza ``StrategyLeg`` a
    carregar uma cópia dos ``terms`` sem risco de snapshot stale.
    """

    symbol: str
    terms: OptionTerms

    def __post_init__(self) -> None:
        if not self.symbol:
            raise InvalidDomainValueError("symbol não pode ser vazio")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OptionContract):
            return NotImplemented
        return self.symbol == other.symbol

    def __hash__(self) -> int:
        return hash(self.symbol)

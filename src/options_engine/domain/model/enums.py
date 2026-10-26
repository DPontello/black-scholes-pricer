"""Enums fundamentais do domínio — tipo, estilo de exercício e direção.

Cada enum existe para tornar um antipadrão irrepresentável:
``OptionType`` elimina ``is_call: bool`` em objetos de negócio;
``ExerciseStyle`` impede precificar americano errado em silêncio (decisão
nº 2, emendada pela ADR-0002);
``Side`` impede direção em quantidade negativa (decisão do CONVENTIONS §4);
``PricingApproximation`` impede que uma aproximação aceita por ADR viaje
como preço exato (ADR-0002).
"""

from enum import Enum, unique

__all__ = ["ExerciseStyle", "OptionType", "PricingApproximation", "Side"]


@unique
class OptionType(Enum):
    """CALL ou PUT — no domínio, o tipo é sempre este enum.

    ``is_call: bool`` keyword-only é representação exclusiva do kernel
    (functional core, floats puros); esta propriedade é a fronteira única
    de tradução enum -> bool do shell.
    """

    CALL = "call"
    PUT = "put"

    @property
    def is_call(self) -> bool:
        return self is OptionType.CALL


@unique
class ExerciseStyle(Enum):
    """Estilo de exercício — primeira classe porque na B3 varia por instrumento.

    AMERICAN existe no enum (é legal no domínio: há séries americanas na
    B3). Black-Scholes europeu nunca finge suporte exato (decisão ratificada
    nº 2, emendada pela ADR-0002): a CALL americana de ação é aceita pelo
    ``PricingModel`` como aproximação europeia e sai marcada com
    ``PricingApproximation``; a PUT americana é rejeitada com
    ``UnsupportedExerciseStyleError``, assim como qualquer leg americana no
    motor de simulação. Precificação americana exata (binomial) entra na
    Fase 6.
    """

    EUROPEAN = "european"
    AMERICAN = "american"


@unique
class PricingApproximation(Enum):
    """Aproximação de modelo aceita por decisão registrada — marca do resultado.

    ``supports()`` verdadeiro não implica preço exato: um modelo pode aceitar
    termos fora da sua hipótese matemática quando uma ADR justifica o desvio.
    A marca viaja no ``PricingResult`` para que nenhuma borda (painel, API)
    apresente uma aproximação como se fosse o preço do modelo exato.
    Catálogo fechado: cada membro nasce de uma ADR, nunca de conveniência.

    - ``AMERICAN_CALL_AS_EUROPEAN``: call americana de ação precificada por
      Black-Scholes europeu com ``q = 0`` (ADR-0002). Defensável porque a B3
      ajusta o strike pelos proventos em dinheiro, o que remove a maior parte
      do incentivo ao exercício antecipado da call.
    """

    AMERICAN_CALL_AS_EUROPEAN = "american_call_as_european"


@unique
class Side(Enum):
    """Direção de uma leg: BUY (comprado) ou SELL (vendido).

    A direção NUNCA vive em quantidade negativa — ``SELL/-10`` é a
    ambiguidade que inverte P&L em silêncio (CONVENTIONS §4).
    """

    BUY = "buy"
    SELL = "sell"

    @property
    def sign(self) -> int:
        """Sinal da exposição: +1 comprado, -1 vendido.

        ÚNICO lugar do código que deriva sinal de direção (CONVENTIONS §4)
        — exposição assinada é sempre ``side.sign * quantity``.
        """
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        """Lado espelhado — usado pela propriedade short == -long da suíte."""
        return Side.SELL if self is Side.BUY else Side.BUY

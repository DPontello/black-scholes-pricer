"""Hierarquia de exceções do domínio — catálogo canônico único.

Toda falha de regra de domínio deriva de ``DomainError`` — é o contrato que
permite ao adapter HTTP (Sprint 4) mapear qualquer erro de negócio para um
422 estruturado, nunca um 500 opaco. Exceções cruas (``ValueError``,
``KeyError``) não podem atravessar as fronteiras do domínio.

O catálogo espelha a tabela normativa de fronteiras (docs/ARCHITECTURE.md
§6): cada classe existe porque há uma regra de negócio ratificada que a
exige — nenhuma é especulativa.
"""

from datetime import datetime

__all__ = [
    "DomainError",
    "DuplicateProfileError",
    "EmptyStrategyError",
    "ExpiredOptionError",
    "InvalidDomainValueError",
    "InvalidKernelInputError",
    "InvalidStrategyError",
    "MissingPremiumError",
    "MixedAnnualizationBaseError",
    "MixedExpiryError",
    "MixedUnderlyingError",
    "NoActiveProfileError",
    "ProfileFolderUnavailableError",
    "ProfileLockedError",
    "UnderlyingUnavailableError",
    "UnknownProfileError",
    "UnknownSymbolError",
    "UnsupportedExerciseStyleError",
]


class DomainError(Exception):
    """Raiz da hierarquia de exceções de domínio."""


class InvalidKernelInputError(DomainError):
    """Pré-condição do kernel violada (s<=0, k<=0, sigma<0, tau<0, r/q não finitos).

    Os Value Objects tornam essas entradas irrepresentáveis; o kernel mantém
    a checagem como defesa em profundidade, pois é chamável diretamente com
    floats crus.
    """


class InvalidDomainValueError(DomainError):
    """Invariante de Value Object violada na construção (strike<=0, vol<0, ...).

    É a materialização de "estado inválido é irrepresentável": o objeto nem
    chega a existir. Cobre as violações de valor escalar que não pertencem a
    nenhuma regra mais específica abaixo.
    """


class EmptyStrategyError(DomainError):
    """``Strategy`` exige ao menos uma leg (invariante 1 do agregado)."""


class MixedUnderlyingError(DomainError):
    """Legs de subjacentes distintos na mesma ``Strategy`` (decisão ratificada nº 6).

    Restrição de fase, reversível: cross-asset é extensão futura sinalizada.
    """


class MixedExpiryError(DomainError):
    """Legs de vencimentos distintos na mesma ``Strategy`` (decisão ratificada nº 6).

    Restrição de fase, reversível: calendar spreads são extensão futura
    sinalizada.
    """


class InvalidStrategyError(DomainError):
    """Geometria ou composição inválida numa factory nomeada.

    Cobre strikes fora de ordem (``K1 < K2 < K3 < K4`` no condor) E
    composição errada de pernas (tipos/sides que não formam a estrutura
    nomeada) — validar só a ordem deixaria passar um "condor" de 4 calls.
    """


class UnsupportedExerciseStyleError(DomainError):
    """Estilo de exercício legal no domínio, mas fora do modelo (decisão nº 2).

    Desde a emenda da ADR-0002, o Black-Scholes europeu aceita a CALL
    americana como aproximação marcada (``PricingApproximation``), desde que
    a taxa contínua seja >= 0, e rejeita explicitamente a PUT americana, cujo
    exercício antecipado pode ser ótimo mesmo sem dividendos (como o da call
    com taxa negativa); o motor de simulação segue rejeitando qualquer leg
    americana. Precificar errado em silêncio nunca é opção. Suporte
    americano exato (binomial) é Fase 6, atrás do seam ``supports()``.
    """


class MissingPremiumError(DomainError):
    """P&L líquido exigido sem prêmio informado (decisão ratificada nº 4).

    Prêmio é opcional e informado pelo chamador: sem ele, apenas o payoff
    bruto (``payoff_at_expiry``) é calculável — ``pnl`` e breakevens não.
    """


class MixedAnnualizationBaseError(DomainError):
    """Vol e tau em bases de anualização distintas (armadilha do CONVENTIONS §2).

    Vol em base 252 com tau em base 365 produz preço errado sem nenhum erro
    de runtime — os VOs carregam a base exatamente para que esta checagem
    exista na fronteira do motor.
    """


class ExpiredOptionError(DomainError):
    """Vencimento ANTERIOR à data de valoração num caminho de precificação.

    ``expiry == hoje`` é legal — resta 0 dia útil, tau = 0 e a posição vale
    o intrínseco descontado (decisão nº 5). ``expiry < hoje`` não tem preço
    a termo: é a guarda dos use cases (Sprint 3), disparada ANTES da
    contagem de dias — o ``TradingCalendar`` só recebe ``start <= end``.
    """


class UnderlyingUnavailableError(DomainError):
    """Subjacente conhecido na fonte, mas sem preço utilizável no pregão.

    ADR-0004: o ativo "fica fora do painel do dia com motivo explícito" —
    sem fechamento no pregão, ou sem histórico suficiente para a vol
    realizada. A mensagem carrega o motivo, que o painel exibe. Distinta de
    ``UnknownSymbolError``: o símbolo existe, só não há número honesto hoje.
    """


class UnknownSymbolError(DomainError):
    """Símbolo desconhecido na fonte de dados de mercado.

    Parte do contrato de ``MarketDataPort`` (Sprint 3): nunca ``KeyError``
    ou ``None`` vazando pelo port. Declarada aqui porque o catálogo de
    erros é único e canônico.
    """


class ProfileFolderUnavailableError(DomainError):
    """Pasta de perfis fora do ar (nuvem não montada, pendrive removido).

    A mensagem carrega o caminho. Nada é criado em outro lugar e a
    configuração não muda: perfil é dado do usuário, e trocar a pasta em
    silêncio esconderia os perfis reais.
    """


class ProfileLockedError(DomainError):
    """Perfil em uso por outro PC — a trava ainda está dentro do prazo.

    ``machine`` (nome do PC que travou) e ``since`` (quando) viram atributos
    para o chamador pedir confirmação ao usuário citando os dois. Trava
    vencida não chega aqui: é ignorada antes.
    """

    def __init__(self, machine: str, since: datetime) -> None:
        self.machine = machine
        self.since = since
        super().__init__(f"perfil em uso no PC {machine!r} desde {since:%d/%m/%Y} às {since:%H:%M}")


class DuplicateProfileError(DomainError):
    """Já existe um perfil com esse nome."""


class UnknownProfileError(DomainError):
    """Perfil inexistente na pasta de perfis."""


class NoActiveProfileError(DomainError):
    """Operação que exige perfil ativo, sem nenhum selecionado."""

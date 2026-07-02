"""Hierarquia de exceções do domínio.

Toda falha de regra de domínio deriva de ``DomainError`` — é o contrato que
permite ao adapter HTTP (Sprint 4) mapear qualquer erro de negócio para um
422 estruturado, nunca um 500 opaco. Exceções cruas (``ValueError``,
``KeyError``) não podem atravessar as fronteiras do domínio.
"""

__all__ = ["DomainError", "InvalidKernelInputError"]


class DomainError(Exception):
    """Raiz da hierarquia de exceções de domínio."""


class InvalidKernelInputError(DomainError):
    """Pré-condição do kernel violada (s<=0, k<=0, sigma<0, tau<0, r/q não finitos).

    Na Sprint 2 os Value Objects tornam essas entradas irrepresentáveis; o
    kernel mantém a checagem como defesa em profundidade, pois é chamável
    diretamente com floats crus.
    """

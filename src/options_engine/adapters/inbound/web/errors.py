"""Mapeamento de exceções de domínio para respostas HTTP estruturadas.

``DomainError`` nunca vira 500 opaco: toda falha de regra de negócio sai como
``{"erro": <nome da classe>, "mensagem": <texto>}`` com um status previsível.
O handler do Starlette resolve pela hierarquia (MRO), então a entrada mais
específica vence — ``UnknownSymbolError`` (404) antes de ``DomainError`` (422).
As tasks seguintes acrescentam entradas aqui para os erros dos seus routers.
"""

from options_engine.domain.model.errors import DomainError, UnknownSymbolError

__all__ = ["ERROR_STATUS", "error_body"]

ERROR_STATUS: dict[type[Exception], int] = {
    DomainError: 422,
    UnknownSymbolError: 404,
}


def error_body(exc: Exception) -> dict[str, object]:
    """Corpo JSON do erro: nome da classe (estável para o frontend) e a mensagem."""
    return {"erro": type(exc).__name__, "mensagem": str(exc)}

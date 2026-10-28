"""Mapeamento de exceções de domínio para respostas HTTP estruturadas.

``DomainError`` nunca vira 500 opaco: toda falha de regra de negócio sai como
``{"erro": <nome da classe>, "mensagem": <texto>}`` com um status previsível.
O handler do Starlette resolve pela hierarquia (MRO), então a entrada mais
específica vence — ``UnknownSymbolError`` (404) antes de ``DomainError`` (422).
As tasks seguintes acrescentam entradas aqui para os erros dos seus routers.

O frontend trata um formato só: validação de requisição e erros HTTP do
Starlette (rota inexistente, método errado) saem no mesmo molde
``{"erro", "mensagem"}``, com a mensagem em português.
"""

from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError

from options_engine.adapters.outbound.b3files.library import B3FileRejectedError
from options_engine.domain.model.errors import (
    DomainError,
    DuplicateProfileError,
    NoActiveProfileError,
    ProfileLockedError,
    UnknownProfileError,
    UnknownSymbolError,
)

__all__ = ["ERROR_STATUS", "error_body", "http_error_body", "validation_error_body"]

ERROR_STATUS: dict[type[Exception], int] = {
    DomainError: 422,
    UnknownSymbolError: 404,
    DuplicateProfileError: 409,
    ProfileLockedError: 409,
    NoActiveProfileError: 404,
    UnknownProfileError: 404,
    B3FileRejectedError: 422,
}


def error_body(exc: Exception) -> dict[str, object]:
    """Corpo JSON do erro: nome da classe (estável para o frontend) e a mensagem.

    ``ProfileLockedError`` leva também a ``trava`` (PC e instante em ISO 8601
    com fuso) para o frontend pedir a confirmação citando os dois.
    """
    corpo: dict[str, object] = {"erro": type(exc).__name__, "mensagem": str(exc)}
    if isinstance(exc, ProfileLockedError):
        corpo["trava"] = {"pc": exc.machine, "desde": exc.since.isoformat()}
    return corpo


_MENSAGEM_HTTP = {
    404: ("NaoEncontrado", "Recurso não encontrado."),
    405: ("MetodoNaoPermitido", "Método não permitido neste endereço."),
}


def http_error_body(status: int) -> dict[str, object]:
    """Corpo de um erro HTTP do Starlette: 404 e 405 têm nome próprio, o resto é ``ErroHttp``."""
    erro, mensagem = _MENSAGEM_HTTP.get(status, ("ErroHttp", f"Erro HTTP {status}."))
    return {"erro": erro, "mensagem": mensagem}


# Partes da requisição que o pydantic põe no início de ``loc``: não são nome de campo.
_ORIGENS = frozenset({"body", "query", "path", "header", "cookie"})

_COMPLEMENTO_POR_TIPO = {
    "missing": "obrigatório",
    "string_type": "deve ser texto",
    "int_type": "deve ser um número",
    "int_parsing": "deve ser um número",
    "int_from_float": "deve ser um número inteiro",
    "float_type": "deve ser um número",
    "float_parsing": "deve ser um número",
    "bool_type": "deve ser verdadeiro ou falso",
    "bool_parsing": "deve ser verdadeiro ou falso",
    "list_type": "deve ser uma lista",
}


def _nome_do_campo(loc: tuple[str | int, ...]) -> str:
    """``("body", "ativos", 1)`` → ``ativos[1]``; vazio quando o erro é do corpo inteiro."""
    nome = ""
    for parte in loc[1:] if loc and loc[0] in _ORIGENS else loc:
        if isinstance(parte, int):
            nome += f"[{parte}]"
        else:
            nome += f".{parte}" if nome else parte
    return nome


def _resumo_do_erro(erro: dict[str, object]) -> str:
    tipo = erro["type"]
    loc = erro["loc"]
    campo = _nome_do_campo(loc) if isinstance(loc, tuple) else ""
    if tipo == "json_invalid":
        return "corpo da requisição não é um JSON válido"
    if campo:
        return f"campo '{campo}' {_COMPLEMENTO_POR_TIPO.get(str(tipo), 'inválido')}"
    if tipo == "missing":
        return "corpo da requisição obrigatório"
    if tipo in {"model_attributes_type", "dict_type"}:
        return "corpo da requisição deve ser um objeto JSON"
    return "corpo da requisição inválido"


def validation_error_body(exc: RequestValidationError) -> dict[str, object]:
    """Corpo do 422 de validação: resumo em português e os ``detalhes`` do pydantic.

    ``jsonable_encoder`` porque o ``ctx`` do pydantic pode carregar a exceção
    de um validador, que o ``json`` padrão não serializa.
    """
    erros: list[dict[str, object]] = [dict(erro) for erro in exc.errors()]
    # `dict.fromkeys`: o mesmo campo reprovado por mais de uma regra aparece uma vez.
    resumos = dict.fromkeys(_resumo_do_erro(erro) for erro in erros)
    return {
        "erro": "RequisicaoInvalida",
        "mensagem": "; ".join(resumos),
        "detalhes": jsonable_encoder(erros),
    }

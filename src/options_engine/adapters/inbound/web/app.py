"""Fábrica do app FastAPI — saúde, routers injetados, erros de domínio e SPA.

Os endpoints de cálculo dos routers são ``def`` síncronos de propósito: o
Starlette os roda no threadpool, e o motor (CPU-bound) não trava o loop de
eventos (ROADMAP S4). O app escuta só localmente — quem o sobe é o ponto de
entrada, não esta fábrica.
"""

import importlib.metadata
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from pathlib import Path

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from options_engine.adapters.inbound.web.errors import (
    ERROR_STATUS,
    error_body,
    http_error_body,
    validation_error_body,
)

__all__ = ["create_app"]


def _handler_de_erro(status: int) -> Callable[[Request, Exception], Response]:
    def handler(_requisicao: Request, exc: Exception) -> Response:
        return JSONResponse(error_body(exc), status_code=status)

    return handler


def _registrar_spa(app: FastAPI, static_dir: Path) -> None:
    raiz = static_dir.resolve()
    indice = raiz / "index.html"

    @app.get("/{caminho:path}", include_in_schema=False)
    def spa(caminho: str) -> FileResponse:
        # Rota desconhecida da API é 404 de verdade, nunca o HTML do frontend.
        if caminho == "api" or caminho.startswith("api/"):
            raise HTTPException(status_code=404)
        # ``resolve`` + ``is_relative_to``: ``..`` no caminho não escapa de static_dir.
        try:
            arquivo = (raiz / caminho).resolve()
            existe = arquivo.is_relative_to(raiz) and arquivo.is_file()
        except ValueError:  # caminho inválido para o SO (ex.: byte nulo): rota da SPA
            existe = False
        if existe:
            return FileResponse(arquivo)
        if not indice.is_file():
            raise HTTPException(status_code=404)
        return FileResponse(indice)


Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_app(
    routers: Sequence[APIRouter],
    static_dir: Path | None = None,
    *,
    lifespan: Lifespan | None = None,
) -> FastAPI:
    """Monta o app: ``GET /api/saude``, os ``routers`` e, com ``static_dir``, o frontend (SPA).

    ``lifespan`` é o que sobe e desce junto com o servidor (a ponte do Tryd, a trava do
    perfil); quem compõe o app decide o que entra nele.
    """
    versao = importlib.metadata.version("options-engine")
    # Documentação sob /api: fora dela, /docs e afins sombreariam rotas do frontend.
    app = FastAPI(
        title="Painel de Opções",
        version=versao,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    for tipo, status in ERROR_STATUS.items():
        app.add_exception_handler(tipo, _handler_de_erro(status))

    # Mesmo molde ``{"erro", "mensagem"}`` dos erros de domínio: o frontend trata um formato só.
    @app.exception_handler(RequestValidationError)
    def requisicao_invalida(_requisicao: Request, exc: RequestValidationError) -> Response:
        return JSONResponse(validation_error_body(exc), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    def erro_http(_requisicao: Request, exc: StarletteHTTPException) -> Response:
        # Os cabeçalhos do erro (ex.: ``Allow`` do 405) seguem na resposta.
        return JSONResponse(
            http_error_body(exc.status_code), status_code=exc.status_code, headers=exc.headers
        )

    @app.get("/api/saude")
    def saude() -> dict[str, str]:
        return {"status": "ok", "versao": versao}

    for router in routers:
        app.include_router(router)

    # Por último: o curinga da SPA não pode sombrear as rotas acima.
    if static_dir is not None:
        _registrar_spa(app, static_dir)
    return app

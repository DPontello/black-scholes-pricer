"""Router da atualização automática: a versão nova, o início da atualização e o andamento."""

from typing import Protocol

from fastapi import APIRouter
from pydantic import BaseModel

from options_engine.adapters.outbound.atualizacao import EstadoAtualizacao, Fase, VersaoNova

__all__ = ["AtualizadorDoApp", "router_versao"]


class AtualizadorDoApp(Protocol):
    @property
    def atual(self) -> str: ...

    def conferir(self) -> VersaoNova | None: ...

    def iniciar(self) -> EstadoAtualizacao: ...

    def estado(self) -> EstadoAtualizacao: ...


class VersaoNovaOut(BaseModel):
    """O que a tela mostra da versão nova; a URL e o SHA-256 do instalador não saem do servidor."""

    versao: str
    novidades: list[str]
    tamanho: int


class InfoVersaoOut(BaseModel):
    """``nova`` = ``null``: sem versão nova (ou sem conferência, como fora do app instalado)."""

    atual: str
    nova: VersaoNovaOut | None


class EstadoAtualizacaoOut(BaseModel):
    fase: Fase
    baixado: int
    total: int
    mensagem: str


def _estado_out(estado: EstadoAtualizacao) -> EstadoAtualizacaoOut:
    return EstadoAtualizacaoOut(
        fase=estado.fase, baixado=estado.baixado, total=estado.total, mensagem=estado.mensagem
    )


def router_versao(atualizador: AtualizadorDoApp) -> APIRouter:
    router = APIRouter(prefix="/api/versao", tags=["versao"])

    @router.get("")
    def versao() -> InfoVersaoOut:
        nova = atualizador.conferir()
        return InfoVersaoOut(
            atual=atualizador.atual,
            nova=None
            if nova is None
            else VersaoNovaOut(
                versao=nova.versao, novidades=list(nova.novidades), tamanho=nova.tamanho
            ),
        )

    @router.post("/atualizar")
    def atualizar() -> EstadoAtualizacaoOut:
        return _estado_out(atualizador.iniciar())

    @router.get("/atualizar")
    def andamento() -> EstadoAtualizacaoOut:
        return _estado_out(atualizador.estado())

    return router

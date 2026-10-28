"""Router de perfis — abrir, criar e editar a watchlist do perfil deste PC.

Os DTOs pydantic moram só aqui: o domínio devolve ``Profile``/``ProfileEntry``
e este módulo os traduz para o JSON em português da API. Erros de regra
(trava, pasta indisponível, duplicado) sobem como ``DomainError`` e viram
resposta em ``errors.py``. Os endpoints são ``def`` síncronos: tocam arquivos,
e o Starlette os roda no threadpool.
"""

from fastapi import APIRouter, Response
from pydantic import BaseModel

from options_engine.application.ports.inbound import ProfileUseCase
from options_engine.domain.model.profile import Profile, ProfileEntry

__all__ = ["router_perfis"]


class EntradaPerfilOut(BaseModel):
    nome: str
    pasta: str


class PerfilOut(BaseModel):
    nome: str
    ativos: list[str]
    cdi_anual: float


class NovoPerfilIn(BaseModel):
    nome: str
    pasta: str


class AbrirPerfilIn(BaseModel):
    forcar: bool = False


class AtivosIn(BaseModel):
    ativos: list[str]


def _entrada_out(entrada: ProfileEntry) -> EntradaPerfilOut:
    return EntradaPerfilOut(nome=entrada.name, pasta=entrada.folder)


def _perfil_out(perfil: Profile) -> PerfilOut:
    return PerfilOut(nome=perfil.name, ativos=list(perfil.watchlist), cdi_anual=perfil.cdi_annual)


def router_perfis(service: ProfileUseCase) -> APIRouter:
    """Rotas ``/api/perfis`` (cadastro deste PC) e ``/api/perfil`` (o perfil aberto)."""
    router = APIRouter(prefix="/api", tags=["perfis"])

    @router.get("/perfis")
    def listar() -> list[EntradaPerfilOut]:
        return [_entrada_out(entrada) for entrada in service.list()]

    @router.post("/perfis", status_code=201)
    def criar(corpo: NovoPerfilIn) -> PerfilOut:
        return _perfil_out(service.create(corpo.nome, corpo.pasta))

    # ``:path``: o nome do perfil é livre (pode ter "/"), e o cliente o manda
    # codificado; o Starlette decodifica antes de casar a rota.
    @router.post("/perfis/{nome:path}/abrir")
    def abrir(nome: str, corpo: AbrirPerfilIn) -> PerfilOut:
        return _perfil_out(service.open(nome, force=corpo.forcar))

    @router.get("/perfil")
    def ativo() -> PerfilOut:
        return _perfil_out(service.active())

    @router.put("/perfil/ativos")
    def definir_ativos(corpo: AtivosIn) -> PerfilOut:
        return _perfil_out(service.set_watchlist(corpo.ativos))

    @router.post("/perfil/fechar", status_code=204)
    def fechar() -> Response:
        service.close()
        return Response(status_code=204)

    return router

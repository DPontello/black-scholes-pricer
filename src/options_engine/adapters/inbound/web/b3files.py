"""Router dos arquivos da B3 — upload do COTAHIST e do cadastro, e a lista do que há na biblioteca.

O upload manda o arquivo como corpo binário cru e o nome em ``?nome=`` (sem
``python-multipart``). O corpo é lido por uma dependência assíncrona, e não
pelo tipo do parâmetro, para o endpoint seguir ``def`` síncrono (threadpool:
a validação lê o arquivo inteiro) e para o upload funcionar com qualquer
``Content-Type`` — o navegador manda o que o sistema sabe do arquivo, ou nada.
Arquivo recusado sobe como ``B3FileRejectedError`` e vira 422 em ``errors.py``.
"""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from options_engine.adapters.outbound.b3files.downloads import DownloadsImporter
from options_engine.adapters.outbound.b3files.library import B3FileLibrary, ImportedFile

__all__ = ["router_arquivos_b3"]


class ArquivoB3Out(BaseModel):
    tipo: str
    nome: str
    data: date | None


class ArquivoB3ListadoOut(ArquivoB3Out):
    importado_em: datetime


class EventoAutomaticoOut(BaseModel):
    nome: str
    quando: datetime
    importado: bool
    detalhe: str


class ImportacaoAutomaticaOut(BaseModel):
    pasta: str | None
    eventos: list[EventoAutomaticoOut]


async def _corpo_cru(requisicao: Request) -> bytes:
    return await requisicao.body()


def _arquivo_out(arquivo: ImportedFile) -> ArquivoB3Out:
    return ArquivoB3Out(tipo=arquivo.kind.value, nome=arquivo.name, data=arquivo.reference_date)


def _listado_out(arquivo: ImportedFile) -> ArquivoB3ListadoOut:
    return ArquivoB3ListadoOut(
        tipo=arquivo.kind.value,
        nome=arquivo.name,
        data=arquivo.reference_date,
        importado_em=arquivo.imported_at,
    )


def router_arquivos_b3(
    library: B3FileLibrary, importer: DownloadsImporter | None = None
) -> APIRouter:
    """Rotas ``/api/mercado/arquivos``: importar (POST) e listar (GET)."""
    router = APIRouter(prefix="/api/mercado", tags=["mercado"])

    @router.post("/arquivos", status_code=201)
    def importar(nome: str, corpo: Annotated[bytes, Depends(_corpo_cru)]) -> ArquivoB3Out:
        return _arquivo_out(library.import_file(nome, corpo))

    @router.get("/arquivos")
    def listar() -> list[ArquivoB3ListadoOut]:
        return [_listado_out(arquivo) for arquivo in library.files()]

    @router.get("/arquivos/automatico")
    def automatico() -> ImportacaoAutomaticaOut:
        if importer is None:
            return ImportacaoAutomaticaOut(pasta=None, eventos=[])
        eventos = [
            EventoAutomaticoOut(
                nome=e.nome, quando=e.quando, importado=e.importado, detalhe=e.detalhe
            )
            for e in importer.eventos()
        ]
        return ImportacaoAutomaticaOut(pasta=str(importer.folder), eventos=eventos)

    return router

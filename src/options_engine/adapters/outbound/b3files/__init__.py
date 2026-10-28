"""Biblioteca local dos arquivos da B3 (COTAHIST e Cadastro de Instrumentos).

A B3 proíbe o download automático (ADR-0006): o usuário baixa à mão e arrasta
o arquivo para o app. A biblioteca identifica o tipo pelo CONTEÚDO, valida
com os parsers do adapter COTAHIST e só então guarda; arquivo errado é
recusado com o motivo e nada fica gravado.
"""

from options_engine.adapters.outbound.b3files.library import (
    B3FileKind,
    B3FileLibrary,
    B3FileRejectedError,
    CadastroFreshness,
    ImportedFile,
    cadastro_freshness,
)

__all__ = [
    "B3FileKind",
    "B3FileLibrary",
    "B3FileRejectedError",
    "CadastroFreshness",
    "ImportedFile",
    "cadastro_freshness",
]

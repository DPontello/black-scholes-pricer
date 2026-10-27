"""Erros de ARQUIVO do adapter COTAHIST — fora do catálogo de domínio de propósito.

Arquivo malformado é problema de I/O do usuário (download manual, ADR-0006),
não regra de negócio: as exceções nascem e morrem na borda. São levantadas
na CARGA (construtor do adapter), nunca pelo port — uma consulta ao
``OptionChainPort`` só conhece erros de domínio. A CLI as captura e reporta
sem traceback.
"""

from pathlib import Path

__all__ = ["CotahistFormatError", "InstrumentsFileError", "SourceFileError"]


class SourceFileError(Exception):
    """Raiz dos erros de arquivo de fonte (COTAHIST e cadastro de instrumentos)."""

    def __init__(self, path: Path, line: int | None, message: str) -> None:
        self.path = path
        self.line = line
        where = f"{path}" if line is None else f"{path}, linha {line}"
        super().__init__(f"{where}: {message}")


class CotahistFormatError(SourceFileError):
    """COTAHIST fora do layout: tamanho de linha, campo numérico, header ou trailer."""


class InstrumentsFileError(SourceFileError):
    """Cadastro de instrumentos ilegível ou sem as colunas obrigatórias."""

"""Armazenamento em arquivos JSON — perfis do usuário e escrita atômica.

Só stdlib (``json``, ``os``, ``pathlib``): ``json_files`` grava sem deixar
arquivo pela metade e ``profiles`` implementa o port ``ProfileRepository``.
"""

from options_engine.adapters.outbound.storage.json_files import write_json_atomic
from options_engine.adapters.outbound.storage.profiles import JsonProfileRepository

__all__ = ["JsonProfileRepository", "write_json_atomic"]

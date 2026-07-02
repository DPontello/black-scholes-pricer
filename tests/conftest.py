"""Configuração global de testes — perfis Hypothesis (VV-PLAN §determinismo).

- ``dev``     (default): 100 exemplos, rápido no ciclo local.
- ``ci``      : 500 exemplos, ``derandomize=True`` — PR nunca flaka por sorteio.
- ``nightly`` : 10.000 exemplos aleatórios; toda falha é promovida
                permanentemente a ``@example(...)`` no teste (corpus versionado).

Seleção via variável de ambiente ``HYPOTHESIS_PROFILE``.
"""

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=500, derandomize=True)
settings.register_profile("nightly", max_examples=10_000, print_blob=True)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))

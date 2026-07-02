"""Perfis Hypothesis dos testes de kernel (VV-PLAN §determinismo).

- ``dev``     (default): 100 exemplos, rápido no ciclo local.
- ``ci``      : 500 exemplos, ``derandomize=True`` — PR nunca flaka por sorteio.
- ``nightly`` : 10.000 exemplos aleatórios; toda falha é promovida
                permanentemente a ``@example(...)`` no teste (corpus versionado).

Seleção via variável de ambiente ``HYPOTHESIS_PROFILE``.

Vive em ``tests/kernel/`` (não em ``tests/``) de propósito: o ambiente do
job de oráculo (``tests/oracle/``) não instala hypothesis, e um conftest na
raiz de ``tests/`` quebraria a coleta daquele job. Quando outra suíte
passar a usar Hypothesis (domínio, Sprint 2), extrair os perfis para um
módulo compartilhado importado pelos conftests locais.
"""

import os

from hypothesis import settings

settings.register_profile("dev", max_examples=100)
settings.register_profile("ci", max_examples=500, derandomize=True)
settings.register_profile("nightly", max_examples=10_000, print_blob=True)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))

"""Perfis Hypothesis compartilhados entre as suítes (VV-PLAN §determinismo).

- ``dev``     (default): 100 exemplos, rápido no ciclo local.
- ``ci``      : 500 exemplos, ``derandomize=True`` — PR nunca flaka por sorteio.
- ``nightly`` : 10.000 exemplos aleatórios; toda falha é promovida
                permanentemente a ``@example(...)`` no teste (corpus versionado).

Seleção via variável de ambiente ``HYPOTHESIS_PROFILE``.

Cada suíte que usa Hypothesis chama ``load_profiles()`` no seu conftest
local (``tests/kernel/``, ``tests/domain/``, ...). O registro NÃO vive num
conftest na raiz de ``tests/`` de propósito: o ambiente do job de oráculo
(``tests/oracle/``) não instala hypothesis, e um conftest raiz quebraria a
coleta daquele job.
"""

import os

from hypothesis import settings


def load_profiles() -> None:
    """Registra os perfis e carrega o selecionado por ``HYPOTHESIS_PROFILE``.

    Idempotente: re-registrar um perfil com o mesmo nome apenas o sobrescreve
    — conftests de suítes distintas podem chamar sem coordenação.
    """
    settings.register_profile("dev", max_examples=100)
    settings.register_profile("ci", max_examples=500, derandomize=True)
    settings.register_profile("nightly", max_examples=10_000, print_blob=True)
    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "dev"))

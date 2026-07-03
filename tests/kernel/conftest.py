"""Conftest da suíte de kernel — carrega os perfis Hypothesis compartilhados.

Os perfis (dev/ci/nightly) vivem em ``tests/_hypothesis_profiles.py``,
compartilhados com as demais suítes que usam Hypothesis. Ver o docstring
daquele módulo para o porquê de não haver conftest na raiz de ``tests/``.
"""

from tests._hypothesis_profiles import load_profiles

load_profiles()

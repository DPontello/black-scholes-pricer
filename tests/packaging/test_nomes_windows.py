"""Nomes de arquivo que o Windows confunde.

O Windows não diferencia maiúsculas: com ``Termos.tsx`` e ``termos.ts`` na mesma pasta, o import
``./Termos`` (sem extensão) achou o ``.ts`` e o build da tela quebrou no job do instalador.
"""

from collections import defaultdict
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "src"


def test_nenhum_modulo_da_tela_difere_de_outro_so_por_maiusculas() -> None:
    por_nome: dict[tuple[Path, str], list[str]] = defaultdict(list)
    for arquivo in FRONTEND.rglob("*"):
        if arquivo.suffix in {".ts", ".tsx"}:
            nome = arquivo.name.removesuffix(".tsx").removesuffix(".ts")
            nome = nome.removesuffix(".test")
            por_nome[(arquivo.parent, nome.lower())].append(arquivo.name)
    colisoes = {
        str(pasta / nome): nomes
        for (pasta, nome), nomes in por_nome.items()
        if len({n.removesuffix(".tsx").removesuffix(".ts").removesuffix(".test") for n in nomes})
        > 1
    }
    assert not colisoes

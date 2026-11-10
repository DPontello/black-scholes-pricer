"""Cores do tema.css: contraste mínimo do texto colorido e o papel de cada tom."""

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TEMA = RAIZ / "frontend" / "src" / "tema.css"


def _variaveis() -> dict[str, str]:
    """As `--nome: #rrggbb;` do primeiro bloco `:root`."""
    bloco = re.search(r":root \{([^}]*)\}", TEMA.read_text(encoding="utf-8"))
    assert bloco is not None
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6});", bloco.group(1)))


def _luminancia(cor: str) -> float:
    canais = [int(cor[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canais)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contraste(a: str, b: str) -> float:
    """Razão de contraste do WCAG 2.x."""
    claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (escuro + 0.05)


@pytest.mark.parametrize("fundo", ["fundo", "painel"])
@pytest.mark.parametrize("cor", ["compra", "venda", "alta", "baixa", "destaque"])
def test_cores_de_texto_tem_contraste_minimo(cor: str, fundo: str) -> None:
    v = _variaveis()
    assert _contraste(v[cor], v[fundo]) >= 4.5


def test_tons_suaves_do_rascunho() -> None:
    v = _variaveis()
    assert (v["destaque"], v["compra"], v["venda"], v["alta"], v["baixa"]) == (
        "#1e88e5",
        "#7fb3e6",
        "#e09a98",
        "#5fbfb4",
        "#e5807e",
    )


def test_compra_so_pinta_o_preco_de_compra() -> None:
    # Links, menu, abas, foco e a faixa da rolagem usam --destaque.
    assert TEMA.read_text(encoding="utf-8").count("var(--compra)") == 1


def test_botao_principal_tem_texto_escuro_sobre_o_destaque() -> None:
    bloco = re.search(r"\.botao-principal \{([^}]*)\}", TEMA.read_text(encoding="utf-8"))
    assert bloco is not None
    assert "background: var(--destaque)" in bloco.group(1)
    assert "color: var(--fundo)" in bloco.group(1)

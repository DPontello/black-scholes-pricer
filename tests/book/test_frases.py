"""Frase curta de cada estrutura do catálogo: por que ela serve, sem repetir os números."""

import pytest

from options_engine.domain.book.frases import short_reason
from options_engine.domain.model.templates import TEMPLATES


@pytest.mark.parametrize("chave", [modelo.key for modelo in TEMPLATES])
def test_toda_estrutura_do_catalogo_tem_frase_curta(chave: str) -> None:
    frase = short_reason(chave)

    assert frase
    assert frase.endswith(".")
    assert not any(c.isdigit() for c in frase)


def test_frase_da_venda_coberta() -> None:
    assert short_reason("venda_coberta") == (
        "Renda com as suas ações: recebe o prêmio e aceita vender no strike."
    )


def test_frase_da_compra_de_call_diz_so_o_cenario_e_o_risco() -> None:
    assert short_reason("compra_call") == "Aposta na alta: a perda máxima é o que pagou."


@pytest.mark.parametrize("chave", [modelo.key for modelo in TEMPLATES])
def test_frase_curta_nao_afirma_nada_sobre_a_vol(chave: str) -> None:
    assert "vol" not in short_reason(chave).lower()


def test_chave_desconhecida_e_erro() -> None:
    with pytest.raises(KeyError):
        short_reason("x")

"""Frase curta de cada estrutura do book: por que ela serve, em linguagem simples.

Sem número: o cartão já mostra os números. A chave é a de ``TEMPLATES``.
"""

from typing import Final

__all__ = ["short_reason"]

_FRASES: Final = {
    "venda_coberta": "Renda com as suas ações: recebe o prêmio e aceita vender no strike.",
    "put_coberta": "Renda com caixa: recebe o prêmio e aceita comprar a ação no strike.",
    "trava_alta_put": "Renda com risco limitado: dá certo se a ação não cair.",
    "trava_baixa_call": "Renda com risco limitado: dá certo se a ação não subir.",
    "compra_call": "Aposta na alta: a perda máxima é o que pagou.",
    "compra_put": "Aposta na queda: a perda máxima é o que pagou.",
    "trava_alta_call": "Aposta na alta com perda limitada.",
    "trava_baixa_put": "Aposta na queda com perda limitada.",
    "straddle_comprado": (
        "Ganha se a ação andar muito para qualquer lado; a perda máxima é o que pagou."
    ),
    "straddle_vendido": "Ganha se a ação ficar parada; a perda não tem limite.",
    "strangle_comprado": (
        "Ganha se a ação sair da faixa para qualquer lado; a perda máxima é o que pagou."
    ),
    "strangle_vendido": "Ganha se a ação ficar na faixa; a perda não tem limite.",
    "iron_condor_vendido": "Ganha se a ação ficar na faixa, com perda limitada.",
    "iron_condor_comprado": "Ganha se a ação sair da faixa, com perda limitada.",
    "borboleta_comprada": "Ganha se a ação parar perto do strike do meio, com perda limitada.",
    "borboleta_vendida": "Ganha se a ação se afastar do strike do meio, com perda limitada.",
    "put_protetora": "Seguro para as suas ações até o vencimento.",
    "collar": "Seguro barato: protege a queda e abre mão de parte da alta.",
}


def short_reason(template_key: str) -> str:
    """A frase da estrutura; ``KeyError`` para uma chave fora do catálogo."""
    return _FRASES[template_key]

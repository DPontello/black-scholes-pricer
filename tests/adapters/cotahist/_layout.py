"""Montagem de registros COTAHIST em largura fixa — para testes e para o gerador da fixture.

Espelha o layout que ``options_engine.adapters.outbound.cotahist.parser`` lê
(posições 1-based, 245 caracteres). Preços entram em reais por unidade e
saem multiplicados por FATCOT, como a B3 os grava.
"""

from collections.abc import Sequence
from datetime import date

__all__ = ["CRLF", "arquivo", "header", "registro", "trailer"]

CRLF = "\r\n"
_TAMANHO = 245
_SEM_VENCIMENTO = date(9999, 12, 31)


def _numero(valor: int, largura: int) -> str:
    texto = f"{valor:0{largura}d}"
    if len(texto) != largura or valor < 0:
        raise ValueError(f"{valor!r} não cabe em N({largura})")
    return texto


def _texto(valor: str, largura: int) -> str:
    if len(valor) > largura:
        raise ValueError(f"{valor!r} não cabe em X({largura})")
    return valor.ljust(largura)


def _preco(valor: float, fator: int) -> str:
    return _numero(round(valor * fator * 100), 13)


def _data(valor: date) -> str:
    return valor.strftime("%Y%m%d")


def header(geracao: date, ano: int) -> str:
    return ("00" + f"COTAHIST.{ano}" + "BOVESPA " + _data(geracao)).ljust(_TAMANHO)


def trailer(geracao: date, ano: int, total_de_registros: int) -> str:
    linha = "99" + f"COTAHIST.{ano}" + "BOVESPA " + _data(geracao)
    return (linha + _numero(total_de_registros, 11)).ljust(_TAMANHO)


def registro(
    *,
    pregao: date,
    simbolo: str,
    mercado: int,
    nome: str = "",
    especificacao: str = "",
    ultimo: float = 0.0,
    oferta_compra: float = 0.0,
    oferta_venda: float = 0.0,
    negocios: int = 0,
    quantidade: int = 0,
    volume: float = 0.0,
    strike: float = 0.0,
    indopc: int = 0,
    vencimento: date = _SEM_VENCIMENTO,
    fator: int = 1,
    codbdi: str = "02",
) -> str:
    """Um registro ``01`` com os campos que o parser lê; o resto em branco ou zero."""
    partes = [
        "01",
        _data(pregao),
        _texto(codbdi, 2),
        _texto(simbolo, 12),
        _numero(mercado, 3),
        _texto(nome, 12),
        _texto(especificacao, 10),
        " " * 3,  # PRAZOT
        "R$  ",  # MODREF
        _preco(ultimo, fator) * 4,  # PREABE, PREMAX, PREMIN, PREMED
        _preco(ultimo, fator),
        _preco(oferta_compra, fator),
        _preco(oferta_venda, fator),
        _numero(negocios, 5),
        _numero(quantidade, 18),
        _numero(round(volume * 100), 18),
        _preco(strike, fator),
        _numero(indopc, 1),
        _data(vencimento),
        _numero(fator, 7),
        _numero(0, 13),  # PTOEXE
        " " * 12,  # CODISI
        _numero(0, 3),  # DISMES
    ]
    linha = "".join(partes)
    if len(linha) != _TAMANHO:
        raise AssertionError(f"registro montado com {len(linha)} caracteres")
    return linha


def arquivo(registros: Sequence[str], *, geracao: date, ano: int, fim_de_linha: str = CRLF) -> str:
    """Header + registros + trailer com o total correto (header e trailer inclusos)."""
    linhas = [header(geracao, ano), *registros, trailer(geracao, ano, len(registros) + 2)]
    return fim_de_linha.join(linhas) + fim_de_linha

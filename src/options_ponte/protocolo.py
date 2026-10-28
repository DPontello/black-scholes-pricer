"""Protocolo da ponte — JSON por linha (UTF-8, ``\\n`` no fim) sobre TCP local.

Só stdlib: o app importa este módulo para falar com a ponte. A ponte NÃO interpreta
o valor que o Tryd entrega (zeros iniciais do RTD, texto de hora, etc.): repassa com o
tipo de origem em ``tipo_valor`` e a tradução para o domínio fica no app.
"""

import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass

__all__ = [
    "CAMPOS_ATIVO",
    "CAMPOS_OPCAO",
    "CLSID",
    "LIMITE_TOPICOS",
    "PORTA_PONTE",
    "PROGID",
    "TRYD_CONECTADO",
    "TRYD_INICIANDO",
    "TRYD_PERDIDO",
    "Assinar",
    "Cancelar",
    "Encerrar",
    "ErroDeProtocolo",
    "Mensagem",
    "Ping",
    "Pong",
    "Status",
    "Valor",
    "classificar_valor",
    "codificar",
    "decodificar",
    "topico_rtd",
]

PROGID = "RTDTrading.RtdServer"
CLSID = "{272D2E65-05FB-4500-BD7B-5905D5B0A1B8}"

# Padrões compartilhados pela ponte (CLI) e pelo app (settings do adapter do Tryd).
PORTA_PONTE = 8766
LIMITE_TOPICOS = 600
CAMPOS_ATIVO = ("ULT", "OCP", "OVD", "NEG", "VOL", "FEC", "HOR", "DAT")
CAMPOS_OPCAO = ("ULT", "OCP", "OVD", "NEG", "VOL", "HOR", "DAT")

TRYD_INICIANDO = "iniciando"
TRYD_CONECTADO = "conectado"
TRYD_PERDIDO = "perdido"
_ESTADOS_TRYD = (TRYD_INICIANDO, TRYD_CONECTADO, TRYD_PERDIDO)


class ErroDeProtocolo(ValueError):
    """Linha que não é JSON, tipo de mensagem desconhecido ou campo ausente/malformado."""


def topico_rtd(ticker: str, campo: str) -> tuple[str, str]:
    """As duas strings do ``ConnectData`` do Tryd: ``("PETRK500_B_0", "ULT")``."""
    return (f"{ticker}_B_0", campo)


@dataclass(frozen=True, slots=True)
class Valor:
    """Valor de um tópico, como veio do RTD. ``tipo_valor``: float, int, str, none ou outro.

    ``inicial``: é o valor que o ``ConnectData`` devolveu ao assinar (no RTD, zero até o Tryd
    carregar o tópico), ainda sem nenhuma atualização do servidor. Na linha JSON a chave só
    aparece quando verdadeira; ausente vale falso.
    """

    ticker: str
    campo: str
    tipo_valor: str
    valor: float | int | str | None
    instante: str
    inicial: bool = False


@dataclass(frozen=True, slots=True)
class Status:
    """Estado da ponte diante do Tryd; ``motivo`` explica ``perdido`` (ou uma recusa)."""

    tryd: str
    motivo: str | None
    topicos: int


@dataclass(frozen=True, slots=True)
class Assinar:
    topicos: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Cancelar:
    topicos: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Ping:
    pass


@dataclass(frozen=True, slots=True)
class Pong:
    pass


@dataclass(frozen=True, slots=True)
class Encerrar:
    pass


Mensagem = Valor | Status | Assinar | Cancelar | Ping | Pong | Encerrar

_NOMES: dict[type, str] = {
    Valor: "valor",
    Status: "status",
    Assinar: "assinar",
    Cancelar: "cancelar",
    Ping: "ping",
    Pong: "pong",
    Encerrar: "encerrar",
}


def codificar(msg: Mensagem) -> bytes:
    """Uma linha JSON + ``\\n``. NaN/Infinity saem como o ``json`` do Python os escreve
    (não é JSON estrito, mas os dois lados são Python e ``decodificar`` os lê de volta).
    """
    carga = {"tipo": _NOMES[type(msg)], **asdict(msg)}
    if isinstance(msg, Valor) and not msg.inicial:  # a chave só vai quando verdadeira
        del carga["inicial"]
    return (json.dumps(carga, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decodificar(linha: bytes) -> Mensagem:
    try:
        bruto = json.loads(linha)  # JSONDecodeError e UnicodeDecodeError são ValueError
    except ValueError as erro:
        raise ErroDeProtocolo(f"linha não é JSON válido: {erro}") from erro
    if not isinstance(bruto, dict):
        raise ErroDeProtocolo("a linha deve ser um objeto JSON")
    tipo = bruto.get("tipo")
    montar = _MONTADORES.get(tipo) if isinstance(tipo, str) else None
    if montar is None:
        raise ErroDeProtocolo(f"tipo de mensagem desconhecido: {tipo!r}")
    return montar(bruto)


def classificar_valor(v: object) -> tuple[str, float | int | str | None]:
    """Tipo de origem e valor, para ``Valor``.

    O que não é float/int/str/None, e o texto que não vira UTF-8, vira ``("outro", repr(v))``.
    """
    if v is None:
        return ("none", None)
    if isinstance(v, bool):  # bool é int em Python; aqui não é número do Tryd
        return ("outro", repr(v))
    if isinstance(v, float):
        return ("float", v)
    if isinstance(v, int):
        return ("int", v)
    if isinstance(v, str):
        try:
            v.encode("utf-8")
        except UnicodeEncodeError:  # surrogate solto (BSTR quebrado): a linha não cabe em UTF-8
            return ("outro", repr(v))
        return ("str", v)
    return ("outro", repr(v))


def _texto(bruto: Mapping[str, object], chave: str) -> str:
    valor = bruto.get(chave)
    if not isinstance(valor, str):
        raise ErroDeProtocolo(f"campo {chave!r} deve ser texto")
    return valor


def _inteiro(bruto: Mapping[str, object], chave: str) -> int:
    valor = bruto.get(chave)
    if not isinstance(valor, int) or isinstance(valor, bool):
        raise ErroDeProtocolo(f"campo {chave!r} deve ser inteiro")
    return valor


def _topicos(bruto: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    itens = bruto.get("topicos")
    if not isinstance(itens, list):
        raise ErroDeProtocolo("campo 'topicos' deve ser uma lista")
    pares: list[tuple[str, str]] = []
    for item in itens:
        if not (
            isinstance(item, list)
            and len(item) == 2
            and isinstance(item[0], str)
            and isinstance(item[1], str)
        ):
            raise ErroDeProtocolo(f"tópico deve ser [ticker, campo]; recebido {item!r}")
        pares.append((item[0], item[1]))
    return tuple(pares)


def _montar_valor(bruto: Mapping[str, object]) -> Valor:
    if "valor" not in bruto:
        raise ErroDeProtocolo("campo 'valor' ausente")
    valor = bruto["valor"]
    if isinstance(valor, bool) or not (valor is None or isinstance(valor, float | int | str)):
        raise ErroDeProtocolo(f"campo 'valor' deve ser número, texto ou nulo; recebido {valor!r}")
    inicial = bruto.get("inicial", False)
    if not isinstance(inicial, bool):
        raise ErroDeProtocolo(f"campo 'inicial' deve ser booleano; recebido {inicial!r}")
    return Valor(
        _texto(bruto, "ticker"),
        _texto(bruto, "campo"),
        _texto(bruto, "tipo_valor"),
        valor,
        _texto(bruto, "instante"),
        inicial,
    )


def _montar_status(bruto: Mapping[str, object]) -> Status:
    tryd = _texto(bruto, "tryd")
    if tryd not in _ESTADOS_TRYD:
        raise ErroDeProtocolo(f"campo 'tryd' deve ser um de {_ESTADOS_TRYD}; recebido {tryd!r}")
    motivo = bruto.get("motivo")
    if motivo is not None and not isinstance(motivo, str):
        raise ErroDeProtocolo("campo 'motivo' deve ser texto ou nulo")
    return Status(tryd, motivo, _inteiro(bruto, "topicos"))


_MONTADORES: dict[str, Callable[[Mapping[str, object]], Mensagem]] = {
    "valor": _montar_valor,
    "status": _montar_status,
    "assinar": lambda bruto: Assinar(_topicos(bruto)),
    "cancelar": lambda bruto: Cancelar(_topicos(bruto)),
    "ping": lambda _bruto: Ping(),
    "pong": lambda _bruto: Pong(),
    "encerrar": lambda _bruto: Encerrar(),
}

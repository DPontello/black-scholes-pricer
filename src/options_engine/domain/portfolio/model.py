"""Operação da carteira: pernas e eventos em ordem. Posição, preço médio e resultado saem dos
eventos (``leg_states``); nada é guardado já somado.

Preço médio ponderado por perna (IN RFB 1.585/2015, art. 60, § 2º). Exercício e atribuição fecham
a perna da opção sem resultado próprio: o prêmio vai para o preço da ação (``exercise.py``). Pó
realiza o prêmio inteiro: ganho do lançador, perda do titular (art. 60, § 3º). Transferência tira
ações de uma operação para outra que as usou "da carteira": sai pelo preço médio, sem resultado,
porque quem vende é a operação de destino.
"""

from dataclasses import dataclass, replace
from datetime import date
from math import fsum, isfinite
from typing import Final

from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError

__all__ = [
    "Assignment",
    "Close",
    "Event",
    "Exercise",
    "Expired",
    "LegRef",
    "LegState",
    "Open",
    "Operation",
    "OptionLegRef",
    "StockLegRef",
    "StrikeAdjusted",
    "TransferOut",
    "event_refs",
    "leg_states",
]

# Strikes saem do arquivo como foram gravados; a folga só cobre o último bit de uma conta.
_MESMO_STRIKE: Final = 1e-9


@dataclass(frozen=True, slots=True)
class OptionLegRef:
    symbol: str
    terms: OptionTerms


@dataclass(frozen=True, slots=True)
class StockLegRef:
    """``CARTEIRA``: a ação já está no perfil; esta operação só a usa (não a compra)."""

    symbol: str
    origin: StockOrigin


LegRef = OptionLegRef | StockLegRef


@dataclass(frozen=True, slots=True)
class Open:
    leg: int
    on: date
    side: Side
    quantity: int
    price: float
    costs: float | None = None


@dataclass(frozen=True, slots=True)
class Close:
    """``cost_basis``: só na ação da carteira, o preço médio dela no momento da venda."""

    leg: int
    on: date
    quantity: int
    price: float
    costs: float | None = None
    cost_basis: float | None = None


@dataclass(frozen=True, slots=True)
class Exercise:
    leg: int
    on: date
    quantity: int
    costs: float | None = None


@dataclass(frozen=True, slots=True)
class Assignment:
    leg: int
    on: date
    quantity: int
    costs: float | None = None


@dataclass(frozen=True, slots=True)
class Expired:
    leg: int
    on: date


@dataclass(frozen=True, slots=True)
class TransferOut:
    """``to_operation``: o id da operação que vendeu estas ações "da carteira"."""

    leg: int
    on: date
    quantity: int
    to_operation: str


@dataclass(frozen=True, slots=True)
class StrikeAdjusted:
    """Strike da série ajustado pela B3 (provento em dinheiro): ``previous`` é o strike em vigor
    antes do ajuste e ``source``, de onde veio o novo (o Cadastro da B3 e a data dele). A perna
    gravada não muda; o strike em vigor sai de ``leg_states``."""

    leg: int
    on: date
    previous: float
    strike: float
    source: str


Event = Open | Close | Exercise | Assignment | Expired | TransferOut | StrikeAdjusted


@dataclass(frozen=True, slots=True)
class LegState:
    """``realized`` é bruto, em moeda, sem custos; ``side`` é ``None`` sem posição aberta."""

    index: int
    ref: LegRef
    side: Side | None
    quantity: int
    average_price: float
    realized: float


@dataclass(frozen=True, slots=True)
class Operation:
    """``template``: a chave do modelo do Montador de onde veio (para a rolagem).
    ``stop_loss`` e ``target``: em R$, positivos, comparados com o resultado total."""

    id: str
    underlying: str
    name: str
    created_on: date
    legs: tuple[LegRef, ...]
    events: tuple[Event, ...]
    template: str | None = None
    stop_loss: float | None = None
    target: float | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.name.strip():
            raise InvalidDomainValueError("operação precisa de id e nome")
        for nome, limite in (("stop", self.stop_loss), ("alvo", self.target)):
            if limite is not None and not (isfinite(limite) and limite > 0.0):
                raise InvalidDomainValueError(
                    f"{nome} deve ser um valor em R$ maior que zero; recebido {limite!r}"
                )
        if not self.legs:
            raise InvalidDomainValueError(f"operação {self.name!r} sem perna nenhuma")
        for leg in self.legs:
            ativo = leg.terms.underlying if isinstance(leg, OptionLegRef) else leg.symbol
            if ativo != self.underlying:
                raise InvalidDomainValueError(
                    f"perna {leg.symbol!r} é de {ativo!r}, e a operação é de {self.underlying!r}"
                )
        leg_states(self)

    def with_events(self, *events: Event) -> "Operation":
        return replace(self, events=(*self.events, *events))


class _Estado:
    __slots__ = ("lado", "media", "quantidade", "realizado")

    def __init__(self) -> None:
        self.lado: Side | None = None
        self.quantidade = 0
        self.media = 0.0
        self.realizado: list[float] = []


def _exige_quantidade(quantidade: int) -> None:
    if quantidade < 1:
        raise InvalidDomainValueError(f"quantidade deve ser >= 1; recebido {quantidade!r}")


def _exige_preco(preco: float, acao: bool) -> None:
    if not isfinite(preco) or preco < 0.0 or (acao and preco == 0.0):
        raise InvalidDomainValueError(f"preço inválido: {preco!r}")


def _exige_custos(custos: float | None) -> None:
    if custos is not None and not (isfinite(custos) and custos >= 0.0):
        raise InvalidDomainValueError(f"custos devem ser >= 0; recebido {custos!r}")


def _da_carteira(ref: LegRef) -> bool:
    return isinstance(ref, StockLegRef) and ref.origin is StockOrigin.CARTEIRA


def _abrir(estado: _Estado, ref: LegRef, evento: Open) -> None:
    _exige_quantidade(evento.quantity)
    _exige_preco(evento.price, isinstance(ref, StockLegRef))
    _exige_custos(evento.costs)
    if _da_carteira(ref):
        raise InvalidDomainValueError(
            f"a ação da carteira não é comprada na operação: {ref.symbol!r} já está no perfil"
        )
    if estado.quantidade and estado.lado is not evento.side:
        raise InvalidDomainValueError(
            f"abertura no lado oposto ao da posição de {ref.symbol!r}: use o encerramento"
        )
    total = estado.quantidade + evento.quantity
    estado.media = fsum((estado.media * estado.quantidade, evento.price * evento.quantity)) / total
    estado.quantidade = total
    estado.lado = evento.side


def _fechar(estado: _Estado, ref: LegRef, evento: Close) -> None:
    _exige_quantidade(evento.quantity)
    _exige_preco(evento.price, isinstance(ref, StockLegRef))
    _exige_custos(evento.costs)
    if (evento.cost_basis is not None) != _da_carteira(ref):
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: só a ação da carteira sai pelo custo médio dela, e sempre por ele"
        )
    if evento.cost_basis is not None:
        _exige_preco(evento.cost_basis, True)
        estado.realizado.append((evento.price - evento.cost_basis) * evento.quantity)
        return
    if estado.lado is None or evento.quantity > estado.quantidade:
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: encerra {evento.quantity} com {estado.quantidade} em aberto"
        )
    estado.realizado.append(estado.lado.sign * (evento.price - estado.media) * evento.quantity)
    _baixar(estado, evento.quantity)


def _baixar(estado: _Estado, quantidade: int) -> None:
    estado.quantidade -= quantidade
    if estado.quantidade == 0:
        estado.lado, estado.media = None, 0.0


def _exercer(estado: _Estado, ref: LegRef, evento: Exercise | Assignment) -> None:
    _exige_quantidade(evento.quantity)
    _exige_custos(evento.costs)
    exigido, nome = (
        (Side.BUY, "exercício só em perna comprada")
        if isinstance(evento, Exercise)
        else (Side.SELL, "atribuição só em perna vendida")
    )
    if not isinstance(ref, OptionLegRef):
        raise InvalidDomainValueError(f"{nome} de opção; {ref.symbol!r} é ação")
    if estado.lado is not exigido:
        raise InvalidDomainValueError(f"{ref.symbol!r}: {nome}")
    if evento.quantity > estado.quantidade:
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: exerce {evento.quantity} com {estado.quantidade} em aberto"
        )
    _baixar(estado, evento.quantity)


def _virar_po(estado: _Estado, ref: LegRef) -> None:
    if not isinstance(ref, OptionLegRef):
        raise InvalidDomainValueError(f"pó só em perna de opção; {ref.symbol!r} é ação")
    if estado.lado is None:
        raise InvalidDomainValueError(f"{ref.symbol!r}: nada em aberto para virar pó")
    estado.realizado.append(-estado.lado.sign * estado.media * estado.quantidade)
    _baixar(estado, estado.quantidade)


def _transferir(estado: _Estado, ref: LegRef, evento: TransferOut) -> None:
    _exige_quantidade(evento.quantity)
    if not evento.to_operation.strip():
        raise InvalidDomainValueError("transferência precisa da operação de destino")
    if not isinstance(ref, StockLegRef) or _da_carteira(ref) or estado.lado is not Side.BUY:
        raise InvalidDomainValueError(
            f"transferência só sai de ação comprada na operação; {ref.symbol!r} não é"
        )
    if evento.quantity > estado.quantidade:
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: transfere {evento.quantity} com {estado.quantidade} em aberto"
        )
    _baixar(estado, evento.quantity)


def _ajustar(estado: _Estado, ref: LegRef, evento: StrikeAdjusted) -> OptionLegRef:
    if not isinstance(ref, OptionLegRef):
        raise InvalidDomainValueError(
            f"ajuste de strike só em perna de opção; {ref.symbol!r} é ação"
        )
    if estado.lado is None:
        raise InvalidDomainValueError(f"{ref.symbol!r}: ajuste de strike sem nada em aberto")
    if not (isfinite(evento.strike) and evento.strike > 0.0):
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: strike ajustado inválido: {evento.strike!r}"
        )
    # O anterior foi copiado do strike em vigor: diferença é arquivo editado ou fora de ordem.
    if abs(evento.previous - ref.terms.strike) > _MESMO_STRIKE:
        raise InvalidDomainValueError(
            f"{ref.symbol!r}: strike anterior do ajuste ({evento.previous!r}) não é o strike em "
            f"vigor ({ref.terms.strike!r})"
        )
    if not evento.source.strip():
        raise InvalidDomainValueError(f"{ref.symbol!r}: ajuste de strike sem a fonte")
    return OptionLegRef(ref.symbol, replace(ref.terms, strike=evento.strike))


def event_refs(operation: Operation) -> tuple[LegRef, ...]:
    """A perna em vigor quando cada evento aconteceu (com os ajustes de strike de antes dele)."""
    refs = list(operation.legs)
    em_vigor: list[LegRef] = []
    for evento in operation.events:
        if not 0 <= evento.leg < len(refs):
            raise InvalidDomainValueError(f"evento em perna inexistente: {evento.leg}")
        em_vigor.append(refs[evento.leg])
        if isinstance(evento, StrikeAdjusted):
            ref = refs[evento.leg]
            if isinstance(ref, OptionLegRef):
                refs[evento.leg] = OptionLegRef(
                    ref.symbol, replace(ref.terms, strike=evento.strike)
                )
    return tuple(em_vigor)


def leg_states(operation: Operation) -> tuple[LegState, ...]:
    """Posição de cada perna; ``ref`` traz o strike em vigor (com os ajustes da B3)."""
    estados = [_Estado() for _ in operation.legs]
    refs = list(operation.legs)
    for evento in operation.events:
        if not 0 <= evento.leg < len(operation.legs):
            raise InvalidDomainValueError(f"evento em perna inexistente: {evento.leg}")
        estado, ref = estados[evento.leg], refs[evento.leg]
        match evento:
            case Open():
                _abrir(estado, ref, evento)
            case Close():
                _fechar(estado, ref, evento)
            case Exercise() | Assignment():
                _exercer(estado, ref, evento)
            case Expired():
                _virar_po(estado, ref)
            case TransferOut():
                _transferir(estado, ref, evento)
            case StrikeAdjusted():
                refs[evento.leg] = _ajustar(estado, ref, evento)
    return tuple(
        LegState(i, ref, e.lado, e.quantidade, e.media, fsum(e.realizado))
        for i, (ref, e) in enumerate(zip(refs, estados, strict=True))
    )

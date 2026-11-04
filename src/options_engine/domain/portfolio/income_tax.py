"""Peças de resultado das opções por série: a base do IR mensal estimado.

Preço médio por série no perfil, como a Receita e o informe da corretora fazem: as pernas da mesma
série, em operações diferentes, entram juntas (IN RFB 1.585/2015, art. 60, § 2º). Day trade é
compra e venda da mesma série no mesmo dia, pela data dos eventos: a quantidade casada é o menor
entre o comprado e o vendido no dia, pelos preços médios daquele dia; a sobra entra na posição
comum da série, ao preço médio do lado que sobrou, e encerra posição aberta no sentido oposto.
Os custos entram no preço: a compra soma o custo, a venda desconta. Pó realiza o preço médio
inteiro, sem custo próprio e sem day trade (art. 60, § 3º). Exercício e atribuição não geram
resultado de opção, só uma nota: o prêmio vai para o preço da ação (``exercise.py``), fora daqui.
Pó, exercício e atribuição tiram da posição da série só o que existe do lado da perna: outra
operação da mesma série pode já ter casado a diferença.
Pernas de ação ficam de fora. É estimativa, nunca cálculo fiscal.

No mês, o resultado de cada categoria (comum a 15%, day trade a 20%) abate só o prejuízo da própria
categoria, vindo dos meses anteriores; o prejuízo que sobra segue adiante. O IR do mês abaixo de
R$ 10 não se paga: soma com o dos meses seguintes até chegar a R$ 10, e prejuízo de um mês depois
não abate o que já ficou devido. Só aparecem os meses com peça ou nota; prejuízo e IR pendente
atravessam os meses vazios.
"""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import groupby
from math import fsum
from typing import Final

from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.enums import Side
from options_engine.domain.portfolio.model import (
    Assignment,
    Close,
    Exercise,
    Expired,
    Open,
    Operation,
    OptionLegRef,
)
from options_engine.domain.portfolio.positions import event_costs

__all__ = [
    "COMMON_RATE",
    "DARF_MINIMUM",
    "DAY_TRADE_RATE",
    "ExerciseNote",
    "PieceKind",
    "TaxCategory",
    "TaxMonth",
    "TaxPiece",
    "TaxRecords",
    "monthly_tax",
    "tax_records",
]

COMMON_RATE: Final[float] = 0.15
DAY_TRADE_RATE: Final[float] = 0.20
DARF_MINIMUM: Final[float] = 10.0


class TaxCategory(StrEnum):
    COMMON = "comum"
    DAY_TRADE = "day_trade"


class PieceKind(StrEnum):
    CLOSE = "encerramento"
    EXPIRED = "po"


@dataclass(frozen=True, slots=True)
class TaxPiece:
    """``result`` em R$, já com os custos; ``operations`` são os nomes das operações com movimento
    que entrou na peça, na ordem em que aparecem, sem repetir."""

    on: date
    symbol: str
    category: TaxCategory
    kind: PieceKind
    result: float
    operations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExerciseNote:
    """``operation`` é o nome da operação cuja perna foi exercida ou atribuída."""

    on: date
    symbol: str
    operation: str


@dataclass(frozen=True, slots=True)
class TaxRecords:
    """``pieces`` por (dia, série, categoria); ``exercises`` por (dia, série)."""

    pieces: tuple[TaxPiece, ...]
    exercises: tuple[ExerciseNote, ...]


@dataclass(frozen=True, slots=True)
class TaxMonth:
    """Um mês da apuração. ``month`` é o dia 1; ``*_result`` é a soma das peças da categoria;
    ``*_base`` é o resultado positivo menos o prejuízo da categoria usado; ``*_loss`` é o prejuízo
    que sobra para os meses seguintes. ``tax`` é o IR do próprio mês; ``carried_in`` é o IR abaixo
    de R$ 10 que veio dos meses anteriores; ``due`` é o que se paga no mês e ``carried_out`` o que
    fica para o próximo (um dos dois é sempre zero)."""

    month: date
    common_result: float
    day_trade_result: float
    common_base: float
    day_trade_base: float
    common_loss: float
    day_trade_loss: float
    tax: float
    carried_in: float
    due: float
    carried_out: float
    pieces: tuple[TaxPiece, ...]
    exercises: tuple[ExerciseNote, ...]


@dataclass(frozen=True, slots=True)
class _Negocio:
    """``side`` é o do negócio (BUY compra, SELL venda); ``value`` já tem o custo dentro."""

    on: date
    operation: str
    side: Side
    quantity: int
    value: float


@dataclass(frozen=True, slots=True)
class _Baixa:
    """Tira da posição o que o evento leva; ``side`` é o lado da posição que ele tira."""

    on: date
    operation: str
    event: Expired | Exercise | Assignment
    side: Side
    quantity: int


_Movimento = _Negocio | _Baixa


class _Perna:
    __slots__ = ("lado", "quantidade")

    def __init__(self) -> None:
        self.lado: Side | None = None
        self.quantidade = 0


class _Posicao:
    __slots__ = ("lado", "media", "quantidade")

    def __init__(self) -> None:
        self.lado: Side | None = None
        self.quantidade = 0
        self.media = 0.0


def _tirar_da_perna(perna: _Perna, quantidade: int) -> None:
    perna.quantidade -= quantidade
    if perna.quantidade == 0:
        perna.lado = None


def _negocio(
    operation: Operation,
    ref: OptionLegRef,
    evento: Open | Close,
    lado: Side,
    schedules: Sequence[CostSchedule],
) -> tuple[str, _Movimento]:
    custo = event_costs(evento, ref, schedules)
    valor = evento.quantity * evento.price + lado.sign * custo
    return ref.symbol, _Negocio(evento.on, operation.name, lado, evento.quantity, valor)


def _movimentos(
    operation: Operation, schedules: Sequence[CostSchedule]
) -> Iterator[tuple[str, _Movimento]]:
    """Refaz os eventos de cada perna de opção, na ordem, para saber o lado em cada um."""
    pernas = [_Perna() for _ in operation.legs]
    for evento in operation.events:
        ref, perna = operation.legs[evento.leg], pernas[evento.leg]
        if not isinstance(ref, OptionLegRef):
            continue
        match evento:
            case Open():
                perna.lado = evento.side
                perna.quantidade += evento.quantity
                yield _negocio(operation, ref, evento, evento.side, schedules)
            case Close():
                assert perna.lado is not None  # garantido por leg_states
                oposto = perna.lado.opposite
                _tirar_da_perna(perna, evento.quantity)
                yield _negocio(operation, ref, evento, oposto, schedules)
            case Expired() | Exercise() | Assignment():
                assert perna.lado is not None  # garantido por leg_states
                quantidade = perna.quantidade if isinstance(evento, Expired) else evento.quantity
                yield (
                    ref.symbol,
                    _Baixa(evento.on, operation.name, evento, perna.lado, quantidade),
                )
                _tirar_da_perna(perna, quantidade)


def _nomes(negocios: Sequence[_Negocio]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(n.operation for n in negocios))


def _preco_medio(negocios: Sequence[_Negocio]) -> float:
    return fsum(n.value for n in negocios) / sum(n.quantity for n in negocios)


def _baixar(posicao: _Posicao, quantidade: int) -> None:
    posicao.quantidade -= quantidade
    if posicao.quantidade == 0:
        posicao.lado, posicao.media = None, 0.0


def _somar_a_posicao(
    posicao: _Posicao, lado: Side, quantidade: int, preco: float
) -> tuple[int, float]:
    """A sobra do dia na posição comum: no mesmo sentido recalcula o médio; no oposto encerra até a
    quantidade aberta e o que passar abre o lado oposto. Devolve (encerrado, resultado)."""
    encerrado, resultado = 0, 0.0
    if posicao.lado is not None and posicao.lado is not lado:
        encerrado = min(quantidade, posicao.quantidade)
        resultado = posicao.lado.sign * (preco - posicao.media) * encerrado
        _baixar(posicao, encerrado)
        quantidade -= encerrado
    if quantidade:
        total = posicao.quantidade + quantidade
        posicao.media = fsum((posicao.media * posicao.quantidade, preco * quantidade)) / total
        posicao.quantidade = total
        posicao.lado = lado
    return encerrado, resultado


def _negociar_dia(
    posicao: _Posicao, dia: date, simbolo: str, negocios: Sequence[_Negocio]
) -> list[TaxPiece]:
    compras = [n for n in negocios if n.side is Side.BUY]
    vendas = [n for n in negocios if n.side is Side.SELL]
    comprado, vendido = sum(n.quantity for n in compras), sum(n.quantity for n in vendas)
    pecas: list[TaxPiece] = []
    casado = min(comprado, vendido)
    if casado:
        resultado = casado * (_preco_medio(vendas) - _preco_medio(compras))
        pecas.append(
            TaxPiece(
                dia, simbolo, TaxCategory.DAY_TRADE, PieceKind.CLOSE, resultado, _nomes(negocios)
            )
        )
    if comprado == vendido:
        return pecas
    lado, sobra = (
        (Side.BUY, comprado - vendido) if comprado > vendido else (Side.SELL, vendido - comprado)
    )
    do_lado = compras if lado is Side.BUY else vendas
    encerrado, resultado = _somar_a_posicao(posicao, lado, sobra, _preco_medio(do_lado))
    if encerrado:
        pecas.append(
            TaxPiece(dia, simbolo, TaxCategory.COMMON, PieceKind.CLOSE, resultado, _nomes(do_lado))
        )
    return pecas


def _apurar_serie(
    simbolo: str, movimentos: Sequence[_Movimento]
) -> tuple[list[TaxPiece], list[ExerciseNote]]:
    posicao = _Posicao()
    pecas: list[TaxPiece] = []
    notas: list[ExerciseNote] = []
    # sorted é estável: no mesmo dia vale a ordem das operações recebidas e a dos eventos
    for dia, grupo in groupby(sorted(movimentos, key=lambda m: m.on), key=lambda m: m.on):
        do_dia = list(grupo)
        pecas += _negociar_dia(
            posicao, dia, simbolo, [m for m in do_dia if isinstance(m, _Negocio)]
        )
        for baixa in (m for m in do_dia if isinstance(m, _Baixa)):
            # a posição comum pode ter menos (ou outro lado) que a perna: outra operação da série
            # já pode ter casado a diferença; baixa só o que existe do lado dela
            tirada, media = 0, posicao.media
            if posicao.lado is baixa.side:
                tirada = min(baixa.quantity, posicao.quantidade)
                _baixar(posicao, tirada)
            match baixa.event:
                case Expired() if tirada:
                    resultado = -baixa.side.sign * media * tirada
                    pecas.append(
                        TaxPiece(
                            dia,
                            simbolo,
                            TaxCategory.COMMON,
                            PieceKind.EXPIRED,
                            resultado,
                            (baixa.operation,),
                        )
                    )
                case Exercise() | Assignment():
                    notas.append(ExerciseNote(dia, simbolo, baixa.operation))
    return pecas, notas


def tax_records(operations: Sequence[Operation], schedules: Sequence[CostSchedule]) -> TaxRecords:
    """Junta as pernas de opção de todas as operações por série e devolve as peças e as notas."""
    por_serie: dict[str, list[_Movimento]] = {}
    for operation in operations:
        for simbolo, movimento in _movimentos(operation, schedules):
            por_serie.setdefault(simbolo, []).append(movimento)
    pecas: list[TaxPiece] = []
    notas: list[ExerciseNote] = []
    for simbolo, movimentos in por_serie.items():
        da_serie, notas_da_serie = _apurar_serie(simbolo, movimentos)
        pecas += da_serie
        notas += notas_da_serie
    return TaxRecords(
        tuple(sorted(pecas, key=lambda p: (p.on, p.symbol, p.category))),
        tuple(sorted(notas, key=lambda n: (n.on, n.symbol))),
    )


def _compensar(resultado: float, prejuizo: float) -> tuple[float, float]:
    """Resultado positivo abate o prejuízo da categoria; negativo soma a ele. Devolve (base,
    prejuízo que sobra)."""
    if resultado < 0:
        return 0.0, prejuizo - resultado
    usado = min(resultado, prejuizo)
    return resultado - usado, prejuizo - usado


def monthly_tax(records: TaxRecords) -> tuple[TaxMonth, ...]:
    """Apura mês a mês: compensa o prejuízo por categoria, aplica as alíquotas e o DARF mínimo."""
    pecas_do_mes: dict[date, list[TaxPiece]] = {}
    for peca in records.pieces:
        pecas_do_mes.setdefault(peca.on.replace(day=1), []).append(peca)
    notas_do_mes: dict[date, list[ExerciseNote]] = {}
    for nota in records.exercises:
        notas_do_mes.setdefault(nota.on.replace(day=1), []).append(nota)
    meses: list[TaxMonth] = []
    prejuizo_comum = prejuizo_day_trade = pendente = 0.0
    for mes in sorted(pecas_do_mes.keys() | notas_do_mes.keys()):
        pecas = pecas_do_mes.get(mes, [])
        comum = fsum(p.result for p in pecas if p.category is TaxCategory.COMMON)
        day_trade = fsum(p.result for p in pecas if p.category is TaxCategory.DAY_TRADE)
        base_comum, prejuizo_comum = _compensar(comum, prejuizo_comum)
        base_day_trade, prejuizo_day_trade = _compensar(day_trade, prejuizo_day_trade)
        imposto = round(
            round(COMMON_RATE * base_comum, 2) + round(DAY_TRADE_RATE * base_day_trade, 2), 2
        )
        total = round(imposto + pendente, 2)
        devido, adiado = (total, 0.0) if total >= DARF_MINIMUM else (0.0, total)
        meses.append(
            TaxMonth(
                month=mes,
                common_result=comum,
                day_trade_result=day_trade,
                common_base=base_comum,
                day_trade_base=base_day_trade,
                common_loss=prejuizo_comum,
                day_trade_loss=prejuizo_day_trade,
                tax=imposto,
                carried_in=pendente,
                due=devido,
                carried_out=adiado,
                pieces=tuple(pecas),
                exercises=tuple(notas_do_mes.get(mes, [])),
            )
        )
        pendente = adiado
    return tuple(meses)

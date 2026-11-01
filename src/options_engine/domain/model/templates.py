"""Modelos prontos do montador: a forma de cada estrutura das quatro famílias.

O modelo diz o tipo, o lado e a proporção de cada perna, e onde fica o strike em passos a partir
do strike mais perto do spot. Quem escolhe a série é o usuário; o modelo só sugere e confere.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum

from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidStrategyError
from options_engine.domain.model.factories import (
    butterfly,
    cash_secured_put,
    collar,
    covered_call,
    iron_condor,
    long_call,
    long_put,
    protective_put,
    straddle,
    strangle,
    vertical_spread,
)
from options_engine.domain.model.strategy import StockLeg, Strategy, StrategyLeg

__all__ = ["TEMPLATES", "Family", "Template", "TemplateLeg", "suggest_strikes", "template"]


class Family(Enum):
    RENDA = "renda"
    DIRECIONAIS = "direcionais"
    VOLATILIDADE = "volatilidade"
    PROTECAO = "protecao"


@dataclass(frozen=True, slots=True)
class TemplateLeg:
    option_type: OptionType
    side: Side
    ratio: int
    offset: int


_Fabrica = Callable[[Sequence[StrategyLeg], StockLeg | None, str], Strategy]


def _sem_acao(fabrica: Callable[[Sequence[StrategyLeg], str | None], Strategy]) -> _Fabrica:
    return lambda legs, _stock, name: fabrica(legs, name)


def _com_acao(
    fabrica: Callable[[Sequence[StrategyLeg], StockLeg, str | None], Strategy],
) -> _Fabrica:
    def montar(legs: Sequence[StrategyLeg], stock: StockLeg | None, name: str) -> Strategy:
        if stock is None:
            raise InvalidStrategyError(f"o modelo {name} exige a perna de ação")
        return fabrica(legs, stock, name)

    return montar


@dataclass(frozen=True, slots=True)
class Template:
    key: str
    family: Family
    name: str
    legs: tuple[TemplateLeg, ...]
    factory: _Fabrica
    stock: Side | None = None

    def build(self, legs: Sequence[StrategyLeg], stock: StockLeg | None) -> Strategy:
        """A estrutura pela fábrica da família, desde que as pernas tenham a forma do modelo."""
        if (stock is None) != (self.stock is None):
            exigencia = "exige a perna de ação" if self.stock is not None else "não tem ação"
            raise InvalidStrategyError(f"o modelo {self.name} {exigencia}")
        if stock is not None and stock.side is not self.stock:
            lado = "comprada" if self.stock is Side.BUY else "vendida"
            raise InvalidStrategyError(f"o modelo {self.name} exige a ação {lado}")
        self._exige_forma(legs)
        return self.factory(legs, stock, self.name)

    def _exige_forma(self, legs: Sequence[StrategyLeg]) -> None:
        esperado = sorted(self.legs, key=lambda p: (p.offset, p.option_type.value))
        recebido = sorted(legs, key=lambda p: (p.terms.strike, p.terms.option_type.value))
        forma_ok = len(esperado) == len(recebido) and all(
            (e.option_type, e.side) == (r.terms.option_type, r.side)
            for e, r in zip(esperado, recebido, strict=False)
        )
        lotes = {r.quantity / e.ratio for e, r in zip(esperado, recebido, strict=False)}
        if not forma_ok or len(lotes) != 1:
            raise InvalidStrategyError(
                f"as pernas não formam o modelo {self.name}: esperado "
                f"{[(e.option_type.value, e.side.value, e.ratio) for e in esperado]!r}"
            )


def _perna(option_type: OptionType, side: Side, offset: int, ratio: int = 1) -> TemplateLeg:
    return TemplateLeg(option_type, side, ratio, offset)


_C, _P = OptionType.CALL, OptionType.PUT
_B, _S = Side.BUY, Side.SELL

TEMPLATES: tuple[Template, ...] = (
    Template(
        "venda_coberta",
        Family.RENDA,
        "venda coberta",
        (_perna(_C, _S, 1),),
        _com_acao(covered_call),
        _B,
    ),
    Template(
        "put_coberta",
        Family.RENDA,
        "put coberta",
        (_perna(_P, _S, -1),),
        _sem_acao(cash_secured_put),
    ),
    Template(
        "trava_alta_put",
        Family.RENDA,
        "trava de alta com put",
        (_perna(_P, _B, -2), _perna(_P, _S, -1)),
        _sem_acao(vertical_spread),
    ),
    Template(
        "trava_baixa_call",
        Family.RENDA,
        "trava de baixa com call",
        (_perna(_C, _S, 1), _perna(_C, _B, 2)),
        _sem_acao(vertical_spread),
    ),
    Template(
        "compra_call",
        Family.DIRECIONAIS,
        "compra de call",
        (_perna(_C, _B, 0),),
        _sem_acao(long_call),
    ),
    Template(
        "compra_put", Family.DIRECIONAIS, "compra de put", (_perna(_P, _B, 0),), _sem_acao(long_put)
    ),
    Template(
        "trava_alta_call",
        Family.DIRECIONAIS,
        "trava de alta com call",
        (_perna(_C, _B, 0), _perna(_C, _S, 1)),
        _sem_acao(vertical_spread),
    ),
    Template(
        "trava_baixa_put",
        Family.DIRECIONAIS,
        "trava de baixa com put",
        (_perna(_P, _S, -1), _perna(_P, _B, 0)),
        _sem_acao(vertical_spread),
    ),
    Template(
        "straddle_comprado",
        Family.VOLATILIDADE,
        "straddle comprado",
        (_perna(_C, _B, 0), _perna(_P, _B, 0)),
        _sem_acao(straddle),
    ),
    Template(
        "straddle_vendido",
        Family.VOLATILIDADE,
        "straddle vendido",
        (_perna(_C, _S, 0), _perna(_P, _S, 0)),
        _sem_acao(straddle),
    ),
    Template(
        "strangle_comprado",
        Family.VOLATILIDADE,
        "strangle comprado",
        (_perna(_P, _B, -1), _perna(_C, _B, 1)),
        _sem_acao(strangle),
    ),
    Template(
        "strangle_vendido",
        Family.VOLATILIDADE,
        "strangle vendido",
        (_perna(_P, _S, -1), _perna(_C, _S, 1)),
        _sem_acao(strangle),
    ),
    Template(
        "iron_condor_vendido",
        Family.VOLATILIDADE,
        "iron condor vendido",
        (_perna(_P, _B, -2), _perna(_P, _S, -1), _perna(_C, _S, 1), _perna(_C, _B, 2)),
        _sem_acao(iron_condor),
    ),
    Template(
        "iron_condor_comprado",
        Family.VOLATILIDADE,
        "iron condor comprado",
        (_perna(_P, _S, -2), _perna(_P, _B, -1), _perna(_C, _B, 1), _perna(_C, _S, 2)),
        _sem_acao(iron_condor),
    ),
    Template(
        "borboleta_comprada",
        Family.VOLATILIDADE,
        "borboleta comprada",
        (_perna(_C, _B, -1), _perna(_C, _S, 0, ratio=2), _perna(_C, _B, 1)),
        _sem_acao(butterfly),
    ),
    Template(
        "borboleta_vendida",
        Family.VOLATILIDADE,
        "borboleta vendida",
        (_perna(_C, _S, -1), _perna(_C, _B, 0, ratio=2), _perna(_C, _S, 1)),
        _sem_acao(butterfly),
    ),
    Template(
        "put_protetora",
        Family.PROTECAO,
        "put protetora",
        (_perna(_P, _B, -1),),
        _com_acao(protective_put),
        _B,
    ),
    Template(
        "collar",
        Family.PROTECAO,
        "collar",
        (_perna(_P, _B, -1), _perna(_C, _S, 1)),
        _com_acao(collar),
        _B,
    ),
)

_POR_CHAVE = {modelo.key: modelo for modelo in TEMPLATES}


def template(key: str) -> Template:
    return _POR_CHAVE[key]


def suggest_strikes(modelo: Template, strikes: Sequence[float], spot: float) -> tuple[float, ...]:
    """Strike de cada perna, na ordem de ``modelo.legs``: o mais perto do spot mais o passo dela.

    Empate entre dois strikes fica com o menor, para a sugestão não depender da ordem da cadeia.
    """
    ordenados = sorted(set(strikes))
    if not ordenados:
        raise InvalidStrategyError(f"cadeia sem strikes para sugerir o modelo {modelo.name}")
    no_dinheiro = min(range(len(ordenados)), key=lambda i: (abs(ordenados[i] - spot), i))
    indices = [no_dinheiro + perna.offset for perna in modelo.legs]
    if min(indices) < 0 or max(indices) >= len(ordenados):
        raise InvalidStrategyError(
            f"o modelo {modelo.name} precisa de {max(indices) - min(indices) + 1} strikes em "
            f"volta do spot {spot:g}; a cadeia tem strikes {ordenados!r}"
        )
    return tuple(ordenados[i] for i in indices)

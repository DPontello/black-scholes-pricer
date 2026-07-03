"""Factories nomeadas de estruturas — validação geométrica E de composição.

Cada factory recebe as legs (com tickers e prêmios reais, vindos dos
contratos listados) e valida que elas FORMAM a estrutura nomeada: ordem
estrita de strikes, tipos e sides corretos, quantidades coerentes.
Validar só a ordem de strikes deixaria passar um "condor" de 4 calls —
composição é metade da validação (ROADMAP Sprint 2).

Violação → ``InvalidStrategyError``. As invariantes do agregado (mesmo
subjacente, mesmo vencimento) são de ``Strategy.create`` — aqui vive apenas
o que é específico da geometria nomeada.

As legs retornam SEMPRE ordenadas por strike crescente: ordem canônica
determinística para as agregações com ``math.fsum`` (CONVENTIONS §6).
"""

from collections.abc import Sequence

from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidStrategyError
from options_engine.domain.model.strategy import Strategy, StrategyLeg

__all__ = ["butterfly", "condor_direction", "iron_condor", "straddle", "strangle"]


def _ordenadas_por_strike(
    legs: Sequence[StrategyLeg], n: int, estrutura: str
) -> tuple[StrategyLeg, ...]:
    if len(legs) != n:
        raise InvalidStrategyError(f"{estrutura} exige exatamente {n} legs; recebido {len(legs)}")
    return tuple(sorted(legs, key=lambda leg: leg.terms.strike))


def _exige_quantidades_iguais(legs: Sequence[StrategyLeg], estrutura: str) -> None:
    quantidades = {leg.quantity for leg in legs}
    if len(quantidades) > 1:
        raise InvalidStrategyError(
            f"{estrutura} exige quantidades iguais em todas as legs; "
            f"recebido {[leg.quantity for leg in legs]!r}"
        )


def _rotulo_direcao(side_da_estrutura: Side) -> str:
    return "comprado (débito)" if side_da_estrutura is Side.BUY else "vendido (crédito)"


def iron_condor(legs: Sequence[StrategyLeg], name: str | None = None) -> Strategy:
    """Valida e monta um iron condor: put spread + call spread, 4 strikes.

    Aceita AMBAS as direções (decisão ratificada nº 3): vendido/crédito
    (corpo K2/K3 vendido, asas K1/K4 compradas — o clássico) e
    comprado/débito (o espelho). A direção é lida da estrutura, nunca
    assumida — ver ``condor_direction``.

    Geometria: K1 < K2 < K3 < K4 estritos. Composição: puts em K1 e K2,
    calls em K3 e K4; asas num lado, corpo no oposto; quantidades iguais.
    """
    ordenadas = _ordenadas_por_strike(legs, 4, "iron condor")
    k = [leg.terms.strike for leg in ordenadas]
    if not (k[0] < k[1] < k[2] < k[3]):
        raise InvalidStrategyError(f"iron condor exige K1 < K2 < K3 < K4 estritos; recebido {k!r}")
    tipos = [leg.terms.option_type for leg in ordenadas]
    if tipos != [OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL]:
        raise InvalidStrategyError(
            f"iron condor exige puts nos 2 strikes de baixo e calls nos 2 de "
            f"cima; recebido {[t.value for t in tipos]!r}"
        )
    asa_baixa, corpo_put, corpo_call, asa_alta = ordenadas
    if asa_baixa.side is not asa_alta.side or corpo_put.side is not corpo_call.side:
        raise InvalidStrategyError(
            "iron condor exige asas do mesmo lado e corpo do mesmo lado; "
            f"recebido {[leg.side.value for leg in ordenadas]!r}"
        )
    if corpo_put.side is not asa_baixa.side.opposite:
        raise InvalidStrategyError(
            "iron condor exige corpo no lado oposto ao das asas (spread duplo); "
            f"recebido {[leg.side.value for leg in ordenadas]!r}"
        )
    _exige_quantidades_iguais(ordenadas, "iron condor")
    # Direção da estrutura = lado do CORPO: corpo vendido é o condor clássico
    # de crédito; corpo comprado é o de débito.
    rotulo = _rotulo_direcao(corpo_put.side)
    return Strategy.create(name if name is not None else f"iron condor {rotulo}", ordenadas)


def condor_direction(strategy: Strategy) -> Side:
    """Direção de um condor JÁ validado por ``iron_condor``: lado do corpo.

    SELL = vendido (crédito), BUY = comprado (débito). Pré-condição: a
    estrutura veio da factory (legs ordenadas, composição garantida).
    """
    return strategy.legs[1].side


def straddle(legs: Sequence[StrategyLeg], name: str | None = None) -> Strategy:
    """Valida e monta um straddle: call + put no MESMO strike, mesmo lado.

    Comprado = long vega clássico (V em K); vendido = o espelho.
    """
    ordenadas = _ordenadas_por_strike(legs, 2, "straddle")
    a, b = ordenadas
    if a.terms.strike != b.terms.strike:
        raise InvalidStrategyError(
            f"straddle exige strike único; recebido "
            f"{[leg.terms.strike for leg in ordenadas]!r} (strikes distintos são um strangle)"
        )
    if {a.terms.option_type, b.terms.option_type} != {OptionType.CALL, OptionType.PUT}:
        raise InvalidStrategyError(
            f"straddle exige exatamente uma call e uma put; recebido "
            f"{[leg.terms.option_type.value for leg in ordenadas]!r}"
        )
    if a.side is not b.side:
        raise InvalidStrategyError(
            f"straddle exige as duas legs do mesmo lado; recebido "
            f"{[leg.side.value for leg in ordenadas]!r}"
        )
    _exige_quantidades_iguais(ordenadas, "straddle")
    rotulo = "comprado" if a.side is Side.BUY else "vendido"
    return Strategy.create(name if name is not None else f"straddle {rotulo}", ordenadas)


def strangle(legs: Sequence[StrategyLeg], name: str | None = None) -> Strategy:
    """Valida e monta um strangle: put abaixo + call acima, mesmo lado.

    Geometria: strike da put ESTRITAMENTE menor que o da call — strikes
    iguais são um straddle e a factory não aceita ambiguidade de nome.
    """
    ordenadas = _ordenadas_por_strike(legs, 2, "strangle")
    put_leg, call_leg = ordenadas
    if (
        put_leg.terms.option_type is not OptionType.PUT
        or call_leg.terms.option_type is not OptionType.CALL
    ):
        raise InvalidStrategyError(
            f"strangle exige put no strike de baixo e call no de cima; recebido "
            f"{[(leg.terms.option_type.value, leg.terms.strike) for leg in ordenadas]!r}"
        )
    if not (put_leg.terms.strike < call_leg.terms.strike):
        raise InvalidStrategyError(
            f"strangle exige strike da put < strike da call; recebido "
            f"{[leg.terms.strike for leg in ordenadas]!r}"
        )
    if put_leg.side is not call_leg.side:
        raise InvalidStrategyError(
            f"strangle exige as duas legs do mesmo lado; recebido "
            f"{[leg.side.value for leg in ordenadas]!r}"
        )
    _exige_quantidades_iguais(ordenadas, "strangle")
    rotulo = "comprado" if put_leg.side is Side.BUY else "vendido"
    return Strategy.create(name if name is not None else f"strangle {rotulo}", ordenadas)


def butterfly(legs: Sequence[StrategyLeg], name: str | None = None) -> Strategy:
    """Valida e monta uma butterfly: asas 1x num lado, corpo 2x no oposto.

    Geometria: K1 < K2 < K3 estritos (asas não precisam ser equidistantes —
    broken wing é permitida; o pico/vale continua em K2). Composição: as 3
    legs do MESMO tipo (all-calls ou all-puts — payoffs idênticos), asas do
    mesmo lado com quantidades iguais, corpo no lado oposto com o DOBRO da
    quantidade da asa.
    """
    ordenadas = _ordenadas_por_strike(legs, 3, "butterfly")
    k = [leg.terms.strike for leg in ordenadas]
    if not (k[0] < k[1] < k[2]):
        raise InvalidStrategyError(f"butterfly exige K1 < K2 < K3 estritos; recebido {k!r}")
    tipos = {leg.terms.option_type for leg in ordenadas}
    if len(tipos) > 1:
        raise InvalidStrategyError(
            f"butterfly exige as 3 legs do mesmo tipo (all-calls ou all-puts); "
            f"recebido {[leg.terms.option_type.value for leg in ordenadas]!r}"
        )
    asa_baixa, corpo, asa_alta = ordenadas
    if asa_baixa.side is not asa_alta.side:
        raise InvalidStrategyError(
            f"butterfly exige asas do mesmo lado; recebido "
            f"{[leg.side.value for leg in ordenadas]!r}"
        )
    if corpo.side is not asa_baixa.side.opposite:
        raise InvalidStrategyError(
            f"butterfly exige corpo no lado oposto ao das asas; recebido "
            f"{[leg.side.value for leg in ordenadas]!r}"
        )
    if asa_baixa.quantity != asa_alta.quantity:
        raise InvalidStrategyError(
            f"butterfly exige asas com a mesma quantidade; recebido "
            f"{[leg.quantity for leg in ordenadas]!r}"
        )
    if corpo.quantity != 2 * asa_baixa.quantity:
        raise InvalidStrategyError(
            f"butterfly exige corpo com o dobro da quantidade da asa (1x/2x/1x); "
            f"recebido {[leg.quantity for leg in ordenadas]!r}"
        )
    rotulo = "comprada" if asa_baixa.side is Side.BUY else "vendida"
    return Strategy.create(name if name is not None else f"butterfly {rotulo}", ordenadas)

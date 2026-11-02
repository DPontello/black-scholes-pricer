"""Família Direcionais do book (spec da semana 3, §3.3), sem visão e com visão.

Sem visão: as calls e puts com delta (módulo) de 0,30 a 0,60, IV da série abaixo da HV 21 e IV
rank até 30%, rotuladas como não direcionais. Com visão (ativo, direção, alvo e vencimento): a
compra a seco e as travas de débito (comprada entre o spot e o alvo, vendida no alvo ou depois,
de 1 a 3 strikes de largura), pelo resultado líquido no alvo sobre o risco líquido.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import Enum, unique
from math import isfinite
from typing import Final

from options_engine.domain.analytics.volatility import LOW_RANK, VolContext
from options_engine.domain.book.model import (
    BookExclusion,
    BookItem,
    BookLabel,
    FamilyResult,
    Metric,
    MetricUnit,
)
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.book.scan import (
    PricedLeg,
    ScannedExpiry,
    ScannedSeries,
    book_legs,
    evaluate,
    keeps_liquidity,
    price_leg,
    scan_chain,
)
from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.kernel.black_scholes import d1_d2
from options_engine.domain.kernel.distributions import norm_cdf
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.templates import Family, template

__all__ = ["Direction", "DirectionalView", "cheap_options", "directional_items"]

_LOTE: Final = 100
_DELTA_SEM_VISAO: Final = (0.30, 0.60)
_LARGURAS: Final = (1, 2, 3)


@unique
class Direction(Enum):
    ALTA = "alta"
    BAIXA = "baixa"


@dataclass(frozen=True, slots=True)
class DirectionalView:
    underlying: str
    direction: Direction
    target: float
    expiry: date

    def __post_init__(self) -> None:
        if not self.underlying.strip():
            raise InvalidDomainValueError("a visão exige o ativo")
        if not (isfinite(self.target) and self.target > 0.0):
            raise InvalidDomainValueError(f"alvo deve ser finito e > 0; recebido {self.target!r}")


def cheap_options(
    chain: OptionChain,
    context: VolContext,
    settings: BookSettings,
    schedule: CostSchedule,
    business_days: Mapping[date, int],
) -> FamilyResult:
    """Sem visão: maior desconto da vol primeiro; vazio sem IV rank ou com rank acima de 30%."""
    vencimentos, exclusoes = scan_chain(chain, business_days, settings.expiries)
    if context.iv_rank is None or context.iv_rank > LOW_RANK:
        return FamilyResult.of((), exclusoes)
    fora = list(exclusoes)
    itens = []
    baixo, alto = _DELTA_SEM_VISAO
    for vencimento in vencimentos:
        for serie in (*vencimento.calls, *vencimento.puts):
            iv = serie.implied_vol
            if iv is None or iv >= context.hv21 or not baixo <= abs(serie.delta) <= alto:
                continue
            perna = _precificar(vencimento, settings, fora, (serie, Side.BUY, _LOTE))
            item = perna and _barata(chain, context, settings, schedule, vencimento, perna, iv)
            if item:
                itens.append(item)
    return FamilyResult.of(itens, fora)


def directional_items(
    chain: OptionChain,
    view: DirectionalView,
    settings: BookSettings,
    schedule: CostSchedule,
    business_days: Mapping[date, int],
) -> FamilyResult:
    """Com visão: maior resultado no alvo sobre o risco primeiro. Alvo do lado errado do spot ou
    vencimento sem séries é recusado com o motivo."""
    spot = chain.underlying.spot
    alta = view.direction is Direction.ALTA
    if (view.target <= spot) if alta else (view.target >= spot):
        lado = "acima" if alta else "abaixo"
        raise InvalidDomainValueError(
            f"numa visão de {view.direction.value} o alvo precisa estar {lado} do spot "
            f"{spot:g}; recebido {view.target:g}"
        )
    dias = {view.expiry: business_days[view.expiry]} if view.expiry in business_days else {}
    vencimentos, exclusoes = scan_chain(chain, dias, 1)
    if not vencimentos:
        raise InvalidDomainValueError(
            f"{view.underlying}: sem séries com pelo menos 1 dia útil no vencimento "
            f"{view.expiry.isoformat()}"
        )
    (vencimento,) = vencimentos
    tipo = OptionType.CALL if alta else OptionType.PUT
    passo = 1 if alta else -1
    no_dinheiro = vencimento.at_the_money(tipo)
    fora = list(exclusoes)
    itens = []
    for comprada in _entre_spot_e_alvo(vencimento, tipo, no_dinheiro, view.target, alta):
        candidatas: list[tuple[str, Sequence[tuple[ScannedSeries, Side, int]]]] = [
            ("compra_call" if alta else "compra_put", ((comprada, Side.BUY, _LOTE),))
        ]
        for largura in _LARGURAS:
            vendida = vencimento.neighbor(comprada, passo * largura)
            if vendida is None:
                break
            if (vendida.strike >= view.target) if alta else (vendida.strike <= view.target):
                pernas = ((comprada, Side.BUY, _LOTE), (vendida, Side.SELL, _LOTE))
                if not alta:
                    pernas = pernas[::-1]
                candidatas.append(("trava_alta_call" if alta else "trava_baixa_put", pernas))
        for chave, pedido in candidatas:
            precificadas = _precificar(vencimento, settings, fora, *pedido)
            item = precificadas and _com_visao(
                chain, view, settings, schedule, vencimento, chave, precificadas
            )
            if item:
                itens.append(item)
    return FamilyResult.of(itens, fora)


def _entre_spot_e_alvo(
    expiry: ScannedExpiry,
    option_type: OptionType,
    no_dinheiro: ScannedSeries | None,
    alvo: float,
    alta: bool,
) -> list[ScannedSeries]:
    """As séries do strike no dinheiro até antes do alvo, na direção da visão."""
    if no_dinheiro is None:
        return []
    k0 = no_dinheiro.strike
    return [
        s
        for s in expiry.of_type(option_type)
        if ((k0 <= s.strike < alvo) if alta else (alvo < s.strike <= k0))
    ]


def _precificar(
    expiry: ScannedExpiry,
    settings: BookSettings,
    exclusions: list[BookExclusion],
    *pernas: tuple[ScannedSeries, Side, int],
) -> list[PricedLeg] | None:
    precificadas = []
    for serie, lado, quantidade in pernas:
        perna = price_leg(expiry, serie, lado, quantidade)
        if isinstance(perna, str):
            exclusions.append(BookExclusion("/".join(s.symbol for s, _, _ in pernas), perna))
            return None
        precificadas.append(perna)
    return precificadas if keeps_liquidity(precificadas, settings) else None


def _barata(
    chain: OptionChain,
    context: VolContext,
    settings: BookSettings,
    schedule: CostSchedule,
    expiry: ScannedExpiry,
    pernas: list[PricedLeg],
    iv: float,
) -> BookItem | None:
    (perna,) = pernas
    chave = "compra_call" if perna.series.option_type is OptionType.CALL else "compra_put"
    resultado = evaluate(chave, pernas, chain, expiry, schedule)
    perda = resultado.net_max_loss
    if perda is None or -perda > settings.max_risk:
        return None
    assert context.iv_rank is not None  # garantido por cheap_options
    nome = "call" if chave == "compra_call" else "put"
    return BookItem(
        family=Family.DIRECIONAIS,
        template_key=chave,
        underlying=context.underlying,
        expiry=expiry.expiry,
        business_days=expiry.business_days,
        legs=book_legs(pernas),
        stock=None,
        criterion=Metric(
            "desconto_vol",
            "desconto da vol sobre a HV 21",
            (context.hv21 - iv) / context.hv21,
            MetricUnit.PERCENT,
        ),
        metrics=(
            Metric("iv_serie", "IV da série", iv, MetricUnit.PERCENT),
            Metric("hv21", "HV 21", context.hv21, MetricUnit.PERCENT),
            Metric("iv_rank", "IV rank", context.iv_rank, MetricUnit.PERCENT),
            Metric("premio", "prêmio por ação", perna.premium.premium, MetricUnit.CURRENCY),
            Metric("delta", "delta", perna.series.delta, MetricUnit.NUMBER),
        ),
        reason=(
            f"A {nome} {perna.series.symbol} tem IV de {{iv_serie}} contra HV 21 de {{hv21}} "
            "(desconto de {desconto_vol}) com IV rank de {iv_rank}: opção barata pela vol, "
            "sem visão de direção."
        ),
        labels=(BookLabel.NAO_DIRECIONAL,),
    )


def _com_visao(
    chain: OptionChain,
    view: DirectionalView,
    settings: BookSettings,
    schedule: CostSchedule,
    expiry: ScannedExpiry,
    chave: str,
    pernas: list[PricedLeg],
) -> BookItem | None:
    resultado = evaluate(chave, pernas, chain, expiry, schedule, target=view.target)
    perda, no_alvo = resultado.net_max_loss, resultado.net_at_target
    if perda is None or no_alvo is None or no_alvo <= 0.0 or -perda > settings.max_risk:
        return None
    risco = -perda
    spot = chain.underlying.spot
    vol = expiry.smile.vol_at(spot) or chain.underlying.volatility.value
    _, d2 = d1_d2(
        spot,
        view.target,
        expiry.time_to_expiry.year_fraction,
        chain.underlying.risk_free_rate.as_continuous(),
        vol,
    )
    alta = view.direction is Direction.ALTA
    apoio = [
        Metric("alvo", "alvo", view.target, MetricUnit.CURRENCY),
        Metric("resultado_alvo", "resultado líquido no alvo", no_alvo, MetricUnit.CURRENCY),
        Metric("debito", "débito", -resultado.net_premium, MetricUnit.CURRENCY),
        Metric("risco", "risco líquido", risco, MetricUnit.CURRENCY),
        Metric(
            "prob_alvo",
            "probabilidade de chegar ao alvo",
            norm_cdf(d2) if alta else norm_cdf(-d2),
            MetricUnit.PERCENT,
        ),
    ]
    if resultado.breakevens:
        apoio.append(Metric("breakeven", "breakeven", resultado.breakevens[0], MetricUnit.CURRENCY))
    simbolos = "/".join(leg.series.symbol for leg in pernas)
    frase = (
        f"Visão de {view.direction.value} até {{alvo}}: {template(chave).name} {simbolos} "
        "custa {debito} e dá {resultado_alvo} líquidos se o ativo chegar ao alvo "
        "({retorno_risco} do risco), com {prob_alvo} de probabilidade de chegar lá pela vol "
        "implícita."
    )
    return BookItem(
        family=Family.DIRECIONAIS,
        template_key=chave,
        underlying=view.underlying,
        expiry=expiry.expiry,
        business_days=expiry.business_days,
        legs=book_legs(pernas),
        stock=None,
        criterion=Metric(
            "retorno_risco", "resultado no alvo / risco", no_alvo / risco, MetricUnit.RATIO
        ),
        metrics=tuple(apoio),
        reason=frase,
    )

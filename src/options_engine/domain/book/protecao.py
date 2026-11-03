"""Família Proteção do book (spec da semana 3, §3.3): put protetora e collar.

A posição é a das ações compradas do perfil ou 100 hipotéticas, rotuladas. A put vai do piso do
preset até o strike no dinheiro; o collar vende a call na faixa de delta. Critério: custo mensal
equivalente, ``custo líquido / valor da posição x 21 / dias úteis`` (menor primeiro; collar de
crédito antes de todos). O custo conta só as ordens de opção: a posição já existe.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from math import fsum, isfinite
from typing import Final

from options_engine.domain.book.model import (
    BookExclusion,
    BookItem,
    BookLabel,
    BookStock,
    FamilyResult,
    Metric,
    MetricUnit,
)
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.book.scan import (
    PricedLeg,
    ScannedExpiry,
    ScannedSeries,
    approximation_labels,
    book_legs,
    evaluate,
    keeps_liquidity,
    price_leg,
    scan_chain,
)
from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.strategy import StockLeg
from options_engine.domain.model.templates import Family

__all__ = ["HYPOTHETICAL_SHARES", "ProtectedPosition", "protection_items"]

HYPOTHETICAL_SHARES: Final = 100
_LOTE: Final = 100
_DU_MES: Final = 21


@dataclass(frozen=True, slots=True)
class ProtectedPosition:
    """Ações a proteger; ``average_price`` é o preço médio da carteira (``None`` = hipotética)."""

    underlying: str
    quantity: int
    average_price: float | None
    hypothetical: bool

    def __post_init__(self) -> None:
        if self.quantity < 1:
            raise InvalidDomainValueError(f"posição deve ter >= 1 ação; recebido {self.quantity!r}")
        if self.average_price is not None and not (
            isfinite(self.average_price) and self.average_price > 0.0
        ):
            raise InvalidDomainValueError(
                f"preço médio deve ser finito e > 0; recebido {self.average_price!r}"
            )


def protection_items(
    chain: OptionChain,
    position: ProtectedPosition,
    settings: BookSettings,
    schedule: CostSchedule,
    business_days: Mapping[date, int],
) -> FamilyResult:
    lote = position.quantity // _LOTE * _LOTE
    if lote == 0:
        return FamilyResult(
            exclusions=(
                BookExclusion(
                    position.underlying,
                    f"posição de {position.quantity} ações, menor que um lote de opções "
                    f"({_LOTE}): sem proteção",
                ),
            )
        )
    vencimentos, exclusoes = scan_chain(chain, business_days, settings.expiries)
    fora = list(exclusoes)
    itens = []
    for vencimento in vencimentos:
        for chave, pedido in _candidatas(vencimento, settings, lote):
            pernas = _precificar(vencimento, settings, fora, pedido)
            item = pernas and _item(chain, position, schedule, vencimento, chave, pernas, lote)
            if item:
                itens.append(item)
    return FamilyResult.of(itens, fora)


def _candidatas(
    expiry: ScannedExpiry, settings: BookSettings, lote: int
) -> list[tuple[str, tuple[tuple[ScannedSeries, Side, int], ...]]]:
    no_dinheiro = expiry.at_the_money(OptionType.PUT)
    if no_dinheiro is None:
        return []
    piso = settings.protection_floor * expiry.market.spot
    puts = [p for p in expiry.puts if piso <= p.strike <= no_dinheiro.strike]
    calls = expiry.in_delta_range(OptionType.CALL, settings)
    candidatas: list[tuple[str, tuple[tuple[ScannedSeries, Side, int], ...]]] = []
    for put in puts:
        candidatas.append(("put_protetora", ((put, Side.BUY, lote),)))
        candidatas += [
            ("collar", ((put, Side.BUY, lote), (call, Side.SELL, lote)))
            for call in calls
            if call.strike > put.strike
        ]
    return candidatas


def _precificar(
    expiry: ScannedExpiry,
    settings: BookSettings,
    exclusions: list[BookExclusion],
    pedido: Sequence[tuple[ScannedSeries, Side, int]],
) -> list[PricedLeg] | None:
    precificadas = []
    for serie, lado, quantidade in pedido:
        perna = price_leg(expiry, serie, lado, quantidade)
        if isinstance(perna, str):
            exclusions.append(BookExclusion("/".join(s.symbol for s, _, _ in pedido), perna))
            return None
        precificadas.append(perna)
    return precificadas if keeps_liquidity(precificadas, settings) else None


def _item(
    chain: OptionChain,
    position: ProtectedPosition,
    schedule: CostSchedule,
    expiry: ScannedExpiry,
    chave: str,
    pernas: list[PricedLeg],
    lote: int,
) -> BookItem:
    spot = chain.underlying.spot
    preco = position.average_price if position.average_price is not None else spot
    resultado = evaluate(
        chave,
        pernas,
        chain,
        expiry,
        schedule,
        stock=StockLeg(position.underlying, Side.BUY, lote, preco),
        stock_already_held=True,
    )
    caixa_opcoes = fsum(
        leg.premium.premium * leg.quantity * (1.0 if leg.side is Side.SELL else -1.0)
        for leg in pernas
    )
    custo = resultado.setup_costs - caixa_opcoes
    valor = spot * lote
    put = pernas[0].series
    apoio = [
        Metric("custo", "custo líquido da proteção", custo, MetricUnit.CURRENCY),
        Metric("custo_pct", "custo em % da posição", custo / valor, MetricUnit.PERCENT),
        Metric("piso", "piso por ação", put.strike, MetricUnit.CURRENCY),
        Metric("piso_pct", "piso em % do spot", put.strike / spot, MetricUnit.PERCENT),
        Metric("dias_uteis", "dias úteis", float(expiry.business_days), MetricUnit.BUSINESS_DAYS),
    ]
    if position.hypothetical:
        posicao = f"{lote} ações hipotéticas"
    else:
        posicao = f"As {lote} ações da carteira"
    if chave == "collar":
        call = pernas[1].series
        apoio += [
            Metric("teto", "teto por ação", call.strike, MetricUnit.CURRENCY),
            Metric("teto_pct", "teto em % do spot", call.strike / spot, MetricUnit.PERCENT),
        ]
        frase = (
            f"{posicao}: o collar {put.symbol}/{call.symbol} trava o piso em {{piso}} "
            "({piso_pct} do spot) e o teto em {teto} ({teto_pct}), com custo líquido de {custo} "
            "({custo_pct} da posição), o equivalente a {custo_mensal} ao mês."
        )
    else:
        frase = (
            f"{posicao}: a put {put.symbol} garante o piso de {{piso}} ({{piso_pct}} do spot) "
            "por {custo} ({custo_pct} da posição), o equivalente a {custo_mensal} ao mês."
        )
    origem = StockOrigin.COMPRA if position.hypothetical else StockOrigin.CARTEIRA
    rotulos = (BookLabel.POSICAO_HIPOTETICA,) if position.hypothetical else ()
    return BookItem(
        family=Family.PROTECAO,
        template_key=chave,
        underlying=position.underlying,
        expiry=expiry.expiry,
        business_days=expiry.business_days,
        legs=book_legs(pernas),
        stock=BookStock(Side.BUY, lote, origem),
        criterion=Metric(
            "custo_mensal",
            "custo mensal equivalente",
            custo / valor * _DU_MES / expiry.business_days,
            MetricUnit.PERCENT,
        ),
        metrics=tuple(apoio),
        reason=frase,
        labels=(*rotulos, *approximation_labels(pernas)),
    )

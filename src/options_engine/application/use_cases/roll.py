"""``RollService``: a sugestão de rolagem de uma operação aberta com opção vendida.

O Montador não aceita dois vencimentos numa estrutura (decisão nº 6), então a rolagem são duas
coisas: a mesma estrutura no vencimento seguinte, pelo modelo de onde a operação veio, e o caixa de
zerar as pernas de opção abertas, pelo preço de zerar da Carteira. Nada é enviado nem gravado.
"""

from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, tzinfo
from math import fsum

from options_engine.application.ports.alerts import RollSuggestion
from options_engine.application.ports.inbound import BuilderRequest
from options_engine.application.ports.outbound import Clock, MarketPort
from options_engine.application.ports.portfolio import OperationView, PortfolioView
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError, UnknownRecordError
from options_engine.domain.model.expiries import is_weekly_series, list_expiries
from options_engine.domain.model.templates import TEMPLATES
from options_engine.domain.portfolio.model import LegState, OptionLegRef, StockLegRef

__all__ = ["RollService"]

_MODELOS = frozenset(modelo.key for modelo in TEMPLATES)


class RollService:
    """``open_operations``: a Carteira marcada (o preço de zerar); ``suggest``: o
    ``StrategyBuilderService.suggest`` (ativo, modelo, vencimento)."""

    def __init__(
        self,
        open_operations: Callable[[], PortfolioView],
        suggest: Callable[[str, str, date], BuilderRequest],
        clock: Clock,
        market_timezone: tzinfo,
        *,
        market: MarketPort,
    ) -> None:
        self._open_operations = open_operations
        self._suggest = suggest
        self._clock = clock
        self._tz = market_timezone
        self._market = market

    def roll(self, operation_id: str) -> RollSuggestion:
        carteira = self._open_operations()
        view = next((o for o in carteira.operations if o.operation.id == operation_id), None)
        if view is None:
            raise UnknownRecordError(f"operação aberta desconhecida: {operation_id!r}")
        operacao = view.operation
        vendidas = [e for e in view.legs if isinstance(e.ref, OptionLegRef) and e.side is Side.SELL]
        if not vendidas:
            raise InvalidDomainValueError(
                f"{operacao.name!r} não tem opção vendida aberta para rolar"
            )
        atual = min(vendidas, key=_vencimento)
        seguinte = self._vencimento_seguinte(operacao.underlying, atual)
        pedido = None
        if seguinte is not None and operacao.template in _MODELOS:
            assert operacao.template is not None
            sugerido = self._suggest(operacao.underlying, operacao.template, seguinte)
            pedido = _na_escala(sugerido, view.legs)
        return RollSuggestion(
            operacao.id,
            operacao.name,
            operacao.underlying,
            _vencimento(atual),
            seguinte,
            pedido,
            _caixa_de_zerar(view),
            carteira.source,
        )

    def _vencimento_seguinte(self, ativo: str, perna: LegState) -> date | None:
        """Mensal vai ao próximo mensal; semanal, ao próximo vencimento qualquer."""
        hoje = self._clock.now().astimezone(self._tz).date()
        cadeia = self._market.get_chain(ativo)
        listados = list_expiries(
            ((q.contract.symbol, q.contract.terms.expiry) for q in cadeia.quotes), hoje
        )
        semanal = is_weekly_series(perna.ref.symbol)
        atual = _vencimento(perna)
        return next(
            (v.expiry for v in listados if v.expiry > atual and (semanal or not v.weekly)), None
        )


def _vencimento(perna: LegState) -> date:
    assert isinstance(perna.ref, OptionLegRef)
    return perna.ref.terms.expiry


def _na_escala(sugerido: BuilderRequest, pernas: Sequence[LegState]) -> BuilderRequest:
    """O modelo sugere 100 vezes a razão de cada perna; a rolagem segue o tamanho da operação.
    A ação do modelo, se a operação já tem ação aberta, vem da carteira (não se compra de novo)."""
    abertas = sum(
        e.quantity for e in pernas if isinstance(e.ref, OptionLegRef) and e.side is not None
    )
    sugeridas = sum(p.quantity for p in sugerido.legs)
    fator = max(1, round(abertas / sugeridas)) if sugeridas else 1
    acao = sugerido.stock
    if acao is not None:
        tem_acao = any(isinstance(e.ref, StockLegRef) and e.side is Side.BUY for e in pernas)
        acao = replace(
            acao,
            quantity=acao.quantity * fator,
            origin=StockOrigin.CARTEIRA if tem_acao else acao.origin,
        )
    return replace(
        sugerido,
        legs=tuple(replace(p, quantity=p.quantity * fator) for p in sugerido.legs),
        stock=acao,
    )


def _caixa_de_zerar(view: OperationView) -> float | None:
    """Zerar a comprada recebe o bid; zerar a vendida paga o ask (as marcas da Carteira)."""
    valores: list[float] = []
    for estado, marca in zip(view.legs, view.marks or (None,) * len(view.legs), strict=True):
        if not isinstance(estado.ref, OptionLegRef) or estado.side is None:
            continue
        if marca is None or marca.price is None:
            return None
        sinal = 1.0 if estado.side is Side.BUY else -1.0
        valores.append(sinal * marca.price * estado.quantity)
    return fsum(valores)

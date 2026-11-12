"""``PortfolioService``: a carteira na pasta do perfil aberto, recalculada a partir dos eventos."""

import threading
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import date, datetime, time, timedelta, tzinfo
from math import fsum

from options_engine.application.ports.outbound import (
    Clock,
    MarketPort,
    OperationRepository,
    TradingCalendar,
    UnreadableFile,
)
from options_engine.application.ports.portfolio import (
    AssetView,
    ExpiryNotice,
    OperationView,
    PortfolioSymbols,
    PortfolioView,
    RegisterOperation,
    TaxMonthView,
)
from options_engine.application.use_cases._marks import Marker
from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.exercise import apply_exercise, takes_portfolio_shares
from options_engine.domain.portfolio.expiry import ExpiryOutcome, expiry_outcome
from options_engine.domain.portfolio.income_tax import monthly_tax, tax_records
from options_engine.domain.portfolio.model import (
    Close,
    Event,
    Expired,
    LegRef,
    Open,
    Operation,
    OptionLegRef,
    StockLegRef,
    TransferOut,
)
from options_engine.domain.portfolio.positions import (
    consolidate,
    free_shares,
    is_closed,
    leg_states,
    open_legs,
    realized_result,
)

__all__ = ["PortfolioService"]

_FIM_DO_PREGAO = time(18, 0)
_ACOES_A_MAO = "ações à mão"
_UM_DIA = timedelta(days=1)


class PortfolioService:
    """``repository_for`` é chamado a cada operação: o perfil aberto pode ter mudado.
    ``market_timezone``: o fuso da B3, para saber se o pregão do vencimento já acabou.
    ``market`` e ``calendar``: os preços de zerar e o teórico das posições abertas."""

    def __init__(
        self,
        repository_for: Callable[[], OperationRepository],
        clock: Clock,
        schedules: Sequence[CostSchedule],
        new_id: Callable[[], str],
        market_timezone: tzinfo,
        *,
        market: MarketPort,
        calendar: TradingCalendar,
    ) -> None:
        self._repository_for = repository_for
        self._clock = clock
        self._schedules = tuple(schedules)
        self._new_id = new_id
        self._tz = market_timezone
        self._market = market
        self._calendar = calendar
        # Toda gravação lê, muda e regrava: o WebSocket (pó) e a API não podem se atropelar.
        self._lock = threading.Lock()

    def register(self, command: RegisterOperation) -> Operation:
        with self._lock:
            return self._registrar(command)

    def _registrar(self, command: RegisterOperation) -> Operation:
        pernas: list[LegRef] = []
        eventos: list[Event] = []
        for perna in command.legs:
            if not perna.fills:
                raise InvalidDomainValueError(f"perna {perna.symbol!r} sem execução")
            indice = len(pernas)
            pernas.append(OptionLegRef(perna.symbol, perna.terms))
            eventos.extend(
                Open(indice, command.on, perna.side, f.quantity, f.price, f.costs)
                for f in perna.fills
            )
        acao = command.stock
        if acao is not None:
            if acao.origin is StockOrigin.CARTEIRA and (acao.side is not Side.BUY or acao.fills):
                raise InvalidDomainValueError(
                    "a ação da carteira já está no perfil: comprada e sem execução"
                )
            if acao.origin is StockOrigin.COMPRA and not acao.fills:
                raise InvalidDomainValueError(f"ação {command.underlying!r} sem execução")
            indice = len(pernas)
            pernas.append(StockLegRef(command.underlying, acao.origin))
            eventos.extend(
                Open(indice, command.on, acao.side, f.quantity, f.price, f.costs)
                for f in acao.fills
            )
        operacao = Operation(
            self._new_id(),
            command.underlying,
            command.name.strip(),
            command.on,
            tuple(pernas),
            tuple(eventos),
            command.template,
            command.stop_loss,
            command.target,
        )
        repositorio = self._repository_for()
        if acao is not None and acao.origin is StockOrigin.CARTEIRA:
            _exige_acoes_livres(_operacoes(repositorio.list()), operacao)
        repositorio.save(operacao)
        return operacao

    def add_stock(self, symbol: str, quantity: int, average_price: float, on: date) -> Operation:
        # A compra é anterior ao app: o preço médio informado já é o custo, sem estimar outro.
        operacao = Operation(
            self._new_id(),
            symbol,
            _ACOES_A_MAO,
            on,
            (StockLegRef(symbol, StockOrigin.COMPRA),),
            (Open(0, on, Side.BUY, quantity, average_price, costs=0.0),),
        )
        with self._lock:
            self._repository_for().save(operacao)
        return operacao

    def close(
        self,
        operation_id: str,
        leg: int,
        quantity: int,
        price: float,
        on: date,
        costs: float | None = None,
    ) -> Operation:
        with self._lock:
            repositorio = self._repository_for()
            operacao = repositorio.load(operation_id).with_events(
                Close(leg, on, quantity, price, costs)
            )
            repositorio.save(operacao)
        return operacao

    def exercise(
        self, operation_id: str, leg: int, quantity: int, on: date, costs: float | None = None
    ) -> Operation:
        with self._lock:
            return self._exercer(operation_id, leg, quantity, on, costs, Side.BUY)

    def assign(
        self, operation_id: str, leg: int, quantity: int, on: date, costs: float | None = None
    ) -> Operation:
        with self._lock:
            return self._exercer(operation_id, leg, quantity, on, costs, Side.SELL)

    def set_limits(
        self, operation_id: str, stop_loss: float | None, target: float | None
    ) -> Operation:
        with self._lock:
            repositorio = self._repository_for()
            operacao = replace(repositorio.load(operation_id), stop_loss=stop_loss, target=target)
            repositorio.save(operacao)
        return operacao

    def open_operations(self) -> PortfolioView:
        itens = self._repository_for().list()
        abertas = [o for o in _operacoes(itens) if not is_closed(o)]
        refs = {e.ref.symbol: e.ref for o in abertas for e in open_legs(o)}
        marcador = Marker(self._market, self._calendar, self._tz, tuple(refs.values()))
        return PortfolioView(
            operations=tuple(self._visao_aberta(o, marcador) for o in _recentes(abertas)),
            totals=tuple(
                AssetView(t, marcador.mark(refs[t.symbol], t.side, t.quantity, t.average_price))
                for t in consolidate(abertas)
            ),
            unreadable=tuple(i for i in itens if isinstance(i, UnreadableFile)),
            source=marcador.source,
            symbols=PortfolioSymbols(
                underlyings=tuple(sorted({o.underlying for o in abertas if open_legs(o)})),
                series=tuple(sorted(s for s, r in refs.items() if isinstance(r, OptionLegRef))),
            ),
        )

    def history(self) -> tuple[OperationView, ...]:
        encerradas = [o for o in _operacoes(self._repository_for().list()) if is_closed(o)]
        return tuple(self._visao(o) for o in _recentes(encerradas))

    def income_tax(self) -> tuple[TaxMonthView, ...]:
        registros = tax_records(_operacoes(self._repository_for().list()), self._schedules)
        return tuple(
            TaxMonthView(m, self._pagar_ate(m.month) if m.due > 0 else None)
            for m in monthly_tax(registros)
        )

    def average_price(self, symbol: str) -> float | None:
        livres = _livres(_operacoes(self._repository_for().list()), symbol)
        total = sum(n for _, _, n, _ in livres)
        return fsum(media * n for _, _, n, media in livres) / total if total else None

    def process_expiries(
        self, closes: Callable[[str, date], float | None]
    ) -> tuple[ExpiryNotice, ...]:
        with self._lock:
            return self._vencer(closes)

    def _vencer(self, closes: Callable[[str, date], float | None]) -> tuple[ExpiryNotice, ...]:
        agora = self._clock.now().astimezone(self._tz)
        repositorio = self._repository_for()
        avisos: list[ExpiryNotice] = []
        for operacao in _operacoes(repositorio.list()):
            po: list[Event] = []
            for estado in open_legs(operacao):
                ref = estado.ref
                if not isinstance(ref, OptionLegRef) or not _encerrado(ref.terms.expiry, agora):
                    continue
                resultado = expiry_outcome(
                    ref.terms.option_type,
                    ref.terms.strike,
                    closes(operacao.underlying, ref.terms.expiry),
                )
                if resultado is ExpiryOutcome.PO:
                    po.append(Expired(estado.index, ref.terms.expiry))
                else:
                    avisos.append(
                        ExpiryNotice(
                            operacao.id, estado.index, ref.symbol, ref.terms.expiry, resultado
                        )
                    )
            if po:
                repositorio.save(operacao.with_events(*po))
        return tuple(avisos)

    def _pagar_ate(self, mes: date) -> date | None:
        """O último dia útil do mês seguinte a ``mes`` (dia 1); ``None`` fora do calendário."""
        ultimo = _primeiro_do_mes_seguinte(_primeiro_do_mes_seguinte(mes)) - _UM_DIA
        for i in range(ultimo.day):
            dia = ultimo - i * _UM_DIA
            try:
                if self._calendar.business_days_between(dia, dia + _UM_DIA) == 1:
                    return dia
            except InvalidDomainValueError:
                continue  # o dia sai da cobertura: segue para trás até achar um coberto
        return None

    def _visao(self, operacao: Operation) -> OperationView:
        return OperationView(
            operacao, leg_states(operacao), realized_result(operacao, self._schedules)
        )

    def _visao_aberta(self, operacao: Operation, marcador: Marker) -> OperationView:
        estados = leg_states(operacao)
        marcas = tuple(
            None if e.side is None else marcador.mark(e.ref, e.side, e.quantity, e.average_price)
            for e in estados
        )
        abertas = [m.unrealized for m in marcas if m is not None]
        return OperationView(
            operacao,
            estados,
            realized_result(operacao, self._schedules),
            marcas,
            None if None in abertas else fsum(a for a in abertas if a is not None),
        )

    def _exercer(
        self,
        operation_id: str,
        leg: int,
        quantity: int,
        on: date,
        costs: float | None,
        lado: Side,
    ) -> Operation:
        repositorio = self._repository_for()
        operacao = repositorio.load(operation_id)
        estados = leg_states(operacao)
        if not 0 <= leg < len(estados):
            raise InvalidDomainValueError(f"perna {leg} inexistente na operação")
        if estados[leg].side is not lado:
            nome = (
                "exercício só em perna comprada"
                if lado is Side.BUY
                else "atribuição só em perna vendida"
            )
            raise InvalidDomainValueError(f"{nome}; a perna {leg} não é")
        if not takes_portfolio_shares(operacao, leg, quantity):
            nova = apply_exercise(operacao, leg, quantity, on, costs=costs)
            repositorio.save(nova)
            return nova
        lotes = _lotes_livres(_operacoes(repositorio.list()), operacao, quantity)
        # O custo é o das ações que de fato saem: a soma dos resultados bate com o total real.
        custo = fsum(media * n for _, _, n, media in lotes) / quantity
        nova = apply_exercise(operacao, leg, quantity, on, costs=costs, portfolio_average=custo)
        fontes = [
            fonte.with_events(TransferOut(perna, on, n, operacao.id))
            for fonte, perna, n, _ in lotes
        ]
        # A operação antes das fontes: se a gravação parar no meio, repetir é recusado (a perna já
        # foi atribuída) em vez de tirar as ações duas vezes.
        repositorio.save(nova)
        for fonte in fontes:
            repositorio.save(fonte)
        return nova


def _operacoes(itens: Sequence[Operation | UnreadableFile]) -> list[Operation]:
    return [i for i in itens if isinstance(i, Operation)]


def _primeiro_do_mes_seguinte(dia: date) -> date:
    return (dia.replace(day=28) + timedelta(days=4)).replace(day=1)


def _recentes(operacoes: Sequence[Operation]) -> list[Operation]:
    return sorted(operacoes, key=lambda o: (o.created_on, o.id), reverse=True)


def _encerrado(vencimento: date, agora: datetime) -> bool:
    return agora.date() > vencimento or (
        agora.date() == vencimento and agora.time() >= _FIM_DO_PREGAO
    )


def _exige_acoes_livres(existentes: Sequence[Operation], operacao: Operation) -> None:
    cobertas = sum(
        e.quantity
        for e in leg_states(operacao)
        if isinstance(e.ref, OptionLegRef)
        and e.ref.terms.option_type is OptionType.CALL
        and e.side is Side.SELL
    )
    livres = free_shares(existentes, operacao.underlying)
    if cobertas > livres:
        raise InvalidDomainValueError(
            f"{operacao.underlying}: {livres} ações livres na carteira; a operação cobre {cobertas}"
        )


def _livres(
    operacoes: Sequence[Operation], simbolo: str, exceto: str | None = None
) -> list[tuple[Operation, int, int, float]]:
    """As ações livres por operação, em ordem de criação: ``(operação, perna, quantidade,
    preço médio)``. As que cobrem uma call vendida da própria operação ficam de fora."""
    livres: list[tuple[Operation, int, int, float]] = []
    for fonte in sorted(operacoes, key=lambda o: (o.created_on, o.id)):
        n = free_shares((fonte,), simbolo) if fonte.id != exceto else 0
        if n:
            acoes = next(
                e
                for e in leg_states(fonte)
                if isinstance(e.ref, StockLegRef)
                and e.ref.symbol == simbolo
                and e.ref.origin is StockOrigin.COMPRA
                and e.side is Side.BUY
            )
            livres.append((fonte, acoes.index, n, acoes.average_price))
    return livres


def _lotes_livres(
    operacoes: Sequence[Operation], destino: Operation, quantidade: int
) -> list[tuple[Operation, int, int, float]]:
    """De onde saem as ações "da carteira": ``(operação, perna, quantidade, preço médio)``.

    Na proporção das ações livres de cada operação (maiores restos, em ordem de criação no
    empate): o preço médio de cada uma não muda com a venda.
    """
    simbolo = destino.underlying
    livres = _livres(operacoes, simbolo, exceto=destino.id)
    total = sum(n for _, _, n, _ in livres)
    if total < quantidade:
        raise InvalidDomainValueError(
            f"{simbolo}: faltam {quantidade - total} ações livres na carteira para a atribuição"
        )
    cotas = [quantidade * n // total for _, _, n, _ in livres]
    restos = [quantidade * n % total for _, _, n, _ in livres]
    for i in sorted(range(len(livres)), key=lambda i: -restos[i])[: quantidade - sum(cotas)]:
        cotas[i] += 1
    return [
        (fonte, perna, c, media)
        for (fonte, perna, _, media), c in zip(livres, cotas, strict=True)
        if c
    ]

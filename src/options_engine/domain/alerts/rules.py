"""As regras: recebem a carteira marcada, o spot e os dias úteis, devolvem os alertas, sem I/O.

Vencimento próximo: perna de opção aberta a ``expiry_days`` dias úteis ou menos. Risco de
exercício: perna de opção vendida, na mesma janela, dentro do dinheiro ou a menos de
``strike_distance`` do strike. Stop e alvo: o resultado total da operação contra os limites em R$.
Depois do pregão do vencimento, a perna com aviso só tem o aviso.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import date

from options_engine.domain.alerts.model import (
    AfterExpiry,
    Alert,
    AlertKind,
    AlertSettings,
    Evaluation,
    OperationSnapshot,
)
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.model import LegState, OptionLegRef

__all__ = ["evaluate"]

_GRAVIDADE = {kind: i for i, kind in enumerate(AlertKind)}
_DO_AVISO = {
    ExpiryOutcome.REGISTRAR_EXERCICIO: AlertKind.EXERCISE_TO_REGISTER,
    ExpiryOutcome.AGUARDANDO_FECHAMENTO: AlertKind.AWAITING_CLOSE,
}


class _Coleta:
    """Os alertas com a posição da operação na entrada (desempate da ordem) e as indeterminadas."""

    def __init__(self) -> None:
        self.alertas: list[tuple[int, Alert]] = []
        self.indeterminadas: set[str] = set()

    def avaliacao(self) -> Evaluation:
        self.alertas.sort(key=lambda item: (_GRAVIDADE[item[1].kind], item[0], item[1].leg or 0))
        return Evaluation(tuple(a for _, a in self.alertas), frozenset(self.indeterminadas))


def _chave(kind: AlertKind, operation_id: str, leg: int | None) -> str:
    return f"{kind.value}:{operation_id}:{'-' if leg is None else leg}"


def _alerta(kind: AlertKind, op: OperationSnapshot, leg: int | None = None) -> Alert:
    return Alert(
        _chave(kind, op.operation_id, leg), kind, op.operation_id, op.name, op.underlying, leg
    )


def evaluate(
    operations: Sequence[OperationSnapshot],
    after_expiry: Sequence[AfterExpiry],
    spots: Mapping[str, float],
    business_days: Callable[[date], int | None],
    settings: AlertSettings,
) -> Evaluation:
    """``business_days(vencimento)``: dias úteis de hoje até o vencimento, ``None`` fora do
    calendário. ``spots``: por ativo; ausente, o risco de exercício fica indeterminado."""
    coleta = _Coleta()
    posicoes = {op.operation_id: i for i, op in enumerate(operations)}
    avisadas = _avisos(coleta, operations, posicoes, after_expiry)
    for posicao, op in enumerate(operations):
        rolar = any(isinstance(e.ref, OptionLegRef) and e.side is Side.SELL for e in op.legs)
        for estado in op.legs:
            if (op.operation_id, estado.index) not in avisadas:
                _perna(coleta, posicao, op, estado, rolar, spots, business_days, settings)
        _stop_e_alvo(coleta, posicao, op)
    return coleta.avaliacao()


def _avisos(
    coleta: _Coleta,
    operations: Sequence[OperationSnapshot],
    posicoes: Mapping[str, int],
    after_expiry: Sequence[AfterExpiry],
) -> set[tuple[str, int]]:
    avisadas: set[tuple[str, int]] = set()
    for aviso in after_expiry:
        posicao = posicoes.get(aviso.operation_id)
        if posicao is None:
            raise InvalidDomainValueError(
                f"aviso de vencimento de operação que não está aberta: {aviso.operation_id!r}"
            )
        avisadas.add((aviso.operation_id, aviso.leg))
        alerta = _alerta(_DO_AVISO[aviso.outcome], operations[posicao], aviso.leg)
        coleta.alertas.append((posicao, replace(alerta, symbol=aviso.symbol, expiry=aviso.expiry)))
    return avisadas


def _perna(
    coleta: _Coleta,
    posicao: int,
    op: OperationSnapshot,
    estado: LegState,
    rolar: bool,
    spots: Mapping[str, float],
    business_days: Callable[[date], int | None],
    settings: AlertSettings,
) -> None:
    ref = estado.ref
    if not isinstance(ref, OptionLegRef) or estado.side is None:
        return
    vendida = estado.side is Side.SELL
    vencimento = _alerta(AlertKind.EXPIRY_NEAR, op, estado.index)
    risco = _alerta(AlertKind.EXERCISE_RISK, op, estado.index)
    du = business_days(ref.terms.expiry)
    if du is None:
        coleta.indeterminadas.update([vencimento.key, risco.key] if vendida else [vencimento.key])
        return
    if du > settings.expiry_days:
        return
    vencimento = replace(
        vencimento, symbol=ref.symbol, expiry=ref.terms.expiry, business_days=du, can_roll=rolar
    )
    coleta.alertas.append((posicao, vencimento))
    if not vendida:
        return
    spot = spots.get(op.underlying)
    if spot is None:
        coleta.indeterminadas.add(risco.key)
        return
    dentro = _no_dinheiro(ref, spot, settings.strike_distance)
    if dentro is not None:
        risco = replace(
            vencimento, key=risco.key, kind=AlertKind.EXERCISE_RISK, in_the_money=dentro
        )
        coleta.alertas.append((posicao, risco))


def _no_dinheiro(ref: OptionLegRef, spot: float, distancia: float) -> bool | None:
    """``True`` dentro do dinheiro, ``False`` perto do strike, ``None`` longe."""
    strike = ref.terms.strike
    if ref.terms.option_type.is_call:
        dentro, perto = spot > strike, spot >= strike * (1.0 - distancia)
    else:
        dentro, perto = spot < strike, spot <= strike * (1.0 + distancia)
    return True if dentro else (False if perto else None)


def _stop_e_alvo(coleta: _Coleta, posicao: int, op: OperationSnapshot) -> None:
    for kind, limite in ((AlertKind.STOP, op.stop_loss), (AlertKind.TARGET, op.target)):
        if limite is None:
            continue
        alerta = _alerta(kind, op)
        if op.total is None:
            coleta.indeterminadas.add(alerta.key)
            continue
        disparou = op.total <= -limite if kind is AlertKind.STOP else op.total >= limite
        if disparou:
            coleta.alertas.append((posicao, replace(alerta, total=op.total, limit=limite)))

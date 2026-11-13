"""Regras dos alertas: vencimento próximo, risco de exercício, stop, alvo e avisos de vencimento."""

from collections.abc import Sequence

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.alerts.model import (
    AfterExpiry,
    AlertKind,
    AlertSettings,
    Evaluation,
    OperationSnapshot,
)
from options_engine.domain.alerts.rules import evaluate
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.model import LegRef, LegState
from tests.portfolio._builders import NOVEMBRO, acao, call, put

PADRAO = AlertSettings()


def perna(i: int, ref: LegRef, lado: Side | None, quantidade: int = 100) -> LegState:
    return LegState(i, ref, lado, quantidade if lado is not None else 0, 1.0, 0.0)


def foto(
    *legs: LegState,
    id_: str = "op1",
    total: float | None = 0.0,
    stop: float | None = None,
    alvo: float | None = None,
    estimado: float | None = None,
    sem_preco: bool = False,
) -> OperationSnapshot:
    return OperationSnapshot(
        id_, f"operação {id_}", "PETR4", legs, total, stop, alvo, estimado, sem_preco
    )


def avaliar(
    operacoes: Sequence[OperationSnapshot],
    *,
    spot: float | None = 25.0,
    du: int | None = 3,
    avisos: Sequence[AfterExpiry] = (),
    limites: AlertSettings = PADRAO,
) -> Evaluation:
    spots = {} if spot is None else {"PETR4": spot}
    return evaluate(operacoes, avisos, spots, lambda _vencimento: du, limites)


def tipos(resultado: Evaluation) -> list[tuple[AlertKind, int | None]]:
    return [(a.kind, a.leg) for a in resultado.alerts]


def test_vencimento_a_5_du_dispara_e_a_6_nao() -> None:
    op = foto(perna(0, call(30.0), Side.BUY))
    assert tipos(avaliar([op], du=5)) == [(AlertKind.EXPIRY_NEAR, 0)]
    assert avaliar([op], du=6).alerts == ()


def test_no_dia_do_vencimento_0_du_dispara() -> None:
    alerta = avaliar([foto(perna(0, call(30.0), Side.BUY))], du=0).alerts[0]
    assert (alerta.kind, alerta.business_days, alerta.expiry) == (
        AlertKind.EXPIRY_NEAR,
        0,
        NOVEMBRO,
    )


def test_perna_fechada_e_acao_nao_tem_vencimento() -> None:
    op = foto(perna(0, call(30.0), None), perna(1, acao(), Side.BUY))
    assert avaliar([op]).alerts == ()


def test_call_vendida_dentro_do_dinheiro() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.SELL))], spot=30.10)
    risco = next(a for a in r.alerts if a.kind is AlertKind.EXERCISE_RISK)
    assert risco.in_the_money is True
    assert risco.can_roll is True


def test_call_vendida_a_menos_de_2_por_cento() -> None:
    op = foto(perna(0, call(30.0), Side.SELL))
    risco = [a for a in avaliar([op], spot=29.41).alerts if a.kind is AlertKind.EXERCISE_RISK]
    assert [a.in_the_money for a in risco] == [False]
    assert not [a for a in avaliar([op], spot=29.39).alerts if a.kind is AlertKind.EXERCISE_RISK]


def test_put_vendida_a_menos_de_2_por_cento() -> None:
    op = foto(perna(0, put(30.0), Side.SELL))
    perto = [a for a in avaliar([op], spot=30.50).alerts if a.kind is AlertKind.EXERCISE_RISK]
    assert [a.in_the_money for a in perto] == [False]
    longe = [a for a in avaliar([op], spot=30.70).alerts if a.kind is AlertKind.EXERCISE_RISK]
    assert longe == []
    dentro = [a for a in avaliar([op], spot=29.0).alerts if a.kind is AlertKind.EXERCISE_RISK]
    assert [a.in_the_money for a in dentro] == [True]


def test_call_comprada_nao_tem_risco_de_exercicio() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.BUY))], spot=35.0)
    assert tipos(r) == [(AlertKind.EXPIRY_NEAR, 0)]
    assert r.alerts[0].can_roll is False


def test_vendida_dentro_do_dinheiro_avisa_fora_da_janela() -> None:
    # Put vendida strike 30 com o ativo a 26, a 10 dias úteis: avisa, sem o vencimento próximo.
    r = avaliar([foto(perna(0, put(30.0), Side.SELL))], spot=26.0, du=10)
    assert tipos(r) == [(AlertKind.EXERCISE_RISK, 0)]
    (risco,) = r.alerts
    assert (risco.in_the_money, risco.business_days, risco.expiry, risco.can_roll) == (
        True,
        10,
        NOVEMBRO,
        True,
    )
    assert risco.key == "risco_de_exercicio:op1:0"


def test_perto_do_strike_fora_da_janela_nao_dispara() -> None:
    op = foto(perna(0, call(30.0), Side.SELL))
    assert avaliar([op], spot=29.5, du=6).alerts == ()


def test_fora_da_janela_sem_spot_risco_indeterminado() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.SELL))], spot=None, du=10)
    assert (r.alerts, r.undetermined) == ((), frozenset({"risco_de_exercicio:op1:0"}))


def test_comprada_dentro_do_dinheiro_fora_da_janela_nao_avisa() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.BUY))], spot=35.0, du=10)
    assert (r.alerts, r.undetermined) == ((), frozenset())


def test_limites_do_perfil_valem() -> None:
    op = foto(perna(0, call(30.0), Side.SELL))
    limites = AlertSettings(expiry_days=10, strike_distance=0.05)
    r = avaliar([op], spot=28.60, du=8, limites=limites)
    assert tipos(r) == [(AlertKind.EXERCISE_RISK, 0), (AlertKind.EXPIRY_NEAR, 0)]


def test_stop_dispara_no_limite_exato() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.BUY), total=-200.0, stop=200.0)], du=30)
    assert [(a.kind, a.total, a.limit) for a in r.alerts] == [(AlertKind.STOP, -200.0, 200.0)]
    assert avaliar([foto(total=-199.99, stop=200.0)], du=30).alerts == ()


def test_alvo_dispara() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.BUY), total=150.0, alvo=150.0)], du=30)
    assert [(a.kind, a.leg, a.key) for a in r.alerts] == [(AlertKind.TARGET, None, "alvo:op1:-")]


def test_stop_em_operacao_so_de_acoes() -> None:
    r = avaliar([foto(perna(0, acao(), Side.BUY), total=-500.0, stop=300.0)])
    assert tipos(r) == [(AlertKind.STOP, None)]


def test_sem_preco_de_zerar_stop_indeterminado() -> None:
    r = avaliar([foto(perna(0, acao(), Side.BUY), total=None, stop=300.0, alvo=100.0)])
    assert r.alerts == ()
    assert r.undetermined == {"stop:op1:-", "alvo:op1:-"}


def test_stop_pelo_total_estimado() -> None:
    op = foto(perna(0, call(30.0), Side.BUY), total=None, estimado=-60.0, stop=50.0)
    r = avaliar([op], du=30)
    assert [(a.kind, a.total, a.limit, a.estimated) for a in r.alerts] == [
        (AlertKind.STOP, -60.0, 50.0, True)
    ]
    assert (r.estimated, r.undetermined) == (frozenset({"stop:op1:-"}), frozenset())


def test_estimado_aquem_do_stop_nao_dispara_e_conta_como_estimado() -> None:
    op = foto(perna(0, call(30.0), Side.BUY), total=None, estimado=-40.0, stop=50.0)
    r = avaliar([op], du=30)
    assert r.alerts == ()
    assert r.estimated == {"stop:op1:-"}


def test_alvo_fica_indeterminado_com_o_total_estimado() -> None:
    op = foto(perna(0, call(30.0), Side.BUY), total=None, estimado=40.0, stop=50.0, alvo=30.0)
    r = avaliar([op], du=30)
    assert r.alerts == ()
    assert (r.estimated, r.undetermined) == (frozenset({"stop:op1:-"}), frozenset({"alvo:op1:-"}))


def test_sem_preco_para_avaliar_avisa_e_o_stop_fica_indeterminado() -> None:
    op = foto(perna(0, put(28.0), Side.BUY), total=None, sem_preco=True, stop=50.0, alvo=30.0)
    r = avaliar([op], du=30)
    assert [(a.kind, a.key, a.limit, a.total) for a in r.alerts] == [
        (AlertKind.STOP_UNPRICED, "stop_sem_preco:op1:-", 50.0, None)
    ]
    assert r.undetermined == {"stop:op1:-", "alvo:op1:-"}


def test_sem_preco_sem_stop_nao_avisa() -> None:
    op = foto(perna(0, put(28.0), Side.BUY), total=None, sem_preco=True, alvo=30.0)
    assert avaliar([op], du=30).alerts == ()


def test_total_executavel_prevalece_sobre_o_estimado() -> None:
    op = foto(perna(0, call(30.0), Side.BUY), total=-10.0, estimado=-60.0, stop=50.0)
    r = avaliar([op], du=30)
    assert (r.alerts, r.estimated) == ((), frozenset())


def test_sem_stop_nada_indeterminado() -> None:
    assert avaliar([foto(perna(0, acao(), Side.BUY), total=None)]).undetermined == frozenset()


def test_sem_spot_risco_indeterminado() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.SELL))], spot=None)
    assert tipos(r) == [(AlertKind.EXPIRY_NEAR, 0)]
    assert r.undetermined == {"risco_de_exercicio:op1:0"}


def test_fora_do_calendario_indeterminado() -> None:
    r = avaliar([foto(perna(0, call(30.0), Side.SELL))], du=None)
    assert r.alerts == ()
    assert r.undetermined == {"vencimento_proximo:op1:0", "risco_de_exercicio:op1:0"}


def test_avisos_de_vencimento_viram_alertas() -> None:
    op = foto(perna(0, call(30.0), Side.SELL), perna(1, put(28.0), Side.BUY))
    avisos = [
        AfterExpiry("op1", 0, "PETRK300", NOVEMBRO, ExpiryOutcome.REGISTRAR_EXERCICIO),
        AfterExpiry("op1", 1, "PETRW280", NOVEMBRO, ExpiryOutcome.AGUARDANDO_FECHAMENTO),
    ]
    r = avaliar([op], spot=35.0, du=0, avisos=avisos)
    # Depois do pregão do vencimento só o aviso fala: sem vencimento próximo nem risco repetidos.
    assert tipos(r) == [(AlertKind.EXERCISE_TO_REGISTER, 0), (AlertKind.AWAITING_CLOSE, 1)]
    assert r.alerts[0].symbol == "PETRK300"


def test_aviso_de_operacao_desconhecida_recusado() -> None:
    aviso = AfterExpiry("outra", 0, "PETRK300", NOVEMBRO, ExpiryOutcome.REGISTRAR_EXERCICIO)
    with pytest.raises(InvalidDomainValueError, match="outra"):
        avaliar([foto(perna(0, call(30.0), Side.SELL))], avisos=[aviso])


def test_ordem_por_gravidade() -> None:
    a = foto(perna(0, call(30.0), Side.BUY), id_="a", total=500.0, alvo=100.0)
    b = foto(perna(0, call(30.0), Side.SELL), id_="b", total=-900.0, stop=100.0)
    r = avaliar([a, b], spot=31.0)
    assert [(x.kind, x.operation_id) for x in r.alerts] == [
        (AlertKind.STOP, "b"),
        (AlertKind.EXERCISE_RISK, "b"),
        (AlertKind.EXPIRY_NEAR, "a"),
        (AlertKind.EXPIRY_NEAR, "b"),
        (AlertKind.TARGET, "a"),
    ]


@pytest.mark.parametrize(
    ("dias", "distancia"),
    [(-1, 0.02), (61, 0.02), (5, -0.01), (5, 0.21), (5, float("nan")), (True, 0.02)],
)
def test_limites_invalidos_recusados(dias: int, distancia: float) -> None:
    with pytest.raises(InvalidDomainValueError):
        AlertSettings(dias, distancia)


def test_stop_e_alvo_do_retrato_positivos() -> None:
    with pytest.raises(InvalidDomainValueError):
        foto(stop=0.0)
    with pytest.raises(InvalidDomainValueError):
        foto(alvo=float("inf"))


_LADOS = st.sampled_from([Side.BUY, Side.SELL, None])


@given(
    lados=st.lists(st.tuples(_LADOS, _LADOS), min_size=1, max_size=4),
    spot=st.one_of(st.none(), st.floats(20.0, 40.0)),
    du=st.one_of(st.none(), st.integers(0, 10)),
    total=st.one_of(st.none(), st.floats(-1000.0, 1000.0)),
)
def test_chaves_unicas(
    lados: list[tuple[Side | None, Side | None]],
    spot: float | None,
    du: int | None,
    total: float | None,
) -> None:
    operacoes = [
        foto(
            perna(0, call(30.0), c),
            perna(1, put(28.0), p),
            id_=f"op{i}",
            total=total,
            stop=100.0,
            alvo=100.0,
        )
        for i, (c, p) in enumerate(lados)
    ]
    r = avaliar(operacoes, spot=spot, du=du)
    chaves = [a.key for a in r.alerts]
    assert len(chaves) == len(set(chaves))
    assert not set(chaves) & r.undetermined

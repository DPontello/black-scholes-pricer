"""``AlertService``: a carteira marcada, o spot, o calendário, os limites e os dispensados."""

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from options_engine.application.ports.alerts import AlertsView, AlertUseCase
from options_engine.application.ports.portfolio import (
    ExpiryNotice,
    LegMark,
    OperationView,
    PortfolioSymbols,
    PortfolioView,
)
from options_engine.application.use_cases.alerts import AlertService
from options_engine.domain.alerts.model import AlertKind, AlertSettings
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import NoActiveProfileError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.model import Open, Operation
from options_engine.domain.portfolio.positions import leg_states
from tests.application._mercado_falso import CALENDARIO, MercadoFalso
from tests.portfolio._builders import D1, NOVEMBRO, acao, call, operacao

B3 = timezone(timedelta(hours=-3))
PADRAO = AlertSettings()
# 17/11: dois dias úteis até o vencimento de 19/11 (17 e 18).
DIA_17 = datetime(2026, 11, 17, 14, 0, tzinfo=B3)


@dataclass
class _Relogio:
    agora: datetime = DIA_17

    def now(self) -> datetime:
        return self.agora


@dataclass
class _Dispensados:
    chaves: frozenset[str] = frozenset()
    gravacoes: list[frozenset[str]] = field(default_factory=list)

    def load(self) -> frozenset[str]:
        return self.chaves

    def save(self, keys: frozenset[str]) -> None:
        self.chaves = keys
        self.gravacoes.append(keys)


def _cotacao(last: float | None, anterior: float | None = None) -> UnderlyingQuote:
    return UnderlyingQuote("PETR4", last, None, None, anterior, 0, 0.0, DIA_17, DataSource.AO_VIVO)


def _servico(
    dispensados: _Dispensados | None = None,
    *,
    mercado: MercadoFalso | None = None,
    limites: AlertSettings = PADRAO,
    relogio: _Relogio | None = None,
) -> AlertService:
    caixa = _Dispensados() if dispensados is None else dispensados
    return AlertService(
        lambda: caixa,
        lambda: limites,
        relogio or _Relogio(),
        B3,
        market=MercadoFalso() if mercado is None else mercado,
        calendar=CALENDARIO,
    )


def _visao(
    operacao_: Operation,
    *,
    realizado: float = 0.0,
    aberto: float | None = 0.0,
) -> OperationView:
    """``aberto=None``: as pernas abertas sem cotação (o Tryd piscando)."""
    estados = leg_states(operacao_)
    marca = (
        LegMark(1.0, aberto)
        if aberto is not None
        else LegMark(None, None, reason="aguardando dados", quoted=False)
    )
    marcas = tuple(None if e.side is None else marca for e in estados)
    return OperationView(operacao_, estados, realizado, marcas, aberto)


def _sem_oferta(
    operacao_: Operation,
    *,
    estimado: float | None,
    teorico: float | None = 0.40,
    realizado: float = 0.0,
) -> OperationView:
    """As pernas abertas cotadas, mas sem o lado de zerar; ``estimado``: o não realizado pelo
    teórico, como a marcação da Carteira o calcula."""
    estados = leg_states(operacao_)
    marca = LegMark(
        None, None, teorico, "sem oferta de compra para zerar", estimated_unrealized=estimado
    )
    marcas = tuple(None if e.side is None else marca for e in estados)
    return OperationView(operacao_, estados, realizado, marcas, None)


def _da_operacao(avaliacao: AlertsView) -> list[tuple[AlertKind, float | None, float | None, bool]]:
    """Os alertas da operação inteira (stop, alvo, stop sem preço), sem os das pernas."""
    return [(a.kind, a.total, a.limit, a.estimated) for a in avaliacao.alerts if a.leg is None]


def _comprada_com_stop(stop: float = 50.0, alvo: float | None = None) -> Operation:
    """Call comprada a 1,00, 100 opções."""
    return replace(
        operacao([call(30.0)], [Open(0, D1, Side.BUY, 100, 1.0)], id_="comprada1"),
        stop_loss=stop,
        target=alvo,
    )


def _carteira(*visoes: OperationView, fonte: DataSource = DataSource.AO_VIVO) -> PortfolioView:
    return PortfolioView(visoes, (), (), fonte, PortfolioSymbols((), ()))


def _acoes_com_stop(stop: float = 200.0) -> Operation:
    return replace(
        operacao([acao()], [Open(0, D1, Side.BUY, 100, 30.0)], id_="acoes0001"),
        stop_loss=stop,
    )


def test_servico_cumpre_a_porta() -> None:
    assert isinstance(_servico(), AlertUseCase)


def test_total_soma_realizado_e_aberto() -> None:
    op = _acoes_com_stop()
    servico = _servico()
    assert servico.evaluate(_carteira(_visao(op, realizado=-150.0, aberto=-40.0)), ()).alerts == ()
    (alerta,) = servico.evaluate(_carteira(_visao(op, realizado=-150.0, aberto=-60.0)), ()).alerts
    assert (alerta.kind, alerta.total, alerta.limit) == (AlertKind.STOP, -210.0, 200.0)


def test_stop_dispensado_volta_depois_de_melhorar() -> None:
    op = _acoes_com_stop()
    caixa = _Dispensados()
    servico = _servico(caixa)
    (alerta,) = servico.evaluate(_carteira(_visao(op, aberto=-210.0)), ()).alerts
    servico.dismiss(alerta.key)

    escondido = servico.evaluate(_carteira(_visao(op, aberto=-215.0)), ())
    assert (escondido.alerts, escondido.dismissed) == ((), 1)

    melhorou = servico.evaluate(_carteira(_visao(op, aberto=-150.0)), ())
    assert (melhorou.alerts, melhorou.dismissed, caixa.chaves) == ((), 0, frozenset())

    voltou = servico.evaluate(_carteira(_visao(op, aberto=-205.0)), ())
    assert [a.kind for a in voltou.alerts] == [AlertKind.STOP]


def test_sem_preco_de_zerar_nao_limpa_o_dispensado() -> None:
    op = _acoes_com_stop()
    caixa = _Dispensados(frozenset({"stop:acoes0001:-"}))
    servico = _servico(caixa)
    piscou = servico.evaluate(_carteira(_visao(op, aberto=None)), ())
    assert (piscou.alerts, caixa.chaves) == ((), frozenset({"stop:acoes0001:-"}))
    assert servico.evaluate(_carteira(_visao(op, aberto=-300.0)), ()).dismissed == 1


def test_stop_estimado_dispara_com_comprada_sem_bid() -> None:
    op = _comprada_com_stop(stop=50.0)
    servico = _servico()
    # Realizado de -20 e -40 pelo teórico na comprada sem bid: -60, além do stop de 50.
    avaliacao = servico.evaluate(_carteira(_sem_oferta(op, estimado=-40.0, realizado=-20.0)), ())
    assert _da_operacao(avaliacao) == [(AlertKind.STOP, -60.0, 50.0, True)]
    assert [a.key for a in avaliacao.alerts if a.kind is AlertKind.STOP] == ["stop:comprada1:-"]
    longe = servico.evaluate(_carteira(_sem_oferta(op, estimado=-40.0)), ())
    assert _da_operacao(longe) == []


def test_sem_cotacao_stop_segue_indeterminado() -> None:
    op = _comprada_com_stop(stop=50.0)
    avaliacao = _servico().evaluate(_carteira(_visao(op, realizado=-500.0, aberto=None)), ())
    assert _da_operacao(avaliacao) == []


def test_sem_teorico_vira_aviso() -> None:
    op = _comprada_com_stop(stop=50.0)
    avaliacao = _servico().evaluate(_carteira(_sem_oferta(op, estimado=None, teorico=None)), ())
    assert _da_operacao(avaliacao) == [(AlertKind.STOP_UNPRICED, None, 50.0, False)]
    (aviso,) = [a for a in avaliacao.alerts if a.leg is None]
    assert aviso.key == "stop_sem_preco:comprada1:-"


def test_alvo_nao_usa_total_estimado() -> None:
    op = _comprada_com_stop(stop=50.0, alvo=30.0)
    # +40 pelo teórico passaria do alvo de 30, mas o alvo só vale pelo preço de zerar.
    avaliacao = _servico().evaluate(_carteira(_sem_oferta(op, estimado=40.0)), ())
    assert _da_operacao(avaliacao) == []


def test_dispensado_nao_volta_quando_o_bid_some() -> None:
    op = _comprada_com_stop(stop=50.0)
    caixa = _Dispensados()
    servico = _servico(caixa)
    (stop,) = [
        a for a in servico.evaluate(_carteira(_visao(op, aberto=-60.0)), ()).alerts if a.leg is None
    ]
    servico.dismiss(stop.key)

    # O bid some e o teórico ainda passa do stop: a mesma chave, segue escondido.
    sumiu = servico.evaluate(_carteira(_sem_oferta(op, estimado=-55.0)), ())
    assert (_da_operacao(sumiu), sumiu.dismissed) == ([], 1)

    # O teórico melhora: a estimativa não limpa o dispensado, como o Tryd piscando.
    servico.evaluate(_carteira(_sem_oferta(op, estimado=-30.0)), ())
    assert caixa.chaves == frozenset({"stop:comprada1:-"})

    # O bid volta, ainda além do stop: continua dispensado.
    voltou = servico.evaluate(_carteira(_visao(op, aberto=-60.0)), ())
    assert (_da_operacao(voltou), voltou.dismissed) == ([], 1)


def test_grava_so_quando_muda() -> None:
    op = _acoes_com_stop()
    caixa = _Dispensados(frozenset({"stop:acoes0001:-", "alvo:sumiu:-"}))
    servico = _servico(caixa)
    for _ in range(3):
        servico.evaluate(_carteira(_visao(op, aberto=-300.0)), ())
    assert caixa.gravacoes == [frozenset({"stop:acoes0001:-"})]


def test_spot_pelo_fechamento_anterior_sem_ultimo() -> None:
    vendida = operacao([call(30.0)], [Open(0, D1, Side.SELL, 100, 1.0)], id_="vendida01")
    mercado = MercadoFalso(quotes={"PETR4": _cotacao(None, anterior=31.0)})
    alertas = _servico(mercado=mercado).evaluate(_carteira(_visao(vendida)), ()).alerts
    assert [(a.kind, a.in_the_money, a.business_days) for a in alertas] == [
        (AlertKind.EXERCISE_RISK, True, 2),
        (AlertKind.EXPIRY_NEAR, None, 2),
    ]


def test_sem_cotacao_do_ativo_risco_indeterminado() -> None:
    vendida = operacao([call(30.0)], [Open(0, D1, Side.SELL, 100, 1.0)], id_="vendida01")
    caixa = _Dispensados(frozenset({"risco_de_exercicio:vendida01:0"}))
    alertas = _servico(caixa).evaluate(_carteira(_visao(vendida)), ()).alerts
    assert [a.kind for a in alertas] == [AlertKind.EXPIRY_NEAR]
    assert caixa.gravacoes == []


def test_limites_do_perfil_valem() -> None:
    comprada = operacao([call(30.0)], [Open(0, D1, Side.BUY, 100, 1.0)], id_="comprada1")
    cedo = _Relogio(datetime(2026, 11, 9, 14, 0, tzinfo=B3))  # 8 du até 19/11
    assert _servico(relogio=cedo).evaluate(_carteira(_visao(comprada)), ()).alerts == ()
    limites = AlertSettings(expiry_days=10)
    avaliacao = _servico(relogio=cedo, limites=limites).evaluate(_carteira(_visao(comprada)), ())
    (alerta,) = avaliacao.alerts
    assert (alerta.kind, alerta.business_days) == (AlertKind.EXPIRY_NEAR, 8)


def test_avisos_de_vencimento_e_fonte() -> None:
    vendida = operacao([call(30.0)], [Open(0, D1, Side.SELL, 100, 1.0)], id_="vendida01")
    depois = _Relogio(datetime(2026, 11, 20, 10, 0, tzinfo=B3))
    aviso = ExpiryNotice("vendida01", 0, "PETRK300", NOVEMBRO, ExpiryOutcome.REGISTRAR_EXERCICIO)
    visao = _servico(relogio=depois).evaluate(
        _carteira(_visao(vendida), fonte=DataSource.FIM_DE_DIA), [aviso]
    )
    assert [a.kind for a in visao.alerts] == [AlertKind.EXERCISE_TO_REGISTER]
    assert visao.source is DataSource.FIM_DE_DIA


def test_dispensar_e_restaurar_todos() -> None:
    caixa = _Dispensados()
    servico = _servico(caixa)
    servico.dismiss("stop:a:-")
    servico.dismiss("alvo:b:-")
    assert caixa.chaves == {"stop:a:-", "alvo:b:-"}
    servico.restore_all()
    assert caixa.chaves == frozenset()


def test_sem_perfil_aberto_erro_de_dominio() -> None:
    def sem_perfil() -> AlertSettings:
        raise NoActiveProfileError("nenhum perfil aberto")

    servico = AlertService(
        _Dispensados,
        sem_perfil,
        _Relogio(),
        B3,
        market=MercadoFalso(),
        calendar=CALENDARIO,
    )
    with pytest.raises(NoActiveProfileError):
        servico.evaluate(_carteira(_visao(_acoes_com_stop())), ())


def _meia_noite_utc(dia: date) -> datetime:
    return datetime(dia.year, dia.month, dia.day, tzinfo=UTC)


def test_hoje_pelo_fuso_da_b3() -> None:
    # 01h UTC de 18/11 ainda é 17/11 em Brasília: dois dias úteis, não um.
    comprada = operacao([call(30.0)], [Open(0, D1, Side.BUY, 100, 1.0)], id_="comprada1")
    relogio = _Relogio(_meia_noite_utc(date(2026, 11, 18)) + timedelta(hours=1))
    (alerta,) = _servico(relogio=relogio).evaluate(_carteira(_visao(comprada)), ()).alerts
    assert alerta.business_days == 2


def test_vencimento_que_ja_passou_fica_indeterminado() -> None:
    # Sem aviso de vencimento ainda (o pó roda antes, na Carteira): a perna não vira alerta.
    vendida = operacao([call(30.0)], [Open(0, D1, Side.SELL, 100, 1.0)], id_="vendida01")
    depois = _Relogio(datetime(2026, 11, 23, 10, 0, tzinfo=B3))
    caixa = _Dispensados(frozenset({"vencimento_proximo:vendida01:0"}))
    assert _servico(caixa, relogio=depois).evaluate(_carteira(_visao(vendida)), ()).alerts == ()
    assert caixa.gravacoes == []


def test_cotacao_sem_ultimo_nem_fechamento_anterior() -> None:
    vendida = operacao([call(30.0)], [Open(0, D1, Side.SELL, 100, 1.0)], id_="vendida01")
    mercado = MercadoFalso(quotes={"PETR4": _cotacao(None)})
    alertas = _servico(mercado=mercado).evaluate(_carteira(_visao(vendida)), ()).alerts
    assert [a.kind for a in alertas] == [AlertKind.EXPIRY_NEAR]

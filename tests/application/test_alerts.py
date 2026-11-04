"""``AlertService``: a carteira marcada, o spot, o calendário, os limites e os dispensados."""

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from options_engine.application.ports.alerts import AlertUseCase
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
    estados = leg_states(operacao_)
    marcas = tuple(None if e.side is None else LegMark(1.0, aberto) for e in estados)
    return OperationView(operacao_, estados, realizado, marcas, aberto)


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

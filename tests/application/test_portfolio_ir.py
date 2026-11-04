"""``PortfolioService.income_tax``: o IR mensal estimado e o último dia útil do mês seguinte."""

from datetime import date, timedelta, timezone

from pytest import approx

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.outbound import UnreadableFile
from options_engine.application.use_cases.portfolio import PortfolioService
from options_engine.domain.model.enums import Side
from options_engine.domain.portfolio.model import Close, Exercise, Expired, Open, Operation
from tests.application._fakes import FakeOperationRepository
from tests.application._mercado_falso import CALENDARIO, INSTANTE, MercadoFalso
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import call, operacao, put

B3 = timezone(timedelta(hours=-3))
OUT1, OUT15 = date(2026, 10, 1), date(2026, 10, 15)
NOV3, NOV12, NOV19 = date(2026, 11, 3), date(2026, 11, 12), date(2026, 11, 19)
NOV8_2027, DEZ7 = date(2027, 11, 8), date(2027, 12, 7)


def _servico(*operacoes: Operation, ilegiveis: tuple[UnreadableFile, ...] = ()) -> PortfolioService:
    repositorio = FakeOperationRepository({o.id: o for o in operacoes}, ilegiveis)
    return PortfolioService(
        lambda: repositorio,
        FixedClock(INSTANTE),
        [make_cost_schedule()],
        lambda: "novo",
        B3,
        market=MercadoFalso(),
        calendar=CALENDARIO,
    )


def _call_de_outubro() -> Operation:
    return operacao(
        [call(30.0)],
        [
            Open(0, OUT1, Side.BUY, 200, 1.00, 2.00),
            Close(0, OUT1, 100, 1.30, 1.00),
            Close(0, OUT15, 100, 0.50, 1.00),
        ],
        id_="op1",
        nome="call de outubro",
    )


def _venda_de_put() -> Operation:
    return operacao(
        [put(28.0)],
        [
            Open(0, NOV3, Side.SELL, 200, 0.80, 2.00),
            Close(0, NOV12, 100, 0.20, 1.00),
            Expired(0, NOV19),
        ],
        id_="op2",
        nome="venda de put",
    )


def _call_exercida() -> Operation:
    return operacao(
        [call(32.0)],
        [Open(0, NOV3, Side.BUY, 100, 0.40, 1.00), Exercise(0, NOV19, 100, 0.0)],
        id_="op3",
        nome="call exercida",
    )


def test_dois_meses_conferidos_a_mao() -> None:
    servico = _servico(_call_de_outubro(), _venda_de_put(), _call_exercida())
    outubro, novembro = servico.income_tax()
    assert outubro.month.month == date(2026, 10, 1)
    assert (outubro.month.common_result, outubro.month.day_trade_result) == approx((-52.00, 28.00))
    assert outubro.month.tax == approx(5.60)
    assert (outubro.month.due, outubro.month.carried_out) == approx((0.0, 5.60))
    assert outubro.pay_by is None
    assert novembro.month.month == date(2026, 11, 1)
    assert novembro.month.common_result == approx(137.00)
    assert novembro.month.common_base == approx(85.00)
    assert novembro.month.tax == approx(12.75)
    assert (novembro.month.carried_in, novembro.month.due) == approx((5.60, 18.35))
    assert novembro.pay_by == date(2026, 12, 30)  # 31/12 é feriado na B3
    assert [(n.on, n.symbol, n.operation) for n in novembro.month.exercises] == [
        (NOV19, "PETRK320", "call exercida")
    ]


def test_ir_ignora_arquivo_ilegivel() -> None:
    servico = _servico(
        _venda_de_put(), ilegiveis=(UnreadableFile("operacoes/x.json", "corrompido"),)
    )
    (mes,) = servico.income_tax()
    assert mes.month.month == date(2026, 11, 1)
    assert mes.month.common_result == approx(137.00)


def test_pagar_ate_fora_da_cobertura_e_none() -> None:
    # day trade de R$ 100 em dezembro de 2027: IR de R$ 20 a pagar, mas o mês seguinte já está
    # fora do calendário empacotado (vai até 31/12/2027)
    day_trade = operacao(
        [call(30.0)],
        [Open(0, DEZ7, Side.BUY, 100, 1.00, 0.0), Close(0, DEZ7, 100, 2.00, 0.0)],
        nome="day trade de dezembro",
    )
    (mes,) = _servico(day_trade).income_tax()
    assert mes.month.due == approx(20.00)
    assert mes.pay_by is None


def test_pagar_ate_na_borda_da_cobertura() -> None:
    # day trade de R$ 100 em novembro de 2027: o último dia do mês seguinte (31/12/2027, feriado
    # no CSV) tem a consulta fora da cobertura; o dia útil vem de 30/12, não de None
    day_trade = operacao(
        [call(30.0)],
        [Open(0, NOV8_2027, Side.BUY, 100, 1.00, 0.0), Close(0, NOV8_2027, 100, 2.00, 0.0)],
        nome="day trade de novembro",
    )
    (mes,) = _servico(day_trade).income_tax()
    assert mes.month.due == approx(20.00)
    assert mes.pay_by == date(2027, 12, 30)

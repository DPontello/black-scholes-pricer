"""IR mensal por categoria: prejuízo compensado, alíquotas de 15% e 20% e o DARF mínimo de R$ 10."""

from datetime import date

from pytest import approx

from options_engine.domain.portfolio.income_tax import (
    COMMON_RATE,
    DARF_MINIMUM,
    DAY_TRADE_RATE,
    ExerciseNote,
    PieceKind,
    TaxCategory,
    TaxPiece,
    TaxRecords,
    monthly_tax,
)

OUT5, OUT20 = date(2026, 10, 5), date(2026, 10, 20)
NOV9, NOV24 = date(2026, 11, 9), date(2026, 11, 24)
DEZ7 = date(2026, 12, 7)
COMUM, DT = TaxCategory.COMMON, TaxCategory.DAY_TRADE


def peca(dia: date, categoria: TaxCategory, resultado: float) -> TaxPiece:
    return TaxPiece(dia, "PETRA1", categoria, PieceKind.CLOSE, resultado, ("operação",))


def registros(*pecas: TaxPiece, notas: tuple[ExerciseNote, ...] = ()) -> TaxRecords:
    return TaxRecords(tuple(pecas), notas)


def test_constantes_do_imposto() -> None:
    assert (COMMON_RATE, DAY_TRADE_RATE, DARF_MINIMUM) == (0.15, 0.20, 10.0)


def test_mes_com_day_trade_abaixo_do_minimo_fica_para_depois() -> None:
    (mes,) = monthly_tax(registros(peca(OUT5, COMUM, -52.00), peca(OUT20, DT, 28.00)))
    assert mes.month == date(2026, 10, 1)
    assert (mes.common_result, mes.day_trade_result) == approx((-52.00, 28.00))
    assert (mes.common_base, mes.day_trade_base) == approx((0.0, 28.00))
    assert (mes.common_loss, mes.day_trade_loss) == approx((52.00, 0.0))
    assert mes.tax == approx(5.60)
    assert (mes.carried_in, mes.due, mes.carried_out) == approx((0.0, 0.0, 5.60))


def test_prejuizo_comum_abate_o_mes_seguinte_e_o_ir_pendente_soma() -> None:
    _, nov = monthly_tax(
        registros(peca(OUT5, COMUM, -52.00), peca(OUT20, DT, 28.00), peca(NOV9, COMUM, 137.00))
    )
    assert nov.month == date(2026, 11, 1)
    assert nov.common_result == approx(137.00)
    assert (nov.common_base, nov.common_loss) == approx((85.00, 0.0))
    assert nov.tax == approx(12.75)
    assert (nov.carried_in, nov.due, nov.carried_out) == approx((5.60, 18.35, 0.0))


def test_prejuizo_de_day_trade_nao_abate_comum() -> None:
    _, mes2 = monthly_tax(registros(peca(OUT5, DT, -100.00), peca(NOV9, COMUM, 100.00)))
    assert mes2.common_base == approx(100.00)
    assert mes2.tax == approx(15.00)
    assert mes2.day_trade_loss == approx(100.00)


def test_prejuizo_comum_nao_abate_day_trade() -> None:
    _, mes2 = monthly_tax(registros(peca(OUT5, COMUM, -100.00), peca(NOV9, DT, 100.00)))
    assert mes2.day_trade_base == approx(100.00)
    assert mes2.tax == approx(20.00)
    assert mes2.common_loss == approx(100.00)


def test_prejuizo_depois_nao_apaga_ir_pendente() -> None:
    mes1, mes2 = monthly_tax(registros(peca(OUT5, COMUM, 40.00), peca(NOV9, COMUM, -100.00)))
    assert mes1.tax == approx(6.00)
    assert (mes1.due, mes1.carried_out) == approx((0.0, 6.00))
    assert mes2.tax == approx(0.0)
    assert (mes2.carried_in, mes2.due, mes2.carried_out) == approx((6.00, 0.0, 6.00))
    assert mes2.common_loss == approx(100.00)


def test_ir_pendente_atravessa_mes_vazio() -> None:
    out, dez = monthly_tax(registros(peca(OUT5, DT, 28.00), peca(DEZ7, COMUM, 40.00)))
    assert (out.month, dez.month) == (date(2026, 10, 1), date(2026, 12, 1))
    assert out.carried_out == approx(5.60)
    assert dez.tax == approx(6.00)
    assert (dez.carried_in, dez.due, dez.carried_out) == approx((5.60, 11.60, 0.0))


def test_ir_pendente_acumula_ate_passar_de_dez() -> None:
    out, nov, dez = monthly_tax(
        registros(peca(OUT5, DT, 15.00), peca(NOV9, DT, 20.00), peca(DEZ7, DT, 25.00))
    )
    assert (out.tax, out.carried_in, out.due, out.carried_out) == approx((3.00, 0.0, 0.0, 3.00))
    assert (nov.tax, nov.carried_in, nov.due, nov.carried_out) == approx((4.00, 3.00, 0.0, 7.00))
    assert (dez.tax, dez.carried_in, dez.due, dez.carried_out) == approx((5.00, 7.00, 12.00, 0.0))


def test_abatimento_parcial() -> None:
    _, mes2 = monthly_tax(registros(peca(OUT5, COMUM, -100.00), peca(NOV9, COMUM, 30.00)))
    assert mes2.common_base == approx(0.0)
    assert mes2.common_loss == approx(70.00)
    assert mes2.tax == approx(0.0)


def test_prejuizo_de_day_trade_abate_day_trade() -> None:
    _, mes2 = monthly_tax(registros(peca(OUT5, DT, -50.00), peca(NOV9, DT, 80.00)))
    assert mes2.day_trade_base == approx(30.00)
    assert mes2.day_trade_loss == approx(0.0)
    assert mes2.tax == approx(6.00)


def test_prejuizo_e_ganho_no_mesmo_mes_em_tipos_diferentes() -> None:
    (mes,) = monthly_tax(registros(peca(OUT5, COMUM, -40.00), peca(OUT20, DT, 60.00)))
    assert mes.common_loss == approx(40.00)
    assert mes.day_trade_base == approx(60.00)
    assert mes.tax == approx(12.00)
    assert (mes.due, mes.carried_out) == approx((12.00, 0.0))


def test_ir_de_exatamente_dez_paga() -> None:
    (mes,) = monthly_tax(registros(peca(OUT5, DT, 50.00)))
    assert mes.tax == approx(10.00)
    assert (mes.due, mes.carried_out) == approx((10.00, 0.0))


def test_mes_so_com_exercicio_aparece_com_a_nota() -> None:
    nota = ExerciseNote(NOV9, "PETRA1", "call de outubro")
    (mes,) = monthly_tax(registros(notas=(nota,)))
    assert mes.month == date(2026, 11, 1)
    assert (mes.common_result, mes.day_trade_result) == (0.0, 0.0)
    assert (mes.common_base, mes.day_trade_base, mes.common_loss, mes.day_trade_loss) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert (mes.tax, mes.carried_in, mes.due, mes.carried_out) == (0.0, 0.0, 0.0, 0.0)
    assert mes.pieces == ()
    assert mes.exercises == (nota,)


def test_meses_sem_nada_nao_aparecem() -> None:
    out, dez = monthly_tax(registros(peca(OUT5, COMUM, -30.00), peca(DEZ7, COMUM, 130.00)))
    assert (out.month, dez.month) == (date(2026, 10, 1), date(2026, 12, 1))
    assert dez.common_base == approx(100.00)


def test_cada_mes_leva_as_pecas_e_notas_na_ordem_dos_registros() -> None:
    p1, p2, p3 = peca(OUT5, COMUM, 10.00), peca(OUT20, DT, 5.00), peca(NOV9, COMUM, 20.00)
    n1, n2 = ExerciseNote(OUT20, "PETRB1", "op"), ExerciseNote(NOV24, "PETRB1", "op")
    out, nov = monthly_tax(registros(p1, p2, p3, notas=(n1, n2)))
    assert (out.pieces, out.exercises) == ((p1, p2), (n1,))
    assert (nov.pieces, nov.exercises) == ((p3,), (n2,))


def test_sem_registros_sem_meses() -> None:
    assert monthly_tax(TaxRecords((), ())) == ()

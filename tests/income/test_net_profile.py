"""Perfil líquido no vencimento — tabela de referência, oráculo numérico e propriedades.

Golden cases (ADR-0005 item 4): as quatro estruturas de renda, brutas e
líquidas, com a tabela de referência do spike (emolumentos de opções 0,1340%
por perna; do à vista/exercício 0,0300%; corretagem e corretagem de
exercício R$ 0,00; IR 15%), CDI 12% a.a. efetivo base 252 e 100 ações.
Aritmética à mão na docstring de cada caso; os anualizados vêm de potências
inteiras exatas (252/du inteiro), expandidas com aritmética racional.

Oráculo numérico: ``_resultado_liquido`` avalia o P&L líquido no vencimento
perna a perna, num preço de cada vez, com somas ingênuas — caminho de código
independente da forma fechada de ``metrics.py``. O breakeven líquido é
reencontrado por bisseção sobre ele; os extremos, pela avaliação nos
cenários e por varredura de uma grade de preços.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.income import (
    CostSchedule,
    IncomeMetrics,
    cash_secured_put_metrics,
    covered_call_metrics,
    credit_spread_metrics,
)
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.factories import vertical_spread
from tests._tolerances import (
    ABS_BREAKEVEN,
    ABS_INCOME,
    ABS_INCOME_ORACLE_PER_SCALE,
    INEQ_SLACK,
    REL_BREAKEVEN,
    REL_INCOME,
    REL_INCOME_ORACLE,
    assert_close,
)
from tests.domain._builders import make_vertical_legs
from tests.income._builders import (
    make_cdi,
    make_cost_schedule,
    reference_cost_schedule,
    zero_cost_schedule,
)

ACOES = 100


def _close(actual: float | None, expected: float, label: str) -> None:
    assert actual is not None, f"{label}: None inesperado"
    assert_close(actual, expected, rel=REL_INCOME, abs_=ABS_INCOME, label=label)


# ---------------------------------------------------------------------------
# Golden cases com a tabela de referência do spike
# ---------------------------------------------------------------------------


def test_put_coberta_golden_tabela_de_referencia() -> None:
    """Vende put K = 30,00 a 0,60, 21 du, CDI 12%.

    bruto: rendimento 0,60 / 30 = 0,02; anualizado 1,02^12 - 1 = 0,268241794562545318...;
           breakeven 29,40; ganho 60,00; perda -2.940,00
    montagem  = 0,00134 x 60,00                     = 0,0804
    IR        = 0,15 x (60,00 - 0,0804) = 0,15 x 59,9196 = 8,98794
    custos    = 0,0804 + 8,98794                    = 9,06834
    líquido   = (60,00 - 9,06834) / 3.000,00 = 50,93166 / 3.000 = 0,01697722
    anualizado líquido = 1,01697722^12 - 1          = 0,223868337896317503...
    excesso líquido    = 0,2238683378963175 - 0,12  = 0,1038683378963175
    exercício (put exercida) = 0,0003 x 3.000,00    = 0,90
    ganho máximo líquido = 59,9196 - 8,98794         = 50,93166
    perda máxima líquida = -2.940,00 - 0,0804 - 0,90 = -2.940,9804
    breakeven líquido    = 29,40 + (0,0804 + 0,90) / 100 = 29,409804
    """
    m = cash_secured_put_metrics(
        strike=30.0,
        premium_per_share=0.60,
        business_days=21,
        cdi=make_cdi(0.12),
        cost_schedule=reference_cost_schedule(),
    )
    _close(m.yield_period, 0.02, "rendimento")
    _close(m.yield_annual_252, 0.2682417945625453183, "anualizado")
    _close(m.breakeven, 29.40, "breakeven")
    _close(m.max_gain_per_position, 60.0, "ganho máximo")
    _close(m.max_loss_per_position, -2940.0, "perda máxima")
    _close(m.costs.setup.total, 0.0804, "montagem")
    _close(m.costs.income_tax, 8.98794, "IR")
    _close(m.costs.total, 9.06834, "custos")
    _close(m.net_yield_period, 0.01697722, "rendimento líquido")
    _close(m.net_yield_annual_252, 0.2238683378963175032, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 0.1038683378963175032, "excesso líquido")
    _close(m.net_max_gain_per_position, 50.93166, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -2940.9804, "perda máxima líquida")
    _close(m.net_breakeven, 29.409804, "breakeven líquido")
    assert m.costs.schedule == reference_cost_schedule()


def test_venda_coberta_golden_tabela_de_referencia() -> None:
    """Ação a 32,00, vende call K = 34,00 a 0,80, 42 du, CDI 12%.

    bruto: rendimento 0,80 / 32 = 0,025; anualizado 1,025^6 - 1 = 0,159693418212890625;
           proteção 0,025; breakeven 31,20; ganho 280,00; perda -3.120,00
    montagem  = 0,00134 x 80,00 (opção) + 0,0003 x 3.200,00 (ação) = 0,1072 + 0,96 = 1,0672
    IR        = 0,15 x (80,00 - 1,0672) = 0,15 x 78,9328          = 11,83992
    custos    = 1,0672 + 11,83992                                 = 12,90712
    líquido   = (80,00 - 12,90712) / 3.200,00 = 67,09288 / 3.200  = 0,020966525
    anualizado líquido = 1,020966525^6 - 1                        = 0,132580336274888552...
    excesso líquido    = 0,1325803362748886 - 0,12                = 0,0125803362748886
    exercício (call exercida) = 0,0003 x 3.400,00                 = 1,02
    ganho máximo antes do IR  = 280,00 - 1,0672 - 1,02            = 277,9128
    IR só sobre o prêmio      = 0,15 x (80,00 - 0,1072)           = 11,98392
    ganho máximo líquido      = 277,9128 - 11,98392               = 265,92888
    perda máxima líquida      = -3.120,00 - 1,0672                = -3.121,0672
    breakeven líquido         = 31,20 + 1,0672 / 100              = 31,210672
    """
    m = covered_call_metrics(
        spot=32.0,
        strike=34.0,
        premium_per_share=0.80,
        business_days=42,
        cdi=make_cdi(0.12),
        cost_schedule=reference_cost_schedule(),
    )
    _close(m.yield_period, 0.025, "rendimento")
    _close(m.yield_annual_252, 0.159693418212890625, "anualizado")
    _close(m.downside_protection, 0.025, "proteção")
    _close(m.breakeven, 31.20, "breakeven")
    _close(m.max_gain_per_position, 280.0, "ganho máximo")
    _close(m.max_loss_per_position, -3120.0, "perda máxima")
    _close(m.costs.setup.total, 1.0672, "montagem")
    _close(m.costs.income_tax, 11.83992, "IR")
    _close(m.costs.total, 12.90712, "custos")
    _close(m.net_yield_period, 0.020966525, "rendimento líquido")
    _close(m.net_yield_annual_252, 0.1325803362748885527, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 0.0125803362748885527, "excesso líquido")
    _close(m.net_max_gain_per_position, 265.92888, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -3121.0672, "perda máxima líquida")
    _close(m.net_breakeven, 31.210672, "breakeven líquido")


def test_trava_de_alta_com_put_golden_tabela_de_referencia() -> None:
    """Compra put 28 a 0,50 e vende put 30 a 0,90, 63 du, CDI 12%.

    bruto: crédito 0,40; risco 1,60; retorno 0,25; anualizado 1,25^4 - 1 = 1,44140625;
           breakeven 29,60; ganho 40,00; perda -160,00
    montagem  = 0,00134 x (50,00 + 90,00)               = 0,1876
    IR        = 0,15 x (40,00 - 0,1876) = 0,15 x 39,8124 = 5,97186
    custos    = 0,1876 + 5,97186                        = 6,15946
    líquido   = (40,00 - 6,15946) / 160,00 = 33,84054 / 160 = 0,211503375
    anualizado líquido = 1,211503375^4 - 1              = 1,154261962918254824...
    excesso líquido    = 1,1542619629182548 - 0,12      = 1,0342619629182548
    exercício da vendida (put 30) = 0,0003 x 3.000,00   = 0,90
    exercício das duas (28 e 30)  = 0,0003 x 5.800,00   = 1,74
    ganho máximo líquido = 39,8124 - 5,97186             = 33,84054
    perda máxima líquida = -160,00 - 0,1876 - 1,74       = -161,9276
    breakeven líquido    = 29,60 + (0,1876 + 0,90) / 100 = 29,610876
    """
    trava = vertical_spread(make_vertical_legs(premiums=(0.50, 0.90)))
    m = credit_spread_metrics(
        trava, business_days=63, cdi=make_cdi(0.12), cost_schedule=reference_cost_schedule()
    )
    _close(m.yield_period, 0.25, "retorno sobre risco")
    _close(m.yield_annual_252, 1.44140625, "anualizado")
    _close(m.breakeven, 29.60, "breakeven")
    _close(m.max_gain_per_position, 40.0, "ganho máximo")
    _close(m.max_loss_per_position, -160.0, "perda máxima")
    _close(m.costs.setup.total, 0.1876, "montagem")
    _close(m.costs.income_tax, 5.97186, "IR")
    _close(m.costs.total, 6.15946, "custos")
    _close(m.net_yield_period, 0.211503375, "retorno líquido")
    _close(m.net_yield_annual_252, 1.1542619629182548248, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 1.0342619629182548248, "excesso líquido")
    _close(m.net_max_gain_per_position, 33.84054, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -161.9276, "perda máxima líquida")
    _close(m.net_breakeven, 29.610876, "breakeven líquido")


def test_trava_de_baixa_com_call_golden_tabela_de_referencia() -> None:
    """Vende call 32 a 1,10 e compra call 34 a 0,35, 126 du, CDI 12%.

    bruto: crédito 0,75; risco 1,25; retorno 0,6; anualizado 1,6^2 - 1 = 1,56;
           breakeven 32,75; ganho 75,00; perda -125,00
    montagem  = 0,00134 x (110,00 + 35,00)               = 0,1943
    IR        = 0,15 x (75,00 - 0,1943) = 0,15 x 74,8057 = 11,220855
    custos    = 0,1943 + 11,220855                       = 11,415155
    líquido   = (75,00 - 11,415155) / 125,00 = 63,584845 / 125 = 0,50867876
    anualizado líquido = 1,50867876^2 - 1                = 1,2761116008751376 (exato)
    excesso líquido    = 1,2761116008751376 - 0,12       = 1,1561116008751376
    exercício da vendida (call 32) = 0,0003 x 3.200,00   = 0,96
    exercício das duas (32 e 34)   = 0,0003 x 6.600,00   = 1,98
    ganho máximo líquido = 74,8057 - 11,220855            = 63,584845
    perda máxima líquida = -125,00 - 0,1943 - 1,98        = -127,1743
    breakeven líquido    = 32,75 - (0,1943 + 0,96) / 100  = 32,738457
    """
    trava = vertical_spread(
        make_vertical_legs(
            option_type=OptionType.CALL,
            direction=Side.SELL,
            strikes=(32.0, 34.0),
            premiums=(1.10, 0.35),
        )
    )
    m = credit_spread_metrics(
        trava, business_days=126, cdi=make_cdi(0.12), cost_schedule=reference_cost_schedule()
    )
    _close(m.yield_period, 0.6, "retorno sobre risco")
    _close(m.yield_annual_252, 1.56, "anualizado")
    _close(m.breakeven, 32.75, "breakeven")
    _close(m.max_gain_per_position, 75.0, "ganho máximo")
    _close(m.max_loss_per_position, -125.0, "perda máxima")
    _close(m.costs.setup.total, 0.1943, "montagem")
    _close(m.costs.income_tax, 11.220855, "IR")
    _close(m.costs.total, 11.415155, "custos")
    _close(m.net_yield_period, 0.50867876, "retorno líquido")
    _close(m.net_yield_annual_252, 1.2761116008751376, "anualizado líquido")
    _close(m.net_excess_over_cdi_annual_252, 1.1561116008751376, "excesso líquido")
    _close(m.net_max_gain_per_position, 63.584845, "ganho máximo líquido")
    _close(m.net_max_loss_per_position, -127.1743, "perda máxima líquida")
    _close(m.net_breakeven, 32.738457, "breakeven líquido")


# ---------------------------------------------------------------------------
# Oráculo numérico — P&L líquido no vencimento, perna a perna
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Perna:
    """Perna do oráculo: opção (``tipo``) ou ação comprada (``tipo = None``).

    ``preco`` é o strike da opção ou o preço de compra da ação; ``premio`` é
    o prêmio unitário da opção (0 na ação).
    """

    tipo: OptionType | None
    lado: Side
    preco: float
    premio: float = 0.0


def _resultado_liquido(pernas: tuple[_Perna, ...], s: float, tabela: CostSchedule) -> float:
    """P&L líquido no vencimento com o subjacente a ``s``, para ``ACOES`` ações por perna.

    Perna a perna: prêmio e payoff com sinal pelo lado; cada ordem paga
    emolumento e corretagem; perna dentro do dinheiro (strike estritamente
    ultrapassado) paga o exercício ao strike; IR sobre o resultado positivo,
    limitado ao prêmio menos as ordens de opção. Somas ingênuas de propósito.
    """
    resultado = 0.0
    custos = 0.0
    premio_liquido = 0.0
    ordens_de_opcao = 0.0
    for perna in pernas:
        if perna.tipo is None:
            resultado += ACOES * (s - perna.preco)
            custos += tabela.spot_exchange_fee_rate * perna.preco * ACOES
            custos += tabela.brokerage_per_order
            continue
        sinal = 1.0 if perna.lado is Side.SELL else -1.0
        if perna.tipo is OptionType.CALL:
            intrinseco = max(s - perna.preco, 0.0)
        else:
            intrinseco = max(perna.preco - s, 0.0)
        resultado += sinal * ACOES * (perna.premio - intrinseco)
        ordem = tabela.option_exchange_fee_rate * perna.premio * ACOES + tabela.brokerage_per_order
        custos += ordem
        ordens_de_opcao += ordem
        premio_liquido += sinal * perna.premio * ACOES
        if intrinseco > 0.0:
            custos += tabela.spot_exchange_fee_rate * perna.preco * ACOES
            custos += tabela.exercise_brokerage_per_order
    antes_do_ir = resultado - custos
    teto = premio_liquido - ordens_de_opcao
    return antes_do_ir - tabela.income_tax_rate * max(min(antes_do_ir, teto), 0.0)


def _troca_de_sinal(f: Callable[[float], float], a: float, b: float, zona_morta: float) -> float:
    """Bisseção da fronteira entre ``f < -zona_morta`` e o resto, em [a, b].

    A zona morta é o piso da tolerância do oráculo: um resultado a poucos
    ulps de zero conta como zero dos dois lados, e a fronteira desloca no
    máximo ``zona_morta / ações`` no preço — muito abaixo de ``ABS_BREAKEVEN``.
    """

    def negativo(s: float) -> bool:
        return f(s) < -zona_morta

    negativo_em_a = negativo(a)
    assert negativo(b) != negativo_em_a, "o intervalo não contém troca de sinal"
    for _ in range(200):
        meio = (a + b) / 2.0
        if meio in (a, b):
            break
        if negativo(meio) == negativo_em_a:
            a = meio
        else:
            b = meio
    return (a + b) / 2.0


Estrutura = Literal["put coberta", "venda coberta", "trava de alta com put", "trava de baixa"]


@dataclass(frozen=True)
class _Caso:
    """Uma oportunidade e o que o oráculo precisa para conferi-la.

    ``cenario_de_ganho`` / ``cenario_de_perda``: preço no vencimento dentro do
    cenário de ganho máximo e do de perda máxima. ``intervalo_do_breakeven``:
    trecho em que o resultado líquido troca de sinal. ``folga_do_ganho``: o
    quanto a grade pode passar do ganho máximo — na venda coberta, o custo de
    exercício (com S = K a call não é exercida; docstring de
    ``covered_call_metrics``); zero nas demais.
    """

    estrutura: Estrutura
    metricas: IncomeMetrics
    pernas: tuple[_Perna, ...]
    tabela: CostSchedule
    cenario_de_ganho: float
    cenario_de_perda: float
    intervalo_do_breakeven: tuple[float, float]
    folga_do_ganho: float

    @property
    def strikes(self) -> tuple[float, ...]:
        return tuple(p.preco for p in self.pernas if p.tipo is not None)

    @property
    def escala(self) -> float:
        return max(p.preco for p in self.pernas) * ACOES


def _put_coberta(tabela: CostSchedule, strike: float, premio: float) -> _Caso:
    metricas = cash_secured_put_metrics(
        strike=strike,
        premium_per_share=premio,
        business_days=21,
        cdi=make_cdi(),
        cost_schedule=tabela,
    )
    return _Caso(
        estrutura="put coberta",
        metricas=metricas,
        pernas=(_Perna(OptionType.PUT, Side.SELL, strike, premio),),
        tabela=tabela,
        cenario_de_ganho=2.0 * strike,
        cenario_de_perda=0.0,
        intervalo_do_breakeven=(0.0, strike),
        folga_do_ganho=0.0,
    )


def _venda_coberta(tabela: CostSchedule, spot: float, strike: float, premio: float) -> _Caso:
    metricas = covered_call_metrics(
        spot=spot,
        strike=strike,
        premium_per_share=premio,
        business_days=21,
        cdi=make_cdi(),
        cost_schedule=tabela,
    )
    exercicio = tabela.spot_exchange_fee_rate * strike * ACOES + tabela.exercise_brokerage_per_order
    return _Caso(
        estrutura="venda coberta",
        metricas=metricas,
        pernas=(
            _Perna(None, Side.BUY, spot),
            _Perna(OptionType.CALL, Side.SELL, strike, premio),
        ),
        tabela=tabela,
        cenario_de_ganho=2.0 * strike,
        cenario_de_perda=0.0,
        intervalo_do_breakeven=(0.0, strike),
        folga_do_ganho=exercicio,
    )


def _trava(
    tabela: CostSchedule,
    option_type: OptionType,
    strikes: tuple[float, float],
    premios: tuple[float, float],
) -> _Caso:
    trava = vertical_spread(
        make_vertical_legs(
            option_type=option_type, direction=Side.SELL, strikes=strikes, premiums=premios
        )
    )
    metricas = credit_spread_metrics(trava, business_days=21, cdi=make_cdi(), cost_schedule=tabela)
    pernas = tuple(
        _Perna(leg.terms.option_type, leg.side, leg.terms.strike, leg.premium or 0.0)
        for leg in trava.legs
    )
    k_baixo, k_alto = strikes
    de_puts = option_type is OptionType.PUT
    return _Caso(
        estrutura="trava de alta com put" if de_puts else "trava de baixa",
        metricas=metricas,
        pernas=pernas,
        tabela=tabela,
        cenario_de_ganho=2.0 * k_alto if de_puts else k_baixo / 2.0,
        cenario_de_perda=k_baixo / 2.0 if de_puts else 2.0 * k_alto,
        intervalo_do_breakeven=(k_baixo, k_alto),
        folga_do_ganho=0.0,
    )


def _grade(caso: _Caso, pontos: int) -> list[float]:
    """Preços de 0 a 2 x maior strike, mais cada strike e seus vizinhos imediatos."""
    topo = 2.0 * max(caso.strikes)
    grade = [topo * i / pontos for i in range(pontos + 1)]
    for k in caso.strikes:
        grade += [k, k * (1.0 - 1e-9), k * (1.0 + 1e-9)]
    return grade


def _confere_com_o_oraculo(caso: _Caso, pontos: int) -> None:
    m = caso.metricas

    def liquido(s: float) -> float:
        return _resultado_liquido(caso.pernas, s, caso.tabela)

    piso = ABS_INCOME_ORACLE_PER_SCALE * caso.escala

    def perto(actual: float, expected: float, label: str) -> None:
        assert_close(actual, expected, rel=REL_INCOME_ORACLE, abs_=piso, label=label)

    perto(m.net_max_gain_per_position, liquido(caso.cenario_de_ganho), "ganho máximo")
    perto(m.net_max_loss_per_position, liquido(caso.cenario_de_perda), "perda máxima")
    valores = [liquido(s) for s in _grade(caso, pontos)]
    assert min(valores) >= m.net_max_loss_per_position - piso, "grade abaixo da perda máxima"
    assert max(valores) <= m.net_max_gain_per_position + caso.folga_do_ganho + piso, (
        "grade acima do ganho máximo"
    )
    if m.net_breakeven is None:
        assert max(valores) < piso, "breakeven None, mas o líquido chega a zero na grade"
    else:
        reencontrado = _troca_de_sinal(liquido, *caso.intervalo_do_breakeven, zona_morta=piso)
        assert_close(
            m.net_breakeven,
            reencontrado,
            rel=REL_BREAKEVEN,
            abs_=ABS_BREAKEVEN,
            label="breakeven",
        )


_CASOS_FIXOS: list[Callable[[], _Caso]] = [
    lambda: _put_coberta(reference_cost_schedule(), 30.0, 0.60),
    lambda: _venda_coberta(reference_cost_schedule(), 32.0, 34.0, 0.80),
    lambda: _trava(reference_cost_schedule(), OptionType.PUT, (28.0, 30.0), (0.50, 0.90)),
    lambda: _trava(reference_cost_schedule(), OptionType.CALL, (32.0, 34.0), (1.10, 0.35)),
    lambda: _put_coberta(make_cost_schedule(), 30.0, 0.60),
    lambda: _venda_coberta(make_cost_schedule(), 32.0, 34.0, 0.80),
    lambda: _venda_coberta(make_cost_schedule(), 32.0, 30.0, 2.50),  # dentro do dinheiro
    lambda: _trava(make_cost_schedule(), OptionType.PUT, (28.0, 30.0), (0.50, 0.90)),
    lambda: _trava(make_cost_schedule(), OptionType.CALL, (32.0, 34.0), (1.10, 0.35)),
    # Breakeven no salto do exercício (strike vendido) e sem breakeven:
    lambda: _put_coberta(make_cost_schedule(), 30.0, 0.06),
    lambda: _trava(make_cost_schedule(), OptionType.CALL, (32.0, 34.0), (0.16, 0.05)),
    lambda: _put_coberta(make_cost_schedule(), 30.0, 0.0),
    lambda: _venda_coberta(make_cost_schedule(), 32.0, 32.0, 0.05),
    lambda: _trava(make_cost_schedule(), OptionType.PUT, (28.0, 30.0), (0.50, 0.50)),
]


@pytest.mark.parametrize("fabrica", _CASOS_FIXOS)
def test_forma_fechada_bate_com_o_oraculo_numerico(fabrica: Callable[[], _Caso]) -> None:
    """Extremos e breakeven líquidos da forma fechada contra o P&L avaliado preço a preço."""
    _confere_com_o_oraculo(fabrica(), pontos=6_000)


def test_oraculo_cobre_os_dois_lados_do_breakeven() -> None:
    """Sanidade do próprio oráculo no golden da put coberta: o sinal troca no breakeven."""
    caso = _put_coberta(reference_cost_schedule(), 30.0, 0.60)
    be = caso.metricas.net_breakeven
    assert be is not None
    assert _resultado_liquido(caso.pernas, be - 1e-6, caso.tabela) < 0.0
    assert _resultado_liquido(caso.pernas, be + 1e-6, caso.tabela) > 0.0


# ---------------------------------------------------------------------------
# Propriedades — custos só pioram o perfil; custo zero não muda nada
# ---------------------------------------------------------------------------

_preco = st.integers(min_value=500, max_value=10_000).map(lambda centavos: centavos / 100.0)
_fracao = st.floats(min_value=0.0, max_value=0.5)
# Corretagem pequena: mantém o rendimento líquido acima de -100% (anualizável)
# também nas travas estreitas, onde o risco por posição é de poucos reais.
_tabela = st.builds(
    make_cost_schedule,
    option_exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    spot_exchange_fee_rate=st.floats(min_value=0.0, max_value=0.01),
    brokerage_per_order=st.floats(min_value=0.0, max_value=2.0),
    exercise_brokerage_per_order=st.floats(min_value=0.0, max_value=20.0),
    income_tax_rate=st.floats(min_value=0.0, max_value=0.3),
)


@st.composite
def _casos(draw: st.DrawFn, tabela: st.SearchStrategy[CostSchedule] = _tabela) -> _Caso:
    custos = draw(tabela)
    estrutura = draw(st.sampled_from(["put", "venda", "put spread", "call spread"]))
    if estrutura == "put":
        strike = draw(_preco)
        return _put_coberta(custos, strike, draw(_fracao) * strike)
    if estrutura == "venda":
        spot = draw(_preco)
        strike = spot * (1.0 + draw(st.floats(min_value=-0.3, max_value=0.3)))
        intrinseco = max(spot - strike, 0.0)
        premio = intrinseco + draw(_fracao) * (spot - intrinseco)
        return _venda_coberta(custos, spot, strike, premio)
    largura = draw(st.integers(min_value=50, max_value=1_000)) / 100.0
    credito = draw(st.floats(min_value=0.0, max_value=0.9)) * largura
    comprado = draw(st.integers(min_value=0, max_value=200)) / 100.0
    vendido = comprado + credito
    if estrutura == "put spread":
        return _trava(custos, OptionType.PUT, (30.0, 30.0 + largura), (comprado, vendido))
    return _trava(custos, OptionType.CALL, (30.0, 30.0 + largura), (vendido, comprado))


def _escala(caso: _Caso) -> float:
    return INEQ_SLACK * max(1.0, caso.escala)


@given(caso=_casos())
def test_oraculo_numerico_em_entradas_aleatorias(caso: _Caso) -> None:
    _confere_com_o_oraculo(caso, pontos=200)


@given(caso=_casos())
def test_liquido_nunca_melhora_o_bruto(caso: _Caso) -> None:
    """Ganho líquido <= bruto; perda líquida <= bruta (mais negativa)."""
    m = caso.metricas
    assert m.net_max_gain_per_position <= m.max_gain_per_position + _escala(caso)
    assert m.net_max_loss_per_position <= m.max_loss_per_position + _escala(caso)


@given(caso=_casos())
def test_custos_empurram_o_breakeven_contra_o_vendedor(caso: _Caso) -> None:
    """Breakeven líquido acima do bruto nas estruturas de alta, abaixo na trava de baixa."""
    m = caso.metricas
    if m.net_breakeven is None:
        return
    if caso.estrutura == "trava de baixa":
        assert m.net_breakeven <= m.breakeven + _escala(caso)
    else:
        assert m.net_breakeven >= m.breakeven - _escala(caso)


@given(caso=_casos(tabela=st.just(zero_cost_schedule())))
def test_custo_zero_liquido_igual_ao_bruto(caso: _Caso) -> None:
    m = caso.metricas
    piso = ABS_INCOME_ORACLE_PER_SCALE * caso.escala
    assert m.net_breakeven is not None
    assert_close(m.net_breakeven, m.breakeven, rel=REL_BREAKEVEN, abs_=ABS_BREAKEVEN, label="BE")
    assert_close(
        m.net_max_gain_per_position,
        m.max_gain_per_position,
        rel=REL_INCOME_ORACLE,
        abs_=piso,
        label="ganho",
    )
    assert_close(
        m.net_max_loss_per_position,
        m.max_loss_per_position,
        rel=REL_INCOME_ORACLE,
        abs_=piso,
        label="perda",
    )

"""``StrategyBuilderService`` com mercado falso: PETR4 a 30, vol 0,30, pregão de 23/10."""

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.application.ports.inbound import (
    BuilderLegInput,
    BuilderRequest,
    BuilderStockInput,
    LegPriceOrigin,
    StrategyBuilderUseCase,
)
from options_engine.application.use_cases.strategy_builder import StrategyBuilderService
from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.chain import RejectedSeries
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side, StockOrigin
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    InvalidStrategyError,
    UnderlyingUnavailableError,
)
from options_engine.domain.model.quotes import DataSource
from options_engine.domain.model.templates import TEMPLATES
from tests.application._mercado_falso import (
    CALENDARIO,
    NOVEMBRO,
    PREGAO,
    MercadoFalso,
    cadeia,
    serie,
    series_padrao,
)
from tests.income._builders import make_cost_schedule

_COMPRA, _VENDA = Side.BUY, Side.SELL


def _servico(
    mercado: MercadoFalso | None = None,
    *,
    lotes: dict[str, int] | None = None,
    tabela: CostSchedule | None = None,
) -> StrategyBuilderService:
    return StrategyBuilderService(
        MercadoFalso() if mercado is None else mercado,
        CALENDARIO,
        B3_UTC_OFFSET,
        schedules=[make_cost_schedule() if tabela is None else tabela],
        lots=(lotes or {}).get,
    )


def _pedido(
    *pernas: BuilderLegInput,
    acao: BuilderStockInput | None = None,
    modelo: str | None = None,
) -> BuilderRequest:
    return BuilderRequest("PETR4", tuple(pernas), acao, modelo)


def _com(*quotes: object) -> MercadoFalso:
    return MercadoFalso(chains={"PETR4": cadeia([*series_padrao(), *quotes])})  # type: ignore[list-item]


def test_cumpre_o_protocol_e_lista_o_catalogo() -> None:
    servico = _servico()
    assert isinstance(servico, StrategyBuilderUseCase)
    assert servico.templates() == TEMPLATES


def test_compra_pelo_ask_e_venda_pelo_bid() -> None:
    analise = _servico().analyze(
        _pedido(BuilderLegInput("PETRK300", _COMPRA, 100), BuilderLegInput("PETRK320", _VENDA, 100))
    )
    comprada, vendida = analise.legs
    k300 = next(q for q in series_padrao() if q.contract.symbol == "PETRK300")
    k320 = next(q for q in series_padrao() if q.contract.symbol == "PETRK320")
    assert (comprada.price, comprada.origin) == (k300.ask, LegPriceOrigin.EXECUTAVEL)
    assert (vendida.price, vendida.origin) == (k320.bid, LegPriceOrigin.EXECUTAVEL)


def test_preco_digitado_vira_digitado() -> None:
    analise = _servico().analyze(_pedido(BuilderLegInput("PETRK300", _COMPRA, 100, 1.11)))
    assert (analise.legs[0].price, analise.legs[0].origin) == (1.11, LegPriceOrigin.DIGITADO)


def test_sem_oferta_com_negocio_e_indicativo_e_sem_negocio_e_teorico() -> None:
    mercado = _com(
        serie("PETRK340", 34.0, book=False, trades=3),
        serie("PETRK310", 31.0, book=False, last=None, trades=0),
    )
    analise = _servico(mercado).analyze(
        _pedido(
            BuilderLegInput("PETRK340", _COMPRA, 100), BuilderLegInput("PETRK310", _COMPRA, 100)
        )
    )
    indicativa, teorica = analise.legs
    assert indicativa.origin is LegPriceOrigin.INDICATIVO
    assert teorica.origin is LegPriceOrigin.TEORICO and teorica.price is not None


def test_perna_sem_preco_nenhum_da_resultado_parcial_com_aviso() -> None:
    mercado = _com(serie("PETRK340", 34.0, book=False, last=None, trades=5))
    analise = _servico(mercado).analyze(_pedido(BuilderLegInput("PETRK340", _COMPRA, 100)))
    assert analise.legs[0].price is None
    assert any("PETRK340" in aviso and "sem preço" in aviso for aviso in analise.warnings)
    assert analise.at_expiry is None and analise.today is None
    assert all(p.pnl is None and p.net is None for p in analise.curve)
    assert analise.curve[-1].payoff > 0


def test_aviso_de_quantidade_fora_do_lote() -> None:
    analise = _servico(lotes={"PETRK300": 100}).analyze(
        _pedido(BuilderLegInput("PETRK300", _COMPRA, 150))
    )
    assert analise.legs[0].lot == 100
    assert any("PETRK300" in aviso and "lote de 100" in aviso for aviso in analise.warnings)


def test_serie_fora_da_cadeia_ou_rejeitada_e_erro_claro() -> None:
    with pytest.raises(UnderlyingUnavailableError, match="PETRK999"):
        _servico().analyze(_pedido(BuilderLegInput("PETRK999", _COMPRA, 100)))
    rejeitada = RejectedSeries("PETRK998", "sem estilo de exercício no cadastro")
    mercado = MercadoFalso(chains={"PETR4": cadeia(rejeitadas=(rejeitada,))})
    with pytest.raises(UnderlyingUnavailableError, match="sem estilo"):
        _servico(mercado).analyze(_pedido(BuilderLegInput("PETRK998", _COMPRA, 100)))


def test_estrutura_sem_perna_nenhuma_e_recusada() -> None:
    with pytest.raises(InvalidDomainValueError, match="perna"):
        _servico().analyze(_pedido())


def test_venda_coberta_com_acao_comprada_junto_pelo_ask() -> None:
    analise = _servico().analyze(
        _pedido(
            BuilderLegInput("PETRK320", _VENDA, 100),
            acao=BuilderStockInput(_COMPRA, 100, StockOrigin.COMPRA),
            modelo="venda_coberta",
        )
    )
    assert analise.name == "venda coberta"
    assert analise.stock is not None
    assert (analise.stock.price, analise.stock.price_origin) == (30.01, LegPriceOrigin.EXECUTAVEL)
    premio = analise.legs[0].price
    assert premio is not None and analise.at_expiry is not None
    assert analise.at_expiry.max_gain == pytest.approx(100 * (32.0 - 30.01 + premio), abs=1e-9)
    assert analise.at_expiry.breakevens == pytest.approx((30.01 - premio,), abs=1e-9)


def test_acao_da_carteira_exige_o_preco_medio_e_nao_paga_a_compra() -> None:
    perna = BuilderLegInput("PETRK320", _VENDA, 100)
    with pytest.raises(InvalidDomainValueError, match="preço médio"):
        _servico().analyze(
            _pedido(perna, acao=BuilderStockInput(_COMPRA, 100, StockOrigin.CARTEIRA))
        )
    comprada = _servico().analyze(
        _pedido(perna, acao=BuilderStockInput(_COMPRA, 100, StockOrigin.COMPRA, 30.0))
    )
    da_carteira = _servico().analyze(
        _pedido(perna, acao=BuilderStockInput(_COMPRA, 100, StockOrigin.CARTEIRA, 30.0))
    )
    assert comprada.at_expiry is not None and da_carteira.at_expiry is not None
    perda_comprada, perda_carteira = (
        comprada.at_expiry.net_max_loss,
        da_carteira.at_expiry.net_max_loss,
    )
    assert perda_comprada is not None and perda_carteira is not None
    assert perda_carteira - perda_comprada == pytest.approx(0.0002 * 3000.0 + 5.0, abs=1e-9)


def test_modelo_confere_a_forma_e_modelo_desconhecido_e_recusado() -> None:
    trava = _pedido(
        BuilderLegInput("PETRK300", _COMPRA, 100),
        BuilderLegInput("PETRK320", _VENDA, 100),
        modelo="trava_alta_call",
    )
    assert _servico().analyze(trava).name == "trava de alta com call"
    invertida = _pedido(
        BuilderLegInput("PETRK300", _VENDA, 100),
        BuilderLegInput("PETRK320", _COMPRA, 100),
        modelo="trava_alta_call",
    )
    with pytest.raises(InvalidStrategyError):
        _servico().analyze(invertida)
    with pytest.raises(InvalidDomainValueError, match="calendario"):
        _servico().analyze(_pedido(BuilderLegInput("PETRK300", _COMPRA, 100), modelo="calendario"))


def test_call_americana_avisa_e_tem_curva_de_hoje_rotulada() -> None:
    mercado = _com(serie("PETRA300", 30.0, estilo=ExerciseStyle.AMERICAN))
    analise = _servico(mercado).analyze(_pedido(BuilderLegInput("PETRA300", _COMPRA, 100)))
    assert analise.today is not None and analise.today.american_call_approximated
    assert any("europeia" in aviso for aviso in analise.warnings)
    assert any("exercício antecipado" in aviso for aviso in analise.warnings)


def test_put_americana_fica_sem_curva_de_hoje_mas_tem_o_vencimento() -> None:
    mercado = _com(serie("PETRM300", 30.0, OptionType.PUT, estilo=ExerciseStyle.AMERICAN))
    analise = _servico(mercado).analyze(_pedido(BuilderLegInput("PETRM300", _COMPRA, 100)))
    assert analise.today is None
    assert analise.today_unavailable is not None and "put americana" in analise.today_unavailable
    assert analise.at_expiry is not None


def test_cabecalho_curva_probabilidade_e_grade() -> None:
    mercado = MercadoFalso(healths=[DataSource.ATRASADO])
    analise = _servico(mercado).analyze(
        _pedido(BuilderLegInput("PETRK300", _COMPRA, 100), BuilderLegInput("PETRK320", _VENDA, 100))
    )
    assert (analise.underlying, analise.expiry, analise.source) == (
        "PETR4",
        NOVEMBRO,
        DataSource.ATRASADO,
    )
    assert analise.business_days == CALENDARIO.business_days_between(PREGAO, NOVEMBRO)
    spots = [p.spot for p in analise.curve]
    assert spots == sorted(spots) and {30.0, 32.0} <= set(spots)
    assert analise.at_expiry is not None
    assert set(analise.at_expiry.breakevens) <= set(spots)
    assert 0.0 < analise.at_expiry.probability_of_profit < 1.0
    assert analise.at_expiry.setup_costs > 0.0
    assert analise.today is not None
    assert (len(analise.today.grid.values), len(analise.today.grid.values[0])) == (7, 5)


def test_no_dia_do_vencimento_vale_o_resultado_no_vencimento() -> None:
    mercado = _com(serie("PETRJ280", 28.0, vencimento=PREGAO))
    analise = _servico(mercado).analyze(_pedido(BuilderLegInput("PETRJ280", _COMPRA, 100)))
    assert analise.business_days == 0 and analise.today is None
    assert analise.today_unavailable == "vence hoje: vale o resultado no vencimento"
    assert analise.at_expiry is not None


def test_serie_ausente_com_outra_rejeitada_continua_fora_da_cadeia() -> None:
    rejeitada = RejectedSeries("PETRK998", "sem estilo de exercício no cadastro")
    mercado = MercadoFalso(chains={"PETR4": cadeia(rejeitadas=(rejeitada,))})
    with pytest.raises(UnderlyingUnavailableError, match="fora da cadeia"):
        _servico(mercado).analyze(_pedido(BuilderLegInput("PETRK999", _COMPRA, 100)))

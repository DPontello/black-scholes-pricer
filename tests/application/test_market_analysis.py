"""``MarketAnalysisService`` com a cadeia falsa (PETR4 a 30, vol 30%) e históricos falsos."""

from dataclasses import replace
from datetime import date, timedelta

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.application.ports.inbound import MarketAnalysisUseCase
from options_engine.application.use_cases.market_analysis import MarketAnalysisService
from options_engine.domain.analytics.volatility import DailyVol, VolRegime, iv_percentile, iv_rank
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.quotes import DataSource
from tests.application._book_falso import Historicos, HistoricosFalsos, historico
from tests.application._mercado_falso import CALENDARIO, NOVEMBRO, PREGAO, MercadoFalso, cadeia
from tests.book._cadeias import DEZEMBRO, cadeia_larga, du, series_do_vencimento


def _servico(
    chain: OptionChain | None = None,
    historicos: Historicos | None = None,
    healths: list[DataSource] | None = None,
) -> MarketAnalysisService:
    mercado = MercadoFalso(chains={"PETR4": chain or cadeia_larga()}, healths=healths or [])
    padrao: Historicos = {"PETR4": historico(0.30, 0.40)}
    return MarketAnalysisService(
        mercado,
        HistoricosFalsos(padrao if historicos is None else historicos),
        CALENDARIO,
        B3_UTC_OFFSET,
    )


def test_cumpre_o_protocolo() -> None:
    assert isinstance(_servico(), MarketAnalysisUseCase)


def test_estrutura_a_termo_e_smile_pela_cadeia_do_momento() -> None:
    analise = _servico().analysis("PETR4")

    assert [(t.expiry, t.business_days) for t in analise.term_structure] == [
        (NOVEMBRO, du(NOVEMBRO)),
        (DEZEMBRO, du(DEZEMBRO)),
    ]
    assert all(abs(t.vol - 0.30) < 0.005 for t in analise.term_structure)
    novembro = analise.smiles[0]
    assert novembro.expiry == NOVEMBRO
    assert [p.strike for p in novembro.points] == [26.0, 28.0, 30.0, 32.0, 34.0]
    # Abaixo do spot, a put (fora do dinheiro); acima, a call.
    assert novembro.points[0].symbol == "PETRW260"
    assert novembro.points[-1].symbol == "PETRK340"
    assert (analise.spot, analise.cdi_annual) == (30.0, 0.15)


def test_iv_30_de_hoje_contra_o_historico_de_fim_de_dia() -> None:
    """Histórico de 31% a 40% antes do pregão; a IV 30 de hoje (perto de 30%) fica abaixo de
    todos: rank 0. O pregão de hoje no histórico não entra na comparação."""
    analise = _servico().analysis("PETR4")

    hoje = analise.today
    assert hoje is not None and analise.today_reason is None
    assert abs(hoje.iv30 - 0.30) < 0.005
    passados = [d.iv30 for d in analise.history if d.session < PREGAO and d.iv30 is not None]
    assert len(passados) == 100
    assert hoje.iv_rank == iv_rank(passados, hoje.iv30) == 0.0
    assert hoje.iv_percentile == iv_percentile(passados, hoje.iv30)
    assert hoje.hv21 == 0.40
    assert (hoje.regime, hoje.regime_from_hv) == (VolRegime.BAIXA, False)
    assert len(analise.history) == 101 and analise.history_reason is None


def test_rank_no_meio_do_historico_e_hv_do_ultimo_pregao_que_a_tem() -> None:
    """200 pregões de 20% a 39,9%; o último sem HV: vale a HV do anterior."""
    meio = tuple(
        DailyVol(date(2026, 1, 1) + timedelta(days=i), 30.0, 0.20 + i / 1000, False, 0.3 + i / 1e4)
        for i in range(200)
    )
    meio = (*meio[:-1], replace(meio[-1], hv21=None))
    hoje = _servico(historicos={"PETR4": meio}).analysis("PETR4").today
    assert hoje is not None
    assert hoje.iv_rank == iv_rank([d.iv30 for d in meio if d.iv30 is not None], hoje.iv30)
    assert hoje.iv_rank is not None and 0.45 < hoje.iv_rank < 0.55
    assert hoje.hv21 == meio[-2].hv21


def test_sem_historico_diz_o_motivo_e_mostra_o_resto() -> None:
    analise = _servico(historicos={}).analysis("PETR4")

    assert (analise.history, analise.history_reason) == ((), "PETR4: sem histórico")
    assert analise.term_structure and analise.smiles
    hoje = analise.today
    assert hoje is not None
    assert hoje.iv_rank is None and hoje.regime_from_hv is True
    assert hoje.hv21 == 0.25  # a vol realizada que a cadeia traz


def test_sem_smile_no_spot_nao_ha_iv_de_hoje() -> None:
    longe = cadeia(series_do_vencimento(strikes=(34.0,)))
    analise = _servico(chain=longe).analysis("PETR4")
    assert analise.today is None and analise.term_structure == ()
    assert analise.today_reason == "PETR4: sem IV 30 hoje (nenhum vencimento com smile no spot)"


def test_fonte_e_a_menos_fresca_da_consulta() -> None:
    analise = _servico(healths=[DataSource.AO_VIVO, DataSource.FIM_DE_DIA]).analysis("PETR4")
    assert analise.source is DataSource.FIM_DE_DIA


def test_vencimento_vencido_ou_fora_do_calendario_fica_fora() -> None:
    base = cadeia_larga()
    modelo = base.quotes[0]
    extras = tuple(
        replace(
            modelo,
            contract=replace(
                modelo.contract, symbol=simbolo, terms=replace(modelo.contract.terms, expiry=dia)
            ),
        )
        for simbolo, dia in (
            ("PETRA300", date(2028, 1, 21)),
            ("PETRJ300", date(2026, 10, 16)),
            ("PETRJ310", PREGAO),
        )
    )
    analise = _servico(chain=replace(base, quotes=(*base.quotes, *extras))).analysis("PETR4")
    assert [s.expiry for s in analise.smiles] == [NOVEMBRO, DEZEMBRO]

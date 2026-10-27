"""Gráfico de payoff em SVG — posições das marcas, curvas, escape e determinismo."""

import re
from dataclasses import replace
from pathlib import Path

import pytest

from options_engine.adapters.inbound.html_report import render_income_report
from options_engine.adapters.inbound.payoff_svg import PLOT_LEFT, PLOT_RIGHT, render_payoff_svg
from options_engine.application.ports.inbound import RankIncomeCommand
from options_engine.config.composition import build_income_panel
from options_engine.domain.income.ranking import IncomeCandidate, IncomeRanking, RankingCriterion
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME, REFERENCE_SESSION

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "cotahist"


@pytest.fixture(scope="module")
def ranking() -> IncomeRanking:
    painel = build_income_panel(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
    )
    return painel.execute(RankIncomeCommand(("PETR4", "VALE3")))


def _x_esperado(candidato: IncomeCandidate, preco: float) -> str:
    """Posição pela definição do eixo (0,5 a 1,5 x spot sobre a área útil), sem ``x_of``."""
    spot = candidato.profile.current_spot
    x = PLOT_LEFT + (preco - 0.5 * spot) / spot * (PLOT_RIGHT - PLOT_LEFT)
    return f"{x:.1f}"


def _x_da_linha(svg: str, classe: str) -> str:
    achado = re.search(rf'<line class="{classe}" x1="([0-9.]+)"', svg)
    assert achado is not None, f"linha {classe} ausente"
    return achado.group(1)


def test_breakevens_nas_posicoes_certas(ranking: IncomeRanking) -> None:
    for candidato in ranking.ranked:
        svg = render_payoff_svg(candidato, title="t", chart_id="c")
        m = candidato.metrics
        assert _x_da_linha(svg, "be-bruto") == _x_esperado(candidato, m.breakeven)
        assert m.net_breakeven is not None
        assert _x_da_linha(svg, "be-liquido") == _x_esperado(candidato, m.net_breakeven)
        assert _x_da_linha(svg, "spot") == _x_esperado(candidato, candidato.profile.current_spot)


def test_breakeven_cruza_o_zero_da_curva_liquida(ranking: IncomeRanking) -> None:
    """No x do breakeven líquido, a polyline líquida passa pela linha do zero."""
    candidato = ranking.ranked[0]
    svg = render_payoff_svg(candidato, title="t", chart_id="c")
    zero = re.search(r'<line class="zero" x1="[0-9.]+" y1="([0-9.]+)"', svg)
    assert zero is not None
    pontos = re.search(r'<polyline class="liquido" points="([^"]+)"', svg)
    assert pontos is not None
    pares = [tuple(map(float, par.split(","))) for par in pontos.group(1).split()]
    x_be = float(_x_esperado(candidato, candidato.metrics.net_breakeven or 0.0))
    (y_no_be,) = [py for px, py in pares if abs(px - x_be) < 0.051]
    assert abs(y_no_be - float(zero.group(1))) <= 0.1


def test_curvas_bruta_e_liquida_com_um_vertice_por_ponto_do_perfil(ranking: IncomeRanking) -> None:
    candidato = ranking.ranked[0]
    svg = render_payoff_svg(candidato, title="t", chart_id="c")
    for classe in ("bruto", "liquido"):
        pontos = re.search(rf'<polyline class="{classe}" points="([^"]+)"', svg)
        assert pontos is not None
        assert len(pontos.group(1).split()) == len(candidato.profile.points)
    assert svg.count('<line class="strike"') == len({leg.strike for leg in candidato.legs})
    assert '<line class="ganho-max"' in svg and '<line class="perda-max"' in svg


def test_titulo_acessivel_e_escapado(ranking: IncomeRanking) -> None:
    svg = render_payoff_svg(ranking.ranked[0], title='<b>"x"</b>', chart_id='c"1')
    assert 'role="img"' in svg
    assert '<title id="c&quot;1-titulo">&lt;b&gt;&quot;x&quot;&lt;/b&gt;</title>' in svg
    assert "<b>" not in svg


def test_sem_breakeven_liquido_nao_ha_marca(ranking: IncomeRanking) -> None:
    candidato = ranking.ranked[0]
    sem_be = replace(candidato, metrics=replace(candidato.metrics, net_breakeven=None))
    svg = render_payoff_svg(sem_be, title="t", chart_id="c")
    assert 'class="be-liquido"' not in svg
    assert 'class="be-bruto"' in svg


def test_marca_fora_do_eixo_e_omitida(ranking: IncomeRanking) -> None:
    candidato = ranking.ranked[0]
    longe = replace(candidato, metrics=replace(candidato.metrics, breakeven=1000.0))
    assert 'class="be-bruto"' not in render_payoff_svg(longe, title="t", chart_id="c")


def test_mesma_entrada_mesmos_bytes(ranking: IncomeRanking) -> None:
    candidato = ranking.ranked[0]
    assert render_payoff_svg(candidato, title="t", chart_id="c") == render_payoff_svg(
        candidato, title="t", chart_id="c"
    )


def test_painel_tem_um_grafico_recolhivel_por_linha_do_ranking(ranking: IncomeRanking) -> None:
    html = render_income_report(ranking, {})
    assert html.count("<details>") == len(ranking.ranked)
    assert html.count("<svg ") == len(ranking.ranked)
    assert "<h2>Gráficos de payoff do ranking</h2>" in html
    assert "<script" not in html.lower()


def test_painel_sem_ranking_avisa_que_nao_ha_grafico() -> None:
    vazio = IncomeRanking(RankingCriterion.NET_ANNUAL_YIELD, (), (), (), ())
    assert "Sem estruturas no ranking." in render_income_report(vazio, {})

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


# Estimativa CONSERVADORA da largura de um caractere a font-size 10 numa
# fonte sans-serif (dígitos e minúsculas ficam em torno de 5,5 px). Própria
# do teste: não reaproveita a constante do adapter, para não validar a
# implementação contra ela mesma.
_LARGURA_POR_CARACTERE = 6.0
_COR_DA_GRADE = "#d0d7de"


def _rotulos_do_eixo(svg: str) -> list[tuple[str, float, float, str]]:
    """(texto, x, y, cor) dos rótulos do eixo de preço — os únicos centralizados."""
    return [
        (texto, float(x), float(y), cor)
        for x, y, cor, texto in re.findall(
            r'<text [^>]*x="([0-9.]+)" y="([0-9.]+)"[^>]*fill="([^"]+)"[^>]*'
            r'text-anchor="middle"[^>]*>([^<]+)</text>',
            svg,
        )
    ]


def _assert_rotulos_legiveis(svg: str) -> None:
    caixa = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', svg)
    assert caixa is not None
    largura, altura = float(caixa.group(1)), float(caixa.group(2))
    rotulos = _rotulos_do_eixo(svg)
    assert rotulos, "nenhum rótulo no eixo de preço"
    extensoes = []
    for texto, x, y, _ in rotulos:
        meia = len(texto) * _LARGURA_POR_CARACTERE / 2
        assert x - meia >= 0.0 and x + meia <= largura, f"{texto!r} sai do desenho"
        assert y <= altura, f"{texto!r} abaixo da altura do SVG"
        extensoes.append((texto, y, x - meia, x + meia))
    for i, (a, ya, esq_a, dir_a) in enumerate(extensoes):
        for b, yb, esq_b, dir_b in extensoes[i + 1 :]:
            if ya == yb:
                assert dir_a <= esq_b or dir_b <= esq_a, f"{a!r} sobrepõe {b!r} em y={ya}"


def test_rotulos_do_eixo_nao_se_sobrepoem(ranking: IncomeRanking) -> None:
    """Na fixture, strikes, spot e breakevens ficam a poucos px: precisam empilhar."""
    for candidato in ranking.ranked:
        _assert_rotulos_legiveis(render_payoff_svg(candidato, title="t", chart_id="c"))


def test_marcas_no_mesmo_preco_ocupam_linhas_distintas(ranking: IncomeRanking) -> None:
    candidato = ranking.ranked[0]
    spot = candidato.profile.current_spot
    mesmas = replace(
        candidato, metrics=replace(candidato.metrics, breakeven=spot, net_breakeven=spot)
    )
    svg = render_payoff_svg(mesmas, title="t", chart_id="c")
    _assert_rotulos_legiveis(svg)
    linhas = {y for texto, _, y, _ in _rotulos_do_eixo(svg) if texto.startswith(("spot", "BE"))}
    assert len(linhas) == 3


def test_rotulo_na_borda_do_eixo_fica_dentro_do_desenho(ranking: IncomeRanking) -> None:
    candidato = ranking.ranked[0]
    pontos = candidato.profile.points
    nas_bordas = replace(
        candidato,
        metrics=replace(candidato.metrics, breakeven=pontos[-1].spot, net_breakeven=pontos[0].spot),
    )
    _assert_rotulos_legiveis(render_payoff_svg(nas_bordas, title="t", chart_id="c"))


def test_rotulo_de_strike_nao_usa_a_cor_da_grade(ranking: IncomeRanking) -> None:
    """A linha do strike é clara de propósito; o texto precisa de contraste."""
    svg = render_payoff_svg(ranking.ranked[0], title="t", chart_id="c")
    strikes = [cor for texto, _, _, cor in _rotulos_do_eixo(svg) if texto.startswith("K ")]
    assert strikes and _COR_DA_GRADE not in strikes


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

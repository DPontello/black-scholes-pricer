"""Painel HTML — determinismo, escape de texto externo, formatação pt-BR e seções (ADR-0007)."""

from datetime import date
from pathlib import Path

import pytest

from options_engine.adapters.inbound.html_report import render_income_report
from options_engine.application.ports.inbound import RankIncomeCommand
from options_engine.config.composition import build_income_panel
from options_engine.domain.income import IncomeStructure
from options_engine.domain.income.ranking import (
    Exclusion,
    ExclusionScope,
    IncomeRanking,
    RankingCriterion,
)
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME, REFERENCE_SESSION

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "cotahist"
PARAMETROS = {"Pregão": "23/10/2026", "Ativos": "PETR4, VALE3"}


@pytest.fixture(scope="module")
def ranking() -> IncomeRanking:
    painel = build_income_panel(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
    )
    return painel.execute(RankIncomeCommand(("PETR4", "VALE3", "ITUB4")))


def test_mesma_entrada_mesmos_bytes(ranking: IncomeRanking) -> None:
    assert render_income_report(ranking, PARAMETROS) == render_income_report(ranking, PARAMETROS)


def test_sem_data_de_geracao_por_padrao_e_com_ela_so_se_passada(ranking: IncomeRanking) -> None:
    assert "gerado em" not in render_income_report(ranking, PARAMETROS)
    com = render_income_report(ranking, PARAMETROS, generated_on=date(2026, 10, 24))
    assert "gerado em 24/10/2026" in com


def test_secoes_e_contagens(ranking: IncomeRanking) -> None:
    html = render_income_report(ranking, PARAMETROS)
    assert html.startswith("<!DOCTYPE html>")
    for secao in ("Parâmetros", "Ativos", "Tabela de custos usada", "Notas"):
        assert f"<h2>{secao}</h2>" in html
    assert f"<h2>Ranking — executável ({len(ranking.ranked)})</h2>" in html
    assert f"Referências — indicativo e teórico ({len(ranking.references)})" in html
    assert f"<h2>Exclusões ({len(ranking.exclusions)})</h2>" in html
    assert "ordenado por rendimento anualizado líquido" in html


def test_sem_javascript_nem_recurso_externo(ranking: IncomeRanking) -> None:
    html = render_income_report(ranking, PARAMETROS).lower()
    assert "<script" not in html
    assert "http://" not in html and "https://" not in html
    assert "<link" not in html


def test_marcas_qualidades_e_notas(ranking: IncomeRanking) -> None:
    html = render_income_report(ranking, PARAMETROS)
    assert "aprox. americana (ADR-0002)" in html
    assert "ativo sem ofertas" in html
    assert 'class="q-executavel"' in html
    assert 'class="q-indicativo"' in html
    assert 'class="q-teorico"' in html
    assert "probabilidade RISCO-NEUTRA" in html
    assert "ESTIMATIVA por operação" in html


def test_formatacao_pt_br(ranking: IncomeRanking) -> None:
    html = render_income_report(ranking, PARAMETROS)
    assert "<td>23/10/2026</td>" in html  # pregão
    assert "<td>30,00</td>" in html  # spot de PETR4
    assert "<td>15,00%</td>" in html  # CDI
    assert "0,1340% por perna" in html
    assert "-R$ " in html and "R$ -" not in html  # perda máxima
    assert "R$ 5.568,00" in html  # milhar com ponto


def test_texto_externo_e_escapado(ranking: IncomeRanking) -> None:
    maliciosa = Exclusion(
        ExclusionScope.SERIES, "PETR<K>&1", "motivo <script>alert('x')</script> & cia"
    )
    adulterado = IncomeRanking(
        criterion=RankingCriterion.NET_ANNUAL_YIELD,
        ranked=ranking.ranked,
        references=ranking.references,
        exclusions=(maliciosa,),
        underlyings=ranking.underlyings,
    )
    html = render_income_report(adulterado, {"Arquivo": "<img src=x onerror=1>"})
    assert "<script>" not in html
    assert "&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt; &amp; cia" in html
    assert "PETR&lt;K&gt;&amp;1" in html
    assert "&lt;img src=x onerror=1&gt;" in html


def test_secoes_vazias_tem_mensagem() -> None:
    vazio = IncomeRanking(RankingCriterion.GROSS_PERIOD_YIELD, (), (), (), ())
    html = render_income_report(vazio, {})
    assert "Nenhuma estrutura executável dentro dos filtros." in html
    assert "Nenhuma referência." in html
    assert "Nenhuma exclusão." in html
    assert "Nenhum ativo com cadeia no pregão." in html
    assert "nenhum pregão com dados" in html
    assert "ordenado por rendimento no período bruto" in html


def test_rotulos_das_duas_travas() -> None:
    painel = build_income_panel(
        session_date=REFERENCE_SESSION,
        cotahist_paths=[FIXTURE / COTAHIST_NAME],
        instruments_path=FIXTURE / INSTRUMENTS_NAME,
    )
    command = RankIncomeCommand(
        ("PETR4",),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        delta_min=0.0,
        delta_max=1.0,
    )
    html = render_income_report(painel.execute(command), PARAMETROS)
    assert "Trava de alta com put" in html
    assert "Trava de baixa com call" in html

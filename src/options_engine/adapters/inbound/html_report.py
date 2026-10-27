"""Painel de Renda em HTML estático — adapter de apresentação (ADR-0007, plano da fase 2 §4).

Só apresenta: tudo o que aparece já vem decidido pelo ``IncomeRanking``
(qualidade, ranking só EXECUTAVEL, referências, exclusões com motivo).
Conversões de EXIBIÇÃO vivem só aqui (decisão nº 8): percentuais e números
em pt-BR (vírgula decimal, ponto de milhar), moeda com 2 casas, du inteiros,
datas dd/mm/aaaa.

Segurança e reprodutibilidade:

- ``html.escape`` em TODO texto vindo de dados (tickers, motivos de
  exclusão, nomes de arquivo nos parâmetros) — um motivo com ``<script>``
  vira texto;
- CSS inline, sem JavaScript, sem recurso externo;
- saída determinística: a mesma entrada produz os mesmos bytes. Não há "gerado
  em" com relógio; a data de geração só aparece se for passada explicitamente.
"""

from collections.abc import Callable, Iterable, Mapping
from datetime import date
from html import escape
from typing import Final

from options_engine.adapters.inbound.payoff_svg import render_payoff_svg
from options_engine.domain.income.metrics import IncomeMetrics, IncomeStructure
from options_engine.domain.income.ranking import (
    CandidateLeg,
    Exclusion,
    IncomeCandidate,
    IncomeRanking,
    RankingCriterion,
    UnderlyingSummary,
)
from options_engine.domain.model.chain import PriceQuality
from options_engine.domain.model.enums import OptionType

__all__ = ["render_income_report"]

_TRACO: Final = "—"
_CRITERIOS: Final = {
    RankingCriterion.NET_ANNUAL_YIELD: "rendimento anualizado líquido",
    RankingCriterion.GROSS_ANNUAL_YIELD: "rendimento anualizado bruto",
    RankingCriterion.NET_PERIOD_YIELD: "rendimento no período líquido",
    RankingCriterion.GROSS_PERIOD_YIELD: "rendimento no período bruto",
    RankingCriterion.NET_EXCESS_OVER_CDI: "excesso líquido sobre o CDI",
}
_QUALIDADES: Final = {
    PriceQuality.EXECUTAVEL: "executável",
    PriceQuality.INDICATIVO: "indicativo",
    PriceQuality.TEORICO: "teórico",
}
_CSS: Final = """
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:24px;color:#1f2328;
background:#ffffff;font-size:14px;line-height:1.45}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:17px;margin:28px 0 8px;border-bottom:1px solid #d0d7de;padding-bottom:4px}
.sub{color:#57606a;margin:0 0 16px}
table{border-collapse:collapse;font-variant-numeric:tabular-nums}
th,td{border:1px solid #d0d7de;padding:4px 7px;text-align:right;white-space:nowrap}
th{background:#f6f8fa;font-weight:600;text-align:center}
td.t{text-align:left}
.rolagem{overflow-x:auto;max-width:100%}
.q-executavel{color:#1a7f37}.q-indicativo{color:#9a6700}.q-teorico{color:#8250df}
.marca{display:inline-block;padding:0 6px;border-radius:9px;background:#fff8c5;color:#633c01;
font-size:12px;margin-right:4px}
details{margin:6px 0}summary{cursor:pointer}details svg{display:block;margin:6px 0}
dl{display:grid;grid-template-columns:max-content auto;gap:2px 16px;margin:0}
dt{color:#57606a}dd{margin:0}
ul.notas li{margin-bottom:4px}
"""


# ---------------------------------------------------------------------------
# Formatação pt-BR (decisão nº 8: conversões de exibição só no adapter)
# ---------------------------------------------------------------------------


def _numero(valor: float, casas: int = 2) -> str:
    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _pct(valor: float | None, casas: int = 2) -> str:
    return _TRACO if valor is None else f"{_numero(100.0 * valor, casas)}%"


def _moeda(valor: float) -> str:
    sinal = "-" if valor < 0.0 else ""
    return f"{sinal}R$ {_numero(abs(valor))}"


def _preco(valor: float | None) -> str:
    return _TRACO if valor is None else _numero(valor)


def _data(valor: date) -> str:
    return valor.strftime("%d/%m/%Y")


def _e(texto: object) -> str:
    """Escape de TODO texto vindo de dados."""
    return escape(str(texto), quote=True)


# ---------------------------------------------------------------------------
# Rótulos
# ---------------------------------------------------------------------------


def _estrutura(candidato: IncomeCandidate) -> str:
    if candidato.structure is IncomeStructure.CASH_SECURED_PUT:
        return "Put coberta"
    if candidato.structure is IncomeStructure.COVERED_CALL:
        return "Venda coberta"
    if candidato.legs[0].option_type is OptionType.PUT:
        return "Trava de alta com put"
    return "Trava de baixa com call"


def _qualidade(qualidade: PriceQuality) -> str:
    return f'<span class="q-{qualidade.value}">{_QUALIDADES[qualidade]}</span>'


def _marcas(candidato: IncomeCandidate) -> str:
    marcas = []
    if candidato.approximations:
        marcas.append("aprox. americana (ADR-0002)")
    if not candidato.underlying_book_available:
        marcas.append("ativo sem ofertas")
    return "".join(f'<span class="marca">{_e(m)}</span>' for m in marcas) or _TRACO


def _pernas(candidato: IncomeCandidate, campo: str) -> str:
    """Um valor por perna (vendida primeiro), separados por " / "."""
    formatos: dict[str, Callable[[CandidateLeg], str]] = {
        "serie": lambda p: _e(p.symbol),
        "premio": lambda p: f"{_preco(p.premium.premium)} {_qualidade(p.premium.quality)}",
        "delta": lambda p: _numero(p.delta, 3),
        "nd2": lambda p: _pct(p.exercise_probability, 1),
        "iv": lambda p: _pct(p.implied_vol, 1),
        "negocios": lambda p: _numero(p.trades, 0),
        "volume": lambda p: _moeda(p.volume),
        "spread": lambda p: _pct(p.spread_pct, 1),
    }
    formatar = formatos[campo]
    return " / ".join(formatar(perna) for perna in candidato.legs)


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------

_COLUNAS: Final = (
    "Ativo",
    "Estrutura",
    "Série(s)",
    "Vencimento",
    "du",
    "Prêmio da estrutura",
    "Prêmio por perna",
    "Rend. período bruto",
    "Rend. período líquido",
    "Anualizado bruto",
    "Anualizado líquido",
    "Excesso s/ CDI (líq.)",
    "Retorno s/ risco",
    "Proteção",
    "Breakeven bruto",
    "Breakeven líquido",
    "Ganho máx. bruto",
    "Ganho máx. líquido",
    "Perda máx. bruta",
    "Perda máx. líquida",
    "Delta",
    "N(d2)",
    "IV",
    "Vol realizada",
    "Negócios",
    "Volume",
    "Spread",
    "Marcas",
)


def _linha(candidato: IncomeCandidate, vols: Mapping[str, float]) -> str:
    m: IncomeMetrics = candidato.metrics
    trava = candidato.structure is IncomeStructure.CREDIT_SPREAD
    celulas = [
        ("t", _e(candidato.underlying)),
        ("t", _e(_estrutura(candidato))),
        ("t", _pernas(candidato, "serie")),
        ("", _data(candidato.expiry)),
        ("", str(m.business_days)),
        ("", f"{_preco(m.premium_per_share)} {_qualidade(candidato.quality)}"),
        ("", _pernas(candidato, "premio")),
        ("", _pct(m.yield_period)),
        ("", _pct(m.net_yield_period)),
        ("", _pct(m.yield_annual_252)),
        ("", _pct(m.net_yield_annual_252)),
        ("", _pct(m.net_excess_over_cdi_annual_252)),
        ("", _pct(m.yield_period) if trava else _TRACO),
        ("", _pct(m.downside_protection)),
        ("", _preco(m.breakeven)),
        ("", _preco(m.net_breakeven)),
        ("", _moeda(m.max_gain_per_position)),
        ("", _moeda(m.net_max_gain_per_position)),
        ("", _moeda(m.max_loss_per_position)),
        ("", _moeda(m.net_max_loss_per_position)),
        ("", _pernas(candidato, "delta")),
        ("", _pernas(candidato, "nd2")),
        ("", _pernas(candidato, "iv")),
        ("", _pct(vols.get(candidato.underlying), 1)),
        ("", _pernas(candidato, "negocios")),
        ("", _pernas(candidato, "volume")),
        ("", _pernas(candidato, "spread")),
        ("t", _marcas(candidato)),
    ]
    return (
        "<tr>"
        + "".join(
            f'<td class="{classe}">{valor}</td>' if classe else f"<td>{valor}</td>"
            for classe, valor in celulas
        )
        + "</tr>"
    )


def _tabela(candidatos: Iterable[IncomeCandidate], vols: Mapping[str, float], vazio: str) -> str:
    linhas = [_linha(c, vols) for c in candidatos]
    if not linhas:
        return f"<p>{_e(vazio)}</p>"
    cabecalho = "".join(f"<th>{_e(c)}</th>" for c in _COLUNAS)
    return (
        '<div class="rolagem"><table><thead><tr>'
        + cabecalho
        + "</tr></thead><tbody>"
        + "".join(linhas)
        + "</tbody></table></div>"
    )


def _graficos(candidatos: tuple[IncomeCandidate, ...]) -> str:
    """Um gráfico de payoff recolhível por linha do ranking, na ordem do ranking."""
    if not candidatos:
        return "<p>Sem estruturas no ranking.</p>"
    blocos = []
    for posicao, candidato in enumerate(candidatos, start=1):
        rotulo = (
            f"{posicao}. {candidato.underlying} · {_estrutura(candidato)} · "
            f"{' / '.join(leg.symbol for leg in candidato.legs)} · {_data(candidato.expiry)}"
        )
        svg = render_payoff_svg(
            candidato,
            title=f"Resultado no vencimento: {rotulo}",
            chart_id=f"payoff-{posicao}",
        )
        blocos.append(f"<details><summary>{_e(rotulo)}</summary>{svg}</details>")
    return "".join(blocos)


def _ativos(resumos: Iterable[UnderlyingSummary]) -> str:
    linhas = []
    for r in resumos:
        tabela = r.cost_schedule
        linhas.append(
            "<tr>"
            f'<td class="t">{_e(r.symbol)}</td>'
            f"<td>{_data(r.session)}</td>"
            f"<td>{_preco(r.spot)}</td>"
            f"<td>{_pct(r.realized_vol, 1)}</td>"
            f'<td class="t">{"sim" if r.book_available else "sem ofertas"}</td>'
            f"<td>{_pct(r.cdi.rate)}</td>"
            f"<td>{_data(tabela.valid_from)}</td>"
            "</tr>"
        )
    if not linhas:
        return "<p>Nenhum ativo com cadeia no pregão.</p>"
    cabecalho = "".join(
        f"<th>{c}</th>"
        for c in (
            "Ativo",
            "Pregão",
            "Spot",
            "Vol realizada",
            "Book do ativo",
            "CDI (efetivo a.a.)",
            "Tabela de custos (vigência)",
        )
    )
    return f"<table><thead><tr>{cabecalho}</tr></thead><tbody>{''.join(linhas)}</tbody></table>"


def _custos(resumos: tuple[UnderlyingSummary, ...]) -> str:
    tabelas = sorted({r.cost_schedule for r in resumos}, key=lambda t: t.valid_from)
    itens = []
    for t in tabelas:
        itens.append(
            f"<li>vigente desde {_data(t.valid_from)}: emolumentos de opções "
            f"{_pct(t.option_exchange_fee_rate, 4)} por perna; à vista e exercício "
            f"{_pct(t.spot_exchange_fee_rate, 4)}; corretagem {_moeda(t.brokerage_per_order)} "
            f"por ordem e {_moeda(t.exercise_brokerage_per_order)} por exercício; IR estimado "
            f"{_pct(t.income_tax_rate, 1)}</li>"
        )
    return "<ul>" + "".join(itens) + "</ul>" if itens else "<p>—</p>"


def _exclusoes(exclusoes: tuple[Exclusion, ...]) -> str:
    if not exclusoes:
        return "<p>Nenhuma exclusão.</p>"
    linhas = "".join(
        f'<tr><td class="t">{_e(x.scope.value)}</td><td class="t">{_e(x.symbol)}</td>'
        f'<td class="t">{_e(x.reason)}</td></tr>'
        for x in exclusoes
    )
    return (
        '<div class="rolagem"><table><thead><tr><th>Nível</th><th>Símbolo</th><th>Motivo</th>'
        f"</tr></thead><tbody>{linhas}</tbody></table></div>"
    )


def _parametros(parametros: Mapping[str, str]) -> str:
    itens = "".join(f"<dt>{_e(k)}</dt><dd>{_e(v)}</dd>" for k, v in parametros.items())
    return f"<dl>{itens}</dl>"


_NOTAS: Final = (
    "O ranking contém só estruturas com preço EXECUTÁVEL: a perna vendida pelo melhor bid e a "
    "comprada pelo melhor ask (ADR-0004). Referências INDICATIVO (último negócio, book vazio) e "
    "TEÓRICO (Black-Scholes com a vol do smile, sem negócio) nunca entram no ranking.",
    "O IR é uma ESTIMATIVA por operação (15% sobre o resultado positivo, só sobre o prêmio na "
    "venda coberta), não cálculo fiscal: sem apuração mensal nem compensação de prejuízos.",
    "N(d2) é a probabilidade RISCO-NEUTRA de exercício, não a probabilidade real.",
    "Retorno sobre risco das travas usa a largura entre strikes como proxy do risco; a margem da "
    "B3 não é modelada. A anualização é composta em dias úteis (252).",
    "Marca 'aprox. americana': call americana precificada como europeia (ADR-0002), válida sem "
    "dividendos e com o strike ajustado por proventos.",
    "Marca 'ativo sem ofertas': o ativo-objeto não teve ofertas no pregão; spot = fechamento e "
    "nenhuma métrica usa o book dele (ADR-0004).",
    "Dados de fim de dia (COTAHIST): os preços não são ajustados por proventos, e o último "
    "negócio de uma opção pode ser bem anterior ao fechamento da ação.",
)


def render_income_report(
    ranking: IncomeRanking,
    parameters: Mapping[str, str],
    *,
    generated_on: date | None = None,
) -> str:
    """O painel completo como texto HTML; mesma entrada, mesmos bytes.

    ``parameters``: parâmetros do comando como o usuário os deu, já em texto
    (rótulo -> valor), exibidos no cabeçalho e escapados.
    """
    vols = {r.symbol: r.realized_vol for r in ranking.underlyings}
    pregoes = sorted({r.session for r in ranking.underlyings})
    subtitulo = (
        "pregão " + ", ".join(_data(p) for p in pregoes) if pregoes else "nenhum pregão com dados"
    )
    if generated_on is not None:
        subtitulo += f" · gerado em {_data(generated_on)}"
    partes = [
        "<!DOCTYPE html>",
        '<html lang="pt-BR"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Painel de Renda</title>",
        f"<style>{_CSS.strip()}</style></head><body>",
        "<h1>Painel de Renda com Opções</h1>",
        f'<p class="sub">{_e(subtitulo)} · ordenado por {_e(_CRITERIOS[ranking.criterion])}</p>',
        "<h2>Parâmetros</h2>",
        _parametros(parameters),
        "<h2>Ativos</h2>",
        _ativos(ranking.underlyings),
        "<h2>Tabela de custos usada</h2>",
        _custos(ranking.underlyings),
        f"<h2>Ranking — executável ({len(ranking.ranked)})</h2>",
        _tabela(ranking.ranked, vols, "Nenhuma estrutura executável dentro dos filtros."),
        "<h2>Gráficos de payoff do ranking</h2>",
        "<p>Resultado por posição no vencimento, em função do preço do ativo-objeto: payoff "
        "bruto e resultado líquido de custos e IR estimado.</p>",
        _graficos(ranking.ranked),
        f"<h2>Referências — indicativo e teórico ({len(ranking.references)})</h2>",
        _tabela(ranking.references, vols, "Nenhuma referência."),
        f"<h2>Exclusões ({len(ranking.exclusions)})</h2>",
        _exclusoes(ranking.exclusions),
        "<h2>Notas</h2>",
        '<ul class="notas">' + "".join(f"<li>{_e(n)}</li>" for n in _NOTAS) + "</ul>",
        "</body></html>",
    ]
    return "\n".join(partes) + "\n"

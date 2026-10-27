"""Gráfico de payoff de uma oportunidade em SVG inline — só desenha (plano da fase 2 §4).

Os pontos vêm prontos do domínio (``IncomeCandidate.profile``, mesmo modelo
de custos das métricas); aqui só há escala, coordenadas e rótulos. Stdlib,
sem JavaScript e sem lib de gráfico. Coordenadas arredondadas a 0,1 px: a
mesma entrada produz os mesmos bytes.

Elementos: curva BRUTA (payoff no vencimento) e LÍQUIDA (montagem, exercício
e IR do cenário); linha do zero; spot atual; strikes; breakeven bruto e
líquido; ganho e perda máximos líquidos. Cores com rótulo em texto e
``<title>`` acessível — a cor nunca é a única pista.
"""

from collections.abc import Callable
from html import escape
from typing import Final

from options_engine.domain.income.ranking import IncomeCandidate

__all__ = ["CHART_HEIGHT", "CHART_WIDTH", "PLOT_LEFT", "PLOT_RIGHT", "render_payoff_svg", "x_of"]

CHART_WIDTH: Final = 640
CHART_HEIGHT: Final = 260
PLOT_LEFT: Final = 72.0
PLOT_RIGHT: Final = 624.0
_PLOT_TOP: Final = 24.0
_PLOT_BOTTOM: Final = 224.0
_GROSS: Final = "#0969da"
_NET: Final = "#bc4c00"
_NEUTRAL: Final = "#57606a"
_GRID: Final = "#d0d7de"


def _n(valor: float) -> str:
    """Coordenada com 0,1 px de resolução (saída determinística)."""
    texto = f"{valor:.1f}"
    return "0.0" if texto == "-0.0" else texto


def _br(valor: float) -> str:
    texto = f"{valor:,.2f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _moeda(valor: float) -> str:
    """Moeda pt-BR com o sinal antes do símbolo, como no resto do painel."""
    return f"{'-' if valor < 0.0 else ''}R$ {_br(abs(valor))}"


def x_of(candidate: IncomeCandidate, spot: float) -> float:
    """Posição horizontal, em px, de um preço do subjacente no gráfico do candidato."""
    pontos = candidate.profile.points
    baixo, alto = pontos[0].spot, pontos[-1].spot
    return PLOT_LEFT + (spot - baixo) / (alto - baixo) * (PLOT_RIGHT - PLOT_LEFT)


def _escala_y(candidate: IncomeCandidate) -> Callable[[float], float]:
    valores = [v for p in candidate.profile.points for v in (p.gross, p.net)] + [0.0]
    baixo, alto = min(valores), max(valores)
    folga = (alto - baixo) * 0.08 or 1.0
    baixo, alto = baixo - folga, alto + folga

    def y(valor: float) -> float:
        return _PLOT_TOP + (alto - valor) / (alto - baixo) * (_PLOT_BOTTOM - _PLOT_TOP)

    return y


def render_payoff_svg(candidate: IncomeCandidate, *, title: str, chart_id: str) -> str:
    """SVG do perfil do candidato; ``title`` e ``chart_id`` são escapados."""
    y = _escala_y(candidate)
    pontos = candidate.profile.points
    m = candidate.metrics
    id_titulo = escape(f"{chart_id}-titulo", quote=True)
    partes = [
        # SVG inline no HTML5 dispensa xmlns: nenhuma URL no painel.
        f'<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" '
        f'width="{CHART_WIDTH}" height="{CHART_HEIGHT}" role="img" aria-labelledby="{id_titulo}">',
        f'<title id="{id_titulo}">{escape(title)}</title>',
        f'<rect x="0" y="0" width="{CHART_WIDTH}" height="{CHART_HEIGHT}" fill="#ffffff"/>',
    ]

    def vertical(spot: float, classe: str, cor: str, rotulo: str, tracejado: str = "") -> None:
        if not pontos[0].spot <= spot <= pontos[-1].spot:
            return
        x = _n(x_of(candidate, spot))
        traco = f' stroke-dasharray="{tracejado}"' if tracejado else ""
        partes.append(
            f'<line class="{classe}" x1="{x}" y1="{_n(_PLOT_TOP)}" x2="{x}" '
            f'y2="{_n(_PLOT_BOTTOM)}" stroke="{cor}" stroke-width="1"{traco}/>'
        )
        partes.append(
            f'<text x="{x}" y="{_n(_PLOT_BOTTOM + 14)}" font-size="10" fill="{cor}" '
            f'text-anchor="middle">{escape(rotulo)}</text>'
        )

    def horizontal(valor: float, classe: str, rotulo: str) -> None:
        yy = _n(y(valor))
        partes.append(
            f'<line class="{classe}" x1="{_n(PLOT_LEFT)}" y1="{yy}" x2="{_n(PLOT_RIGHT)}" '
            f'y2="{yy}" stroke="{_NET}" stroke-width="1" stroke-dasharray="2 3"/>'
        )
        partes.append(
            f'<text x="{_n(PLOT_LEFT - 4)}" y="{_n(y(valor) + 3)}" font-size="10" '
            f'fill="{_NET}" text-anchor="end">{escape(rotulo)}</text>'
        )

    zero = _n(y(0.0))
    partes.append(
        f'<line class="zero" x1="{_n(PLOT_LEFT)}" y1="{zero}" x2="{_n(PLOT_RIGHT)}" y2="{zero}" '
        f'stroke="{_NEUTRAL}" stroke-width="1"/>'
    )
    for strike in sorted({leg.strike for leg in candidate.legs}):
        vertical(strike, "strike", _GRID, f"K {_br(strike)}", "1 3")
    vertical(
        candidate.profile.current_spot,
        "spot",
        _NEUTRAL,
        f"spot {_br(candidate.profile.current_spot)}",
    )
    vertical(m.breakeven, "be-bruto", _GROSS, f"BE {_br(m.breakeven)}", "4 3")
    if m.net_breakeven is not None:
        vertical(m.net_breakeven, "be-liquido", _NET, f"BE líq. {_br(m.net_breakeven)}", "4 3")
    horizontal(
        m.net_max_gain_per_position, "ganho-max", f"máx. {_moeda(m.net_max_gain_per_position)}"
    )
    horizontal(
        m.net_max_loss_per_position, "perda-max", f"mín. {_moeda(m.net_max_loss_per_position)}"
    )
    for classe, cor, campo in (("bruto", _GROSS, "gross"), ("liquido", _NET, "net")):
        coordenadas = " ".join(
            f"{_n(x_of(candidate, p.spot))},{_n(y(getattr(p, campo)))}" for p in pontos
        )
        partes.append(
            f'<polyline class="{classe}" points="{coordenadas}" fill="none" stroke="{cor}" '
            f'stroke-width="2"/>'
        )
    partes.append(
        f'<text x="{_n(PLOT_RIGHT)}" y="14" font-size="11" text-anchor="end">'
        f'<tspan fill="{_GROSS}">— bruto</tspan> <tspan fill="{_NET}">— líquido</tspan></text>'
    )
    partes.append("</svg>")
    return "".join(partes)

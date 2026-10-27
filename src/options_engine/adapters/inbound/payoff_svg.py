"""Gráfico de payoff de uma oportunidade em SVG inline — só desenha (plano da fase 2 §4).

Os pontos vêm prontos do domínio (``IncomeCandidate.profile``, mesmo modelo
de custos das métricas); aqui só há escala, coordenadas e rótulos. Stdlib,
sem JavaScript e sem lib de gráfico. Coordenadas arredondadas a 0,1 px: a
mesma entrada produz os mesmos bytes.

Elementos: curva BRUTA (payoff no vencimento) e LÍQUIDA (montagem, exercício
e IR do cenário); linha do zero; spot atual; strikes; breakeven bruto e
líquido; ganho e perda máximos líquidos. Cores com rótulo em texto e
``<title>`` acessível — a cor nunca é a única pista.

Rótulos do eixo de preço: strikes, spot e breakevens costumam ficar a poucos
px uns dos outros (o eixo vai de 0,5 a 1,5 x spot, e os breakevens bruto e
líquido diferem por centavos). Cada rótulo fica centrado na sua marca e vai
para a primeira linha abaixo do gráfico em que não colide com outro; o SVG
cresce em altura conforme o número de linhas.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html import escape
from typing import Final

from options_engine.domain.income.ranking import IncomeCandidate

__all__ = ["CHART_HEIGHT", "CHART_WIDTH", "PLOT_LEFT", "PLOT_RIGHT", "render_payoff_svg", "x_of"]

CHART_WIDTH: Final = 640
CHART_HEIGHT: Final = 260
"""Altura MÍNIMA: cresce quando os rótulos do eixo de preço precisam de mais linhas."""
PLOT_LEFT: Final = 72.0
PLOT_RIGHT: Final = 624.0
_PLOT_TOP: Final = 24.0
_PLOT_BOTTOM: Final = 224.0
_GROSS: Final = "#0969da"
_NET: Final = "#bc4c00"
_NEUTRAL: Final = "#57606a"
_GRID: Final = "#d0d7de"

_LABEL_FONT_SIZE: Final = 10
# Largura média de um caractere a 10 px numa sans-serif (dígitos e minúsculas
# ficam perto de 5,5 px), com folga: sem medir o texto, errar para mais só
# empilha um rótulo a mais; errar para menos deixaria a sobreposição voltar.
_LABEL_CHAR_WIDTH: Final = 6.0
_LABEL_GAP: Final = 6.0
_LABEL_FIRST_BASELINE: Final = _PLOT_BOTTOM + 14
_LABEL_ROW_HEIGHT: Final = 12.0
_BOTTOM_MARGIN: Final = 8.0


@dataclass(frozen=True, slots=True)
class _AxisMark:
    """Marca vertical no eixo de preço: a linha no gráfico e o seu rótulo embaixo."""

    price: float
    css_class: str
    line_color: str
    text_color: str
    label: str
    dash: str = ""


@dataclass(frozen=True, slots=True)
class _PlacedLabel:
    center_x: float
    baseline_y: float


def _label_half_width(label: str) -> float:
    return len(label) * _LABEL_CHAR_WIDTH / 2


def _place_axis_labels(marks: Sequence[_AxisMark], xs: Sequence[float]) -> list[_PlacedLabel]:
    """Linha de cada rótulo: a primeira em que ele cabe sem encostar no anterior.

    Varredura da esquerda para a direita (desempate pela ordem das marcas, o
    que mantém a saída determinística). O centro é deslocado para dentro do
    desenho quando a marca fica perto da borda, para o texto não ser cortado.
    """
    ordem = sorted(range(len(marks)), key=lambda i: (xs[i], i))
    fim_das_linhas: list[float] = []
    colocados: dict[int, _PlacedLabel] = {}
    for i in ordem:
        meia = _label_half_width(marks[i].label)
        centro = min(max(xs[i], meia), CHART_WIDTH - meia)
        esquerda = centro - meia
        linha = next(
            (n for n, fim in enumerate(fim_das_linhas) if esquerda >= fim + _LABEL_GAP),
            len(fim_das_linhas),
        )
        if linha == len(fim_das_linhas):
            fim_das_linhas.append(centro + meia)
        else:
            fim_das_linhas[linha] = centro + meia
        colocados[i] = _PlacedLabel(centro, _LABEL_FIRST_BASELINE + linha * _LABEL_ROW_HEIGHT)
    return [colocados[i] for i in range(len(marks))]


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


def _axis_marks(candidate: IncomeCandidate) -> list[_AxisMark]:
    """Strikes, spot e breakevens que caem dentro do eixo de preço do candidato."""
    m = candidate.metrics
    spot = candidate.profile.current_spot
    marcas = [
        # Linha do strike clara (é grade), texto com contraste para ser lido.
        _AxisMark(strike, "strike", _GRID, _NEUTRAL, f"K {_br(strike)}", "1 3")
        for strike in sorted({leg.strike for leg in candidate.legs})
    ]
    marcas.append(_AxisMark(spot, "spot", _NEUTRAL, _NEUTRAL, f"spot {_br(spot)}"))
    marcas.append(
        _AxisMark(m.breakeven, "be-bruto", _GROSS, _GROSS, f"BE {_br(m.breakeven)}", "4 3")
    )
    if m.net_breakeven is not None:
        marcas.append(
            _AxisMark(
                m.net_breakeven, "be-liquido", _NET, _NET, f"BE líq. {_br(m.net_breakeven)}", "4 3"
            )
        )
    pontos = candidate.profile.points
    return [marca for marca in marcas if pontos[0].spot <= marca.price <= pontos[-1].spot]


def render_payoff_svg(candidate: IncomeCandidate, *, title: str, chart_id: str) -> str:
    """SVG do perfil do candidato; ``title`` e ``chart_id`` são escapados."""
    y = _escala_y(candidate)
    pontos = candidate.profile.points
    m = candidate.metrics
    marcas = _axis_marks(candidate)
    xs = [x_of(candidate, marca.price) for marca in marcas]
    rotulos = _place_axis_labels(marcas, xs)
    base_mais_baixa = max((r.baseline_y for r in rotulos), default=_LABEL_FIRST_BASELINE)
    altura = max(CHART_HEIGHT, math.ceil(base_mais_baixa + _BOTTOM_MARGIN))
    id_titulo = escape(f"{chart_id}-titulo", quote=True)
    partes = [
        # SVG inline no HTML5 dispensa xmlns: nenhuma URL no painel.
        f'<svg viewBox="0 0 {CHART_WIDTH} {altura}" '
        f'width="{CHART_WIDTH}" height="{altura}" role="img" aria-labelledby="{id_titulo}">',
        f'<title id="{id_titulo}">{escape(title)}</title>',
        f'<rect x="0" y="0" width="{CHART_WIDTH}" height="{altura}" fill="#ffffff"/>',
    ]

    def vertical(marca: _AxisMark, x: float, rotulo: _PlacedLabel) -> None:
        traco = f' stroke-dasharray="{marca.dash}"' if marca.dash else ""
        partes.append(
            f'<line class="{marca.css_class}" x1="{_n(x)}" y1="{_n(_PLOT_TOP)}" x2="{_n(x)}" '
            f'y2="{_n(_PLOT_BOTTOM)}" stroke="{marca.line_color}" stroke-width="1"{traco}/>'
        )
        partes.append(
            f'<text x="{_n(rotulo.center_x)}" y="{_n(rotulo.baseline_y)}" '
            f'font-size="{_LABEL_FONT_SIZE}" fill="{marca.text_color}" '
            f'text-anchor="middle">{escape(marca.label)}</text>'
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
    for marca, x, rotulo in zip(marcas, xs, rotulos, strict=True):
        vertical(marca, x, rotulo)
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

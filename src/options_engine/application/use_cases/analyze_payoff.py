"""``AnalyzeStrategyPayoffService`` — implementação de ``AnalyzeStrategyPayoffUseCase``.

Payoff no vencimento é função apenas da estrutura e do eixo de spots — não
consome NENHUM port (sem mercado, sem relógio: o vencimento é o vencimento).
O service existe mesmo assim porque a borda depende do Protocol inbound, não
do motor de simulação (ARCH §4.2); a materialização eixo -> floats acontece
aqui, via ``linspace`` do kernel — o VO permanece especificação barata.
"""

from options_engine.domain.kernel.payoff import linspace
from options_engine.domain.model.results import PayoffProfile
from options_engine.domain.model.scenarios import SpotAxis
from options_engine.domain.model.strategy import Strategy
from options_engine.domain.simulation.engine import payoff_profile

__all__ = ["AnalyzeStrategyPayoffService"]


class AnalyzeStrategyPayoffService:
    """Materializa o eixo e delega ao motor de simulação do domínio."""

    def execute(self, strategy: Strategy, axis: SpotAxis) -> PayoffProfile:
        spots = linspace(axis.spot_min, axis.spot_max, axis.steps)
        return payoff_profile(strategy, spots)

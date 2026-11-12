"""Vol realizada a partir de fechamentos diários — função pura, reutilizável (ADR-0006).

Desvio-padrão amostral dos log-retornos fechamento a fechamento dos últimos
``window`` retornos, vezes sqrt(252), em BUSINESS_252. Usada pelo adapter
COTAHIST e por quem tiver uma série de fechamentos (a cadeia ao vivo).

Histórico insuficiente ou vol zero não levantam exceção nem viram número:
a função devolve o MOTIVO (``str``) e quem chama decide como reportar — o
adapter embrulha em ``UnderlyingUnavailableError``. Limitação: fechamentos
sem ajuste por proventos ou desdobramentos distorcem a vol na janela.
"""

import itertools
import math
import statistics
from collections.abc import Sequence

from options_engine.domain.model.conventions import DayCountConvention, Volatility

__all__ = ["realized_volatility"]


def realized_volatility(closes: Sequence[float], window: int) -> Volatility | str:
    """Vol realizada anualizada, ou o motivo (``str``) de não haver como calculá-la.

    ``closes``: fechamentos > 0 em ordem cronológica, o último é o mais
    recente (o COTAHIST já filtra fechamento zero na origem). ``window``:
    número de retornos da janela, ``>= 2`` (desvio-padrão amostral) — menor
    que isso levanta ``ValueError``, como o construtor do adapter.
    """
    if window < 2:
        raise ValueError(
            f"window deve ser >= 2 retornos (desvio-padrão amostral); recebido {window!r}"
        )
    exigidos = window + 1
    if len(closes) < exigidos:
        return (
            f"histórico insuficiente para a vol realizada: {len(closes)} fechamentos "
            f"até o pregão, mínimo {exigidos} ({window} retornos)"
        )
    janela = closes[-exigidos:]
    retornos = [math.log(b / a) for a, b in itertools.pairwise(janela)]
    desvio = statistics.stdev(retornos)
    if not desvio > 0.0:
        return f"vol realizada zero nos últimos {window} retornos"
    base = DayCountConvention.BUSINESS_252
    return Volatility(desvio * math.sqrt(base.days_per_year), base)

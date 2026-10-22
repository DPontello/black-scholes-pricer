"""Resolução de tempo dos use cases — o ÚNICO lugar que converte agora -> tau.

Duas armadilhas que este módulo existe para centralizar (painel de design,
2026-07-04):

1. ``clock.now().date()`` cru é bug de fuso: o ``Clock`` devolve UTC e, entre
   21h e meia-noite em São Paulo, o ``.date()`` UTC já virou o dia seguinte —
   a opção "vence" um pregão mais cedo. A data de valoração SEMPRE converte
   para o fuso de valoração injetado (B3 = UTC-3 fixo, DST abolido em 2019)
   antes de extrair a data.
2. A contagem de dias depende da convenção: BUSINESS_252 conta dias úteis
   via ``TradingCalendar``; CALENDAR_365 conta dias corridos — usar o
   calendário para ambas contaria feriado como dia útil ou vice-versa.
"""

from datetime import date, tzinfo

from options_engine.application.ports.outbound import Clock, TradingCalendar
from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry
from options_engine.domain.model.errors import ExpiredOptionError, InvalidDomainValueError

__all__ = ["resolve_time_to_expiry", "valuation_date"]


def valuation_date(clock: Clock, valuation_timezone: tzinfo) -> date:
    """Data de valoração: o agora do ``Clock`` visto do fuso de valoração."""
    return clock.now().astimezone(valuation_timezone).date()


def resolve_time_to_expiry(
    expiry: date,
    as_of: date,
    calendar: TradingCalendar,
    day_count: DayCountConvention,
) -> TimeToExpiry:
    """Tau resolvido de ``as_of`` até ``expiry``, na convenção dada.

    ``expiry == as_of`` é legal: resta 0 dia, tau = 0 e a posição vale o
    intrínseco descontado (decisão nº 5). ``expiry < as_of`` não tem preço
    a termo → ``ExpiredOptionError``, disparada AQUI (com mensagem de
    negócio), antes de o calendário receber uma contagem negativa.
    """
    if expiry < as_of:
        raise ExpiredOptionError(
            f"opção vencida em {expiry.isoformat()} não tem preço a termo na data de "
            f"valoração {as_of.isoformat()} — expiry no próprio dia é legal (tau = 0), "
            f"anterior não"
        )
    if day_count is DayCountConvention.BUSINESS_252:
        days = calendar.business_days_between(as_of, expiry)
    elif day_count is DayCountConvention.CALENDAR_365:
        days = (expiry - as_of).days
    else:
        # Exaustivo de propósito: uma convenção nova cair no ramo errado
        # (dias úteis vs corridos) é preço errado sem erro de runtime — a
        # mesma armadilha que MixedAnnualizationBaseError existe para
        # impedir, uma camada acima. Adicionar uma convenção exige decidir
        # aqui explicitamente, nunca herdar o ramo default.
        raise InvalidDomainValueError(
            f"day_count {day_count!r} sem contagem de dias definida em resolve_time_to_expiry"
        )
    return TimeToExpiry.from_days(days, day_count)

"""Tradução dos valores crus do Tryd (``RawValue``) para o domínio.

É a fronteira onde o zero do RTD poderia virar preço em silêncio: o RTD manda zero até o
Tryd carregar o tópico, e zero em oferta, último ou fechamento também é o "sem oferta" do
Tryd. Aqui o zero, o vazio e o campo que não chegou viram lado ausente (``None``, ADR-0003),
nunca preço. Funções puras: o relógio e o "já carregou" (``LiveBoard.is_loaded``) vêm do
chamador.

Regras de leitura de um campo numérico:

- número (``float``/``int``) finito e ``> 0`` vale como veio; ``0``, ``None`` e ``""`` são
  ausência; negativo, ``NaN`` e infinito são ilegíveis;
- texto só no formato estrito (``"52,51"``, ``"1.234,5"`` ou ``"52.51"``); qualquer outro é
  ilegível, nunca é suposto. Espaço e fim de linha nas pontas são ignorados (o DDE termina o
  texto com CR LF). ``"1.234"`` é o formato de ponto (1,234), não milhar;
- ``tipo_valor == "outro"`` é ilegível sempre: o ``repr`` de um objeto não é número.

O que um valor ilegível causa: na opção, a série vira ``RejectedSeries`` com o campo e o
valor no motivo; no ativo, preço ilegível deixa só aquele campo ausente, e ``NEG``/``VOL``
ilegíveis tiram a cotação inteira (``None``): com lixo no volume ou nos negócios não há como
saber se a liquidez é a que o painel mostraria. ``NEG``/``VOL`` ausentes valem ``0``/``0.0``.

Sem nenhum campo (nada chegou da ponte para o ativo) também não há cotação: ``trades=0`` com
a hora de agora seria uma observação inventada.
"""

import logging
import re
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, tzinfo
from math import isfinite

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.tryd.board import RawValue
from options_engine.domain.model.chain import OptionQuote, RejectedSeries
from options_engine.domain.model.contracts import OptionContract
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote

__all__ = ["WarnFn", "parse_tryd_timestamp", "to_option_quote", "to_underlying_quote"]

_log = logging.getLogger(__name__)

# (ticker, motivo, mensagem): o motivo é a categoria do problema, sem o valor (agrupa o que se
# repete a cada consulta); a mensagem é o texto completo para o log.
WarnFn = Callable[[str, str, str], None]

# [0-9], não \d: dígitos de outros alfabetos (fullwidth, árabe-índico) não são do Tryd.
_NUMERO_PT_BR = re.compile(r"[0-9]+(\.[0-9]{3})*,[0-9]+")
_NUMERO_PONTO = re.compile(r"[0-9]+(\.[0-9]+)?")
_DATA = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})")
_HORA = re.compile(r"([0-9]{2}):([0-9]{2}):([0-9]{2})")


class _ValorIlegivel(Exception):
    """Valor cru que não é número legível; ``campo`` e ``valor`` vão para o motivo/log."""

    def __init__(self, campo: str, valor: object) -> None:
        super().__init__(f"valor ilegível no campo {campo}: {valor!r}")
        self.campo = campo
        self.valor = valor


def parse_tryd_timestamp(
    date_text: str | None, time_text: str | None, tz: tzinfo, today: date | None = None
) -> datetime | None:
    """``DAT`` + ``HOR`` no fuso ``tz``; ``None`` se faltar um ou for ilegível.

    O Tryd escreve a data no formato regional do Windows (28/10/2026 ou 10/28/2026). Se dia e
    mês podem ser trocados, vale a leitura mais perto de ``today``; sem ``today``, dia/mês.
    """
    if date_text is None or time_text is None:
        return None
    data = _DATA.fullmatch(date_text.strip())
    hora = _HORA.fullmatch(time_text.strip())
    if data is None or hora is None:
        return None
    primeiro, segundo, ano = (int(parte) for parte in data.groups())
    horas, minutos, segundos = (int(parte) for parte in hora.groups())
    candidatas: list[datetime] = []
    for dia, mes in ((primeiro, segundo), (segundo, primeiro)):
        try:
            candidata = datetime(ano, mes, dia, horas, minutos, segundos, tzinfo=tz)
        except ValueError:
            continue
        if candidata not in candidatas:
            candidatas.append(candidata)
    if not candidatas:
        return None
    if today is None or len(candidatas) == 1:
        return candidatas[0]
    amanha = today + timedelta(days=1)
    return min(candidatas, key=lambda c: (c.date() > amanha, abs((c.date() - today).days)))


def _read_number(campo: str, raw: RawValue | None) -> float | None:
    """Número finito ``>= 0`` do valor cru; ``None`` se ausente; ``_ValorIlegivel`` se lixo."""
    if raw is None:
        return None
    valor = raw.value
    if raw.kind == "outro" or isinstance(valor, bool):
        raise _ValorIlegivel(campo, valor)
    if valor is None:
        return None
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return None
        if _NUMERO_PONTO.fullmatch(texto):
            numero = float(texto)
        elif _NUMERO_PT_BR.fullmatch(texto):
            numero = float(texto.replace(".", "").replace(",", "."))
        else:
            raise _ValorIlegivel(campo, valor)
    else:
        try:
            numero = float(valor)
        except OverflowError:  # int maior que o maior float
            raise _ValorIlegivel(campo, valor) from None
    # Forma negada: NaN falha em qualquer comparação e cairia no caminho "válido".
    if not (isfinite(numero) and numero >= 0.0):
        raise _ValorIlegivel(campo, valor)
    return numero if numero > 0.0 else 0.0  # -0.0 vira 0.0


def _read_price(campo: str, values: Mapping[str, RawValue]) -> float | None:
    """Preço ``> 0``; o zero do RTD, o vazio e o campo que não chegou são ``None``."""
    numero = _read_number(campo, values.get(campo))
    return None if numero is None or numero == 0.0 else numero


def _read_trades(values: Mapping[str, RawValue]) -> int:
    raw = values.get("NEG")
    numero = _read_number("NEG", raw)
    if raw is None or numero is None:
        return 0
    if not numero.is_integer():
        raise _ValorIlegivel("NEG", raw.value)
    return int(numero)


def _read_volume(values: Mapping[str, RawValue]) -> float:
    numero = _read_number("VOL", values.get("VOL"))
    return 0.0 if numero is None else numero


def _text(raw: RawValue | None) -> str | None:
    return raw.value if raw is not None and isinstance(raw.value, str) else None


def _timestamp(values: Mapping[str, RawValue], fallback_time: datetime) -> datetime:
    hoje = fallback_time.astimezone(B3_UTC_OFFSET).date()
    lido = parse_tryd_timestamp(
        _text(values.get("DAT")), _text(values.get("HOR")), B3_UTC_OFFSET, hoje
    )
    return fallback_time if lido is None else lido


def _is_crossed(bid: float | None, ask: float | None) -> bool:
    return bid is not None and ask is not None and not (bid <= ask)


def _log_warning(ticker: str, motivo: str, mensagem: str) -> None:
    _log.warning("%s: %s", ticker, mensagem)


def to_underlying_quote(
    ticker: str,
    values: Mapping[str, RawValue],
    loaded: bool,
    source: DataSource,
    fallback_time: datetime,
    warn: WarnFn = _log_warning,
) -> UnderlyingQuote | None:
    """Cotação do ativo-objeto; ``None`` se não carregado, sem valores, ou dado incoerente.

    Preço ilegível deixa só aquele campo ausente. ``NEG``/``VOL`` ilegíveis e book cruzado na
    fonte tiram a cotação inteira, com o motivo no log. Quem consulta em laço (polling) passa
    ``warn`` para limitar a repetição do mesmo aviso; por padrão cada um vai ao log.
    """
    if not loaded or not values:
        return None
    prices: dict[str, float | None] = {}
    for campo in ("ULT", "OCP", "OVD", "FEC"):
        try:
            prices[campo] = _read_price(campo, values)
        except _ValorIlegivel as erro:
            warn(
                ticker,
                f"valor ilegível no campo {erro.campo}",
                f"{erro}; campo tratado como ausente",
            )
            prices[campo] = None
    try:
        trades = _read_trades(values)
        volume = _read_volume(values)
    except _ValorIlegivel as erro:
        warn(ticker, f"valor ilegível no campo {erro.campo}", f"{erro}; ativo sem cotação")
        return None
    if _is_crossed(prices["OCP"], prices["OVD"]):
        warn(
            ticker,
            "book cruzado na fonte",
            f"book cruzado na fonte (bid={prices['OCP']!r}, ask={prices['OVD']!r}); "
            "ativo sem cotação",
        )
        return None
    return UnderlyingQuote(
        symbol=ticker,
        last=prices["ULT"],
        bid=prices["OCP"],
        ask=prices["OVD"],
        previous_close=prices["FEC"],
        trades=trades,
        volume=volume,
        timestamp=_timestamp(values, fallback_time),
        source=source,
    )


def to_option_quote(
    contract: OptionContract,
    values: Mapping[str, RawValue],
    loaded: bool,
    fallback_time: datetime,
) -> OptionQuote | RejectedSeries | None:
    """Cotação da série; ``None`` se não carregada ou sem valores.

    Campo numérico ilegível ou book cruzado na fonte rejeitam a série, com motivo.
    """
    if not loaded or not values:
        return None
    try:
        last = _read_price("ULT", values)
        bid = _read_price("OCP", values)
        ask = _read_price("OVD", values)
        trades = _read_trades(values)
        volume = _read_volume(values)
    except _ValorIlegivel as erro:
        return RejectedSeries(contract.symbol, str(erro))
    if _is_crossed(bid, ask):
        return RejectedSeries(contract.symbol, "book cruzado na fonte (Tryd)")
    return OptionQuote(
        contract=contract,
        bid=bid,
        ask=ask,
        last=last,
        trades=trades,
        volume=volume,
        timestamp=_timestamp(values, fallback_time),
    )

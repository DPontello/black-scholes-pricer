"""Ports outbound (driven) — Protocols que os adapters implementam (ARCH §4.1).

Structural typing de propósito: o adapter não precisa importar nada daqui
para SER um port. ``runtime_checkable`` existe para os contract tests
afirmarem ``isinstance`` — mas type hints garantem forma, não comportamento;
a conformidade semântica é da suíte de contrato (tests/contract/).

As assinaturas nascem dos use cases, nunca dos adapters (risco nº 1 do
ROADMAP S3: port desenhado a partir do mock). Por isso:

- ``MarketDataPort`` NÃO tem ``subscribe()`` — método que nenhum adapter
  implementa quebra ISP e os contract tests; streaming entra na fase
  websocket.
- NÃO há port de taxa: nenhum use case consome taxa fora do
  ``MarketSnapshot`` — ela chega atômica, dentro da foto, como VO com
  compounding explícito (CONVENTIONS §3).
"""

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["Clock", "MarketDataPort", "OptionChainPort", "RandomSource", "TradingCalendar"]


@runtime_checkable
class MarketDataPort(Protocol):
    """Fonte de snapshots de mercado — mock hoje, feed B3 amanhã, MESMO contrato.

    Contrato semântico (verificado pela suíte herdável de tests/contract/):

    1. ``spot > 0``, ``volatility > 0``, ``0 <= bid <= mid <= ask``;
    2. ``timestamp`` tz-aware; chamadas sucessivas com timestamps
       monotônicos não-decrescentes;
    3. taxa SEMPRE como ``RiskFreeRate`` com compounding explícito —
       conversão para contínua é do domínio, nunca do feed;
    4. símbolo desconhecido → ``UnknownSymbolError`` (exceção de domínio),
       nunca ``KeyError``, ``None`` ou exceção de lib HTTP vazando;
    5. consulta, não comando: snapshots já devolvidos permanecem imutáveis.
    """

    def get_snapshot(self, underlying_symbol: str) -> MarketSnapshot: ...


@runtime_checkable
class OptionChainPort(Protocol):
    """Fonte da cadeia de opções de um subjacente (ADR-0003).

    Port separado do ``MarketDataPort`` (que não muda): a cadeia traz o book
    de cada série, não só o do ativo-objeto. Fim de dia (COTAHIST) e
    intraday sob o MESMO contrato — o pregão de referência vive dentro da
    cadeia (timestamps tz-aware) e o adapter é configurado com a fonte/data,
    por isso a assinatura recebe só o símbolo.

    Contrato semântico (verificado pela suíte herdável de tests/contract/):

    1. ``bid``, ``ask`` e ``last`` são ``None`` ou finitos e ``> 0`` — lado
       ausente é ``None``, NUNCA ``0``; a tradução "zero da fonte → None" é
       exclusiva do adapter;
    2. com os dois lados presentes, ``bid <= ask``;
    3. a cadeia e todas as suas cotações são do subjacente pedido;
    4. timestamps tz-aware (snapshot do subjacente e cotações);
    5. símbolo desconhecido → ``UnknownSymbolError`` (exceção de domínio),
       nunca ``KeyError``, ``None`` ou exceção de lib de I/O vazando;
    6. consulta, não comando: cadeias devolvidas são imutáveis e consultar
       não tem efeito colateral observável — nem uma consulta que falha
       deixa o port inutilizável.

    Semântica que a suíte não consegue verificar, mas o adapter deve
    honrar: a vol do ``MarketSnapshot`` do subjacente é a vol REALIZADA de
    referência, calculada pelo adapter a partir do histórico; a implícita de
    cada série é resolvida fora do port. Ativo-objeto com livro vazio: o
    adapter não inventa bid/ask (ADR-0004).
    """

    def get_chain(self, underlying_symbol: str) -> OptionChain: ...


@runtime_checkable
class Clock(Protocol):
    """Abstrai o "agora" — ``datetime.now()`` espalhado pelo código é o
    assassino nº 1 de testes de pricing: sem ``Clock`` injetado, o
    time-to-expiry flutua entre execuções e nenhum teste é determinístico.

    Contrato: retorno SEMPRE tz-aware (UTC interno; conversão de exibição
    pertence às bordas — ARCH §4.1).
    """

    def now(self) -> datetime: ...


@runtime_checkable
class TradingCalendar(Protocol):
    """Contagem de dias úteis — obrigatória para BUSINESS_252 (B3).

    Contrato: intervalo MEIO-ABERTO ``[start, end)`` — conta os dias úteis
    d com ``start <= d < end``. Consequências deliberadas:

    - ``start == end`` → 0: no próprio dia do vencimento resta 0 dia útil,
      tau = 0 e a posição vale o intrínseco descontado (decisão nº 5);
    - um dia útil antes do vencimento → 1 (o pregão de hoje ainda conta);
    - ``start > end`` → ``InvalidDomainValueError`` — contagem negativa não
      tem semântica; opção vencida é tratada pelo chamador, com mensagem
      própria, antes de chegar aqui.
    """

    def business_days_between(self, start: date, end: date) -> int: ...


@runtime_checkable
class RandomSource(Protocol):
    """Aleatoriedade injetável e SEMPRE seedável (CONVENTIONS §7).

    Serve o gerador de order book mockado hoje e o Monte Carlo amanhã.
    ``random`` global no domínio é proibido: estado compartilhado escondido
    quebra o determinismo por seed — mesma seed ⇒ resultado bit a bit
    idêntico.
    """

    def gaussians(self, n: int) -> tuple[float, ...]: ...

    def uniform(self, low: float, high: float) -> float: ...

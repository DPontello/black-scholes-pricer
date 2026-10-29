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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.market import MarketSnapshot
from options_engine.domain.model.profile import Profile, ProfileEntry
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote

__all__ = [
    "CadastroFreshness",
    "Clock",
    "LiveFeedPort",
    "MarketDataPort",
    "MarketPort",
    "OptionChainPort",
    "ProfileRepository",
    "QuoteBoardPort",
    "RandomSource",
    "TradingCalendar",
]


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
    3. a cadeia e todas as suas cotações são do subjacente pedido; o
       subjacente é um ``MarketSnapshot`` com ``spot > 0``, vol como
       ``Volatility`` com ``value > 0`` e taxa como ``RiskFreeRate`` (as
       mesmas checagens do contrato do ``MarketDataPort``);
    4. timestamps tz-aware (snapshot do subjacente e cotações);
    5. símbolo desconhecido → ``UnknownSymbolError`` (exceção de domínio),
       nunca ``KeyError``, ``None`` ou exceção de lib de I/O vazando;
       símbolo conhecido sem preço utilizável no pregão (sem fechamento,
       histórico insuficiente para a vol realizada) →
       ``UnderlyingUnavailableError`` com o motivo (ADR-0004);
    6. consulta, não comando: cadeias devolvidas são imutáveis e consultar
       não tem efeito colateral observável — nem uma consulta que falha
       deixa o port inutilizável;
    7. ``rejected_series`` traz, com motivo, as séries da fonte que não
       viraram cotação, disjuntas das ``quotes``.

    Semântica que a suíte não consegue verificar, mas o adapter deve
    honrar: a vol do ``MarketSnapshot`` do subjacente é a vol REALIZADA de
    referência, calculada pelo adapter a partir do histórico; a implícita de
    cada série é resolvida fora do port. Ativo-objeto com fechamento mas
    sem ofertas (decisão da mesa, ADR-0004): o snapshot usa o fechamento em
    spot, bid, ask e mid e a cadeia sai com ``underlying_book_available =
    False`` — bid/ask não observados nunca se passam por book real.
    """

    def get_chain(self, underlying_symbol: str) -> OptionChain: ...


@runtime_checkable
class QuoteBoardPort(Protocol):
    """Painel de cotações dos ativos-objeto, cada uma rotulada pela fonte.

    Contrato semântico:

    1. o resultado traz TODOS os símbolos pedidos: ``UnderlyingQuote`` ou o
       MOTIVO (``str``) de não haver cotação — ``"ativo desconhecido"`` (ticker
       fora do cadastro e dos arquivos da B3, em geral digitado errado) ou
       ``"aguardando dados"`` (conhecido, mas a fonte ainda não entregou); o
       motivo é texto para a tela;
    2. nenhuma cotação sai sem ``source``, e ``AO_VIVO``/``ATRASADO`` só com
       dado que a fonte ao vivo de fato entregou: dado parado nunca se passa
       por ao vivo;
    3. lado ausente (``bid``, ``ask``, ``last``, ``previous_close``) é
       ``None``, NUNCA ``0`` (ADR-0003);
    4. consulta, não comando: motivo é valor de retorno, nunca exceção.
    """

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]: ...


@runtime_checkable
class LiveFeedPort(Protocol):
    """Fonte ao vivo: o que acompanhar e em que estado ela está.

    ``watch`` diz à fonte quais ativos e quais cadeias acompanhar (a
    assinatura é a lista inteira: o que sai dela é cancelado; listas vazias
    cancelam tudo). ``health`` é o rótulo que o dado dela tem agora:
    ``AO_VIVO``, ``ATRASADO`` ou ``FIM_DE_DIA`` (sem fonte ao vivo; o app cai
    para os arquivos da B3).
    """

    def watch(self, underlyings: Sequence[str], chain_symbols: Sequence[str]) -> None: ...

    def health(self) -> DataSource: ...


@runtime_checkable
class MarketPort(QuoteBoardPort, LiveFeedPort, OptionChainPort, Protocol):
    """Tudo o que o serviço de mercado consome: cotações, assinatura e cadeia."""


@dataclass(frozen=True, slots=True)
class CadastroFreshness:
    reference_date: date
    business_days: int
    stale: bool


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


@runtime_checkable
class ProfileRepository(Protocol):
    """Perfis do app e a trava de uso entre PCs.

    O perfil mora na pasta que o usuário escolheu (nuvem, pendrive); o nome é
    só a chave do cadastro da máquina, nunca vira nome de pasta ou arquivo.

    Contrato:

    1. ``create`` numa pasta que já tem um perfil ADOTA o existente: o nome
       gravado na pasta prevalece sobre o pedido — é assim que o mesmo perfil,
       na nuvem, aparece em outro PC. Nome já cadastrado (o pedido ou o
       adotado) → ``DuplicateProfileError``;
    2. pasta fora do ar (nuvem não montada, pendrive removido) ou erro do SO
       ao ler/gravar os arquivos do perfil (permissão, arquivo em uso) →
       ``ProfileFolderUnavailableError`` com o caminho; nada é criado em outro
       lugar e o cadastro não muda;
    3. nome não cadastrado em ``load``, ``save``, ``acquire_lock`` ou
       ``release_lock`` → ``UnknownProfileError``;
    4. trava de OUTRO PC com idade de até 12 h → ``ProfileLockedError``, a
       menos que ``force``; mais velha que isso é ignorada. A trava do próprio
       PC é renovada. ``now`` é tz-aware e é gravado no fuso em que chegou;
    5. ``release_lock`` só remove a trava do próprio ``machine`` e nunca
       levanta por trava ausente, pasta fora do ar ou erro do SO: fechar o app
       precisa funcionar;
    6. ``load`` devolve um perfil cujo ``name`` é a chave pedida; arquivo com
       outro nome → ``InvalidDomainValueError`` (a chave do cadastro manda).
    """

    def list_profiles(self) -> tuple[ProfileEntry, ...]: ...

    def create(self, name: str, folder: str) -> Profile: ...

    def load(self, name: str) -> Profile: ...

    def save(self, name: str, profile: Profile) -> None: ...

    def acquire_lock(self, name: str, machine: str, now: datetime, force: bool) -> None: ...

    def release_lock(self, name: str, machine: str) -> None: ...

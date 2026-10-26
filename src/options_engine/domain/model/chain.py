"""Cadeia de opções (ADR-0003) e preço executável por lado (ADR-0004).

Dois cuidados estruturais atravessam o módulo:

- **Lado ausente é ``None``, nunca ``0``** (ADR-0003). Nas fontes reais
  (COTAHIST, brapi) melhor compra e melhor venda vêm zeradas com
  frequência; um zero de "sem oferta" que atravessasse a fronteira viraria
  um preço real, sem nenhum erro de runtime. A tradução "zero da fonte →
  ``None``" acontece exclusivamente no adapter (ARCH §1) — aqui ``0`` é
  irrepresentável.
- **O preço da perna depende do lado** (ADR-0004). Quem vende recebe o
  melhor bid; quem compra paga o melhor ask. Mid ou último negócio
  superestimariam o rendimento e premiariam justamente as séries menos
  líquidas — por isso nenhum prêmio sai daqui sem rótulo de qualidade.
"""

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from math import isfinite

from options_engine.domain.model.contracts import OptionContract
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.market import MarketSnapshot

__all__ = [
    "LegPremium",
    "OptionChain",
    "OptionQuote",
    "PriceQuality",
    "executable_premium",
    "worst_quality",
]


def _is_tz_aware(timestamp: datetime) -> bool:
    # tzinfo presente não basta: um tzinfo que devolve utcoffset None ainda
    # é naive na prática (mesma regra do MarketSnapshot).
    return timestamp.tzinfo is not None and timestamp.tzinfo.utcoffset(timestamp) is not None


@dataclass(frozen=True, slots=True)
class OptionQuote:
    """Cotação de uma série num pregão: book, último negócio e liquidez.

    ``bid``, ``ask`` e ``last`` são ``None`` (lado ausente / sem negócio) ou
    finitos e ``> 0``. Com os dois lados presentes, ``bid <= ask``: spread
    zero (book travado) é coerente, book cruzado não. Não há ``mid``: ele
    serve só para exibir o smile, nunca para calcular rendimento (ADR-0004)
    — derivá-lo é da apresentação.

    ``trades`` (número de negócios) e ``volume`` (volume negociado) são do
    pregão de referência e alimentam os filtros de liquidez, que são
    parâmetros do comando, não invariantes deste VO (ADR-0004). A unidade de
    ``volume`` (financeiro ou quantidade de contratos) não é fixada pela
    ADR-0003; o domínio só exige finito e ``>= 0``.

    Não há invariante cruzando ``last`` e ``trades``: uma fonte pode trazer
    o último preço de um pregão anterior com ``trades == 0``. Decidir se o
    ``last`` é utilizável é da regra de preço, não da cotação.
    """

    contract: OptionContract
    bid: float | None
    ask: float | None
    last: float | None
    trades: int
    volume: float
    timestamp: datetime

    def __post_init__(self) -> None:
        for nome, valor in (("bid", self.bid), ("ask", self.ask), ("last", self.last)):
            # Forma negada: NaN falha em qualquer comparação e cairia no
            # caminho "válido" de um `valor <= 0.0`.
            if valor is not None and not (isfinite(valor) and valor > 0.0):
                raise InvalidDomainValueError(
                    f"{nome} de {self.contract.symbol!r} deve ser None (ausente) ou finito e "
                    f"> 0 — zero de 'sem oferta' vira None no adapter (ADR-0003); "
                    f"recebido {valor!r}"
                )
        if self.bid is not None and self.ask is not None and not (self.bid <= self.ask):
            raise InvalidDomainValueError(
                f"book cruzado em {self.contract.symbol!r}: exigido bid <= ask; recebido "
                f"bid={self.bid!r}, ask={self.ask!r}"
            )
        if self.trades < 0:
            raise InvalidDomainValueError(
                f"trades de {self.contract.symbol!r} deve ser >= 0; recebido {self.trades!r}"
            )
        if not (isfinite(self.volume) and self.volume >= 0.0):
            raise InvalidDomainValueError(
                f"volume de {self.contract.symbol!r} deve ser finito e >= 0; "
                f"recebido {self.volume!r}"
            )
        if not _is_tz_aware(self.timestamp):
            raise InvalidDomainValueError(
                f"timestamp de {self.contract.symbol!r} deve ser tz-aware; "
                f"recebido {self.timestamp!r}"
            )

    @property
    def is_book_empty(self) -> bool:
        """Nenhum lado do book presente — pré-condição de INDICATIVO e TEORICO.

        Distingue os dois "sem preço" da ADR-0004: com book de um lado só, a
        perna no lado ausente fica sem preço; com book vazio, a série ainda
        pode ter preço indicativo (``last`` do pregão) ou teórico.
        """
        return self.bid is None and self.ask is None


@dataclass(frozen=True, slots=True)
class OptionChain:
    """Todas as séries de um subjacente num pregão, junto com o próprio subjacente.

    ``underlying`` reutiliza o ``MarketSnapshot`` (ADR-0003): a vol dele é a
    vol REALIZADA de referência, calculada pelo adapter a partir do
    histórico; a vol por série é a implícita, aplicada por perna com
    ``dataclasses.replace(snapshot, volatility=...)`` — o VO não muda.

    Invariantes: toda cotação é do subjacente do snapshot (cadeia que mistura
    ativos-objeto é bug de adapter, não dado) e os tickers são únicos (duas
    cotações da mesma série tornariam ambígua a pergunta "qual o bid de
    PETRA250?"). Termos idênticos com tickers distintos são legais — são
    instrumentos distintos (ARCH §2.2).

    Cadeia vazia é legal: um subjacente sem séries no pregão é informação
    para o painel, não estado inválido.
    """

    underlying: MarketSnapshot
    quotes: tuple[OptionQuote, ...]

    def __post_init__(self) -> None:
        simbolo = self.underlying.underlying_symbol
        alheias = sorted(
            quote.contract.symbol
            for quote in self.quotes
            if quote.contract.terms.underlying != simbolo
        )
        if alheias:
            raise InvalidDomainValueError(
                f"cadeia de {simbolo!r} contém séries de outro subjacente: {alheias!r}"
            )
        contagem = Counter(quote.contract.symbol for quote in self.quotes)
        duplicados = sorted(ticker for ticker, vezes in contagem.items() if vezes > 1)
        if duplicados:
            raise InvalidDomainValueError(
                f"cadeia de {simbolo!r} repete séries (tickers devem ser únicos): {duplicados!r}"
            )


@unique
class PriceQuality(Enum):
    """Rótulo de qualidade de um prêmio (ADR-0004) — nenhum número sai sem ele.

    Membros declarados do MELHOR para o PIOR; a ordem de declaração é a
    ordem de qualidade que ``worst_quality`` usa (fixada por teste).

    - ``EXECUTAVEL``: o lado do book que a perna de fato agride (bid para
      vender, ask para comprar). Único que entra no ranking padrão.
    - ``INDICATIVO``: book vazio, mas houve negócio no pregão — ``last``.
      Exibível fora do ranking, sempre rotulado.
    - ``TEORICO``: book vazio e sem negócio — Black-Scholes com a vol
      implícita interpolada do smile do mesmo vencimento. Calculado fora
      deste módulo; aparece só como referência, nunca no ranking.
    """

    EXECUTAVEL = "executavel"
    INDICATIVO = "indicativo"
    TEORICO = "teorico"


def worst_quality(qualities: Iterable[PriceQuality]) -> PriceQuality:
    """Pior qualidade entre as pernas de uma estrutura (ADR-0004).

    A estrutura vale o que vale sua perna mais fraca: uma trava com a perna
    vendida EXECUTAVEL e a comprada INDICATIVO é INDICATIVO — e sai do
    ranking padrão. Sem pernas → ``InvalidDomainValueError``: devolver
    EXECUTAVEL para o vazio rotularia como executável algo que não existe.
    """
    ordem = list(PriceQuality)
    materializadas = tuple(qualities)
    if not materializadas:
        raise InvalidDomainValueError(
            "pior qualidade exige ao menos uma perna — estrutura vazia não tem preço"
        )
    return max(materializadas, key=ordem.index)


@dataclass(frozen=True, slots=True)
class LegPremium:
    """Prêmio unitário de uma perna + a qualidade do preço que o produziu.

    Par indivisível de propósito: prêmio sem rótulo é exatamente o número
    que a ADR-0004 proíbe de sair do sistema. ``premium`` é por opção, na
    moeda do subjacente — a mesma unidade de ``StrategyLeg.premium``.

    Preço observado (EXECUTAVEL, INDICATIVO) é ``> 0``, herdado dos lados do
    book (ADR-0003). TEORICO admite ``0``: Black-Scholes de uma série muito
    fora do dinheiro pode valer zero, e isso é informação, não erro.
    """

    premium: float
    quality: PriceQuality

    def __post_init__(self) -> None:
        if not (isfinite(self.premium) and self.premium >= 0.0):
            raise InvalidDomainValueError(
                f"premium deve ser finito e >= 0; recebido {self.premium!r}"
            )
        if self.premium == 0.0 and self.quality is not PriceQuality.TEORICO:
            raise InvalidDomainValueError(
                f"preço observado ({self.quality.name}) nunca é zero — lado ausente é "
                f"None (ADR-0003); só TEORICO admite premium == 0"
            )


def executable_premium(quote: OptionQuote, side: Side) -> LegPremium | None:
    """Prêmio da perna pelo lado correto do book — a tabela da ADR-0004.

    ==========================  ==================  ==================
    Situação da série           ``Side.SELL``       ``Side.BUY``
    ==========================  ==================  ==================
    bid e ask presentes         bid, EXECUTAVEL     ask, EXECUTAVEL
    só bid                      bid, EXECUTAVEL     ``None``
    só ask                      ``None``            ask, EXECUTAVEL
    nenhum lado, com negócio    last, INDICATIVO    last, INDICATIVO
    nenhum lado, sem negócio    ``None``            ``None``
    ==========================  ==================  ==================

    ``None`` é "sem preço observado para este lado" e nunca é trocado por
    mid ou por ``last`` em silêncio. Os dois ``None`` têm destinos
    distintos na ADR-0004 — ``quote.is_book_empty`` os separa:

    - book de um lado só, perna no lado ausente: **sem preço**. Não há
      contraparte a agredir, e a ADR só admite ``last`` com book vazio;
    - book vazio e sem negócio: elegível ao TEORICO (BS com a vol implícita
      interpolada do smile), calculado FORA desta regra pura.

    "Com negócio no pregão" exige ``trades > 0`` E ``last`` presente: um
    ``last`` com ``trades == 0`` pode ser de pregão anterior e não indica
    nada sobre hoje.
    """
    lado_agredido = quote.bid if side is Side.SELL else quote.ask
    if lado_agredido is not None:
        return LegPremium(lado_agredido, PriceQuality.EXECUTAVEL)
    if quote.is_book_empty and quote.trades > 0 and quote.last is not None:
        return LegPremium(quote.last, PriceQuality.INDICATIVO)
    return None

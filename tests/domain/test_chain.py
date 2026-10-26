"""Cadeia de opções (ADR-0003) e preço executável por lado (ADR-0004)."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, tzinfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from options_engine.domain.model.chain import (
    LegPremium,
    OptionChain,
    OptionQuote,
    PriceQuality,
    executable_premium,
    worst_quality,
)
from options_engine.domain.model.contracts import OptionContract
from options_engine.domain.model.enums import Side
from options_engine.domain.model.errors import InvalidDomainValueError
from tests.domain._builders import make_contract, make_snapshot, make_terms

INSTANTE = datetime(2026, 10, 23, 18, 0, tzinfo=UTC)


def make_series(symbol: str, strike: float = 30.0, underlying: str = "PETR4") -> OptionContract:
    return make_contract(symbol=symbol, terms=make_terms(underlying=underlying, strike=strike))


def make_quote(
    contract: OptionContract | None = None,
    bid: float | None = 1.20,
    ask: float | None = 1.25,
    last: float | None = 1.22,
    trades: int = 37,
    volume: float = 52_800.0,
    timestamp: datetime = INSTANTE,
) -> OptionQuote:
    """Cotação VÁLIDA por default (book completo, com negócio no pregão)."""
    return OptionQuote(
        contract=contract if contract is not None else make_contract(),
        bid=bid,
        ask=ask,
        last=last,
        trades=trades,
        volume=volume,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# OptionQuote — lado ausente é None, nunca 0 (ADR-0003)
# ---------------------------------------------------------------------------


def _quote_com_um_lado(campo: str, valor: float) -> OptionQuote:
    """Só ``campo`` presente: isola o valor sob exame da checagem bid <= ask."""
    lados: dict[str, float | None] = {"bid": None, "ask": None, "last": None}
    lados[campo] = valor
    return make_quote(bid=lados["bid"], ask=lados["ask"], last=lados["last"])


def test_cotacao_valida_com_book_completo() -> None:
    quote = make_quote()
    assert (quote.bid, quote.ask, quote.last) == (1.20, 1.25, 1.22)


def test_todos_os_lados_ausentes_sao_legais() -> None:
    """Livro vazio e sem negócio é dado real (série ilíquida), não erro."""
    quote = make_quote(bid=None, ask=None, last=None, trades=0, volume=0.0)
    assert (quote.bid, quote.ask, quote.last) == (None, None, None)


@pytest.mark.parametrize("campo", ["bid", "ask", "last"])
def test_zero_de_sem_oferta_e_irrepresentavel(campo: str) -> None:
    """O zero da fonte vira None no adapter; se vazar, falha alto aqui."""
    with pytest.raises(InvalidDomainValueError, match="ADR-0003"):
        _quote_com_um_lado(campo, 0.0)


@pytest.mark.parametrize("campo", ["bid", "ask", "last"])
@pytest.mark.parametrize("valor", [-0.01, float("nan"), float("inf"), float("-inf")])
def test_lado_negativo_ou_nao_finito_e_irrepresentavel(campo: str, valor: float) -> None:
    with pytest.raises(InvalidDomainValueError, match=campo):
        _quote_com_um_lado(campo, valor)


def test_book_cruzado_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError, match="cruzado"):
        make_quote(bid=1.30, ask=1.25)


def test_book_travado_e_legal() -> None:
    """bid == ask é spread zero — coerente, como no MarketSnapshot."""
    quote = make_quote(bid=1.25, ask=1.25)
    assert quote.bid == quote.ask


@pytest.mark.parametrize(("bid", "ask"), [(1.30, None), (None, 0.90)])
def test_book_de_um_lado_so_nao_compara_com_o_lado_ausente(
    bid: float | None, ask: float | None
) -> None:
    """Sem o outro lado não há spread: qualquer valor positivo é legal."""
    quote = make_quote(bid=bid, ask=ask)
    assert (quote.bid, quote.ask) == (bid, ask)


def test_trades_negativo_e_irrepresentavel() -> None:
    with pytest.raises(InvalidDomainValueError, match="trades"):
        make_quote(trades=-1)


@pytest.mark.parametrize("volume", [-1.0, float("nan"), float("inf")])
def test_volume_negativo_ou_nao_finito_e_irrepresentavel(volume: float) -> None:
    with pytest.raises(InvalidDomainValueError, match="volume"):
        make_quote(volume=volume)


def test_last_sem_negocio_no_pregao_e_legal() -> None:
    """Fontes trazem o último preço de pregão anterior com trades == 0:
    não é incoerência da cotação — a regra de preço é quem o descarta."""
    quote = make_quote(bid=None, ask=None, last=1.10, trades=0, volume=0.0)
    assert quote.last == 1.10


class _FusoSemOffset(tzinfo):
    """tzinfo presente que ainda é naive na prática (utcoffset None)."""

    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None


@pytest.mark.parametrize(
    "timestamp",
    [datetime(2026, 10, 23, 18, 0), datetime(2026, 10, 23, 18, 0, tzinfo=_FusoSemOffset())],
    ids=["naive", "tzinfo-sem-offset"],
)
def test_timestamp_naive_e_irrepresentavel(timestamp: datetime) -> None:
    with pytest.raises(InvalidDomainValueError, match="tz-aware"):
        make_quote(timestamp=timestamp)


def test_cotacao_e_imutavel() -> None:
    quote = make_quote()
    with pytest.raises(FrozenInstanceError):
        quote.bid = 0.0  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste


# ---------------------------------------------------------------------------
# OptionChain — mesmo subjacente, tickers únicos
# ---------------------------------------------------------------------------


def test_cadeia_valida_preserva_o_subjacente_e_a_ordem_das_series() -> None:
    quotes = (
        make_quote(contract=make_series("PETRK300", strike=30.0)),
        make_quote(contract=make_series("PETRK320", strike=32.0)),
    )
    chain = OptionChain(underlying=make_snapshot(), quotes=quotes)
    assert chain.underlying.underlying_symbol == "PETR4"
    assert chain.quotes == quotes


def test_cadeia_vazia_e_legal() -> None:
    """Subjacente sem séries no pregão é informação para o painel, não erro."""
    chain = OptionChain(underlying=make_snapshot(), quotes=())
    assert chain.quotes == ()


def test_serie_de_outro_subjacente_e_irrepresentavel() -> None:
    quotes = (
        make_quote(contract=make_series("PETRK300")),
        make_quote(contract=make_series("VALEK600", strike=60.0, underlying="VALE3")),
    )
    with pytest.raises(InvalidDomainValueError, match="VALEK600"):
        OptionChain(underlying=make_snapshot(underlying_symbol="PETR4"), quotes=quotes)


def test_ticker_repetido_e_irrepresentavel() -> None:
    """Duas cotações da mesma série tornariam ambíguo o book dela."""
    quotes = (
        make_quote(contract=make_series("PETRK300"), bid=1.20),
        make_quote(contract=make_series("PETRK320", strike=32.0)),
        make_quote(contract=make_series("PETRK300"), bid=1.10),
    )
    with pytest.raises(InvalidDomainValueError, match="PETRK300"):
        OptionChain(underlying=make_snapshot(), quotes=quotes)


def test_termos_identicos_com_tickers_distintos_sao_legais() -> None:
    """Identidade é o ticker (ARCH §2.2): mesmos termos, instrumentos distintos."""
    quotes = (
        make_quote(contract=make_series("PETRK300")),
        make_quote(contract=make_series("PETRK300E")),
    )
    chain = OptionChain(underlying=make_snapshot(), quotes=quotes)
    assert len(chain.quotes) == 2


def test_cadeia_e_imutavel() -> None:
    chain = OptionChain(underlying=make_snapshot(), quotes=(make_quote(),))
    with pytest.raises(FrozenInstanceError):
        chain.quotes = ()  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste


# ---------------------------------------------------------------------------
# PriceQuality e worst_quality (ADR-0004)
# ---------------------------------------------------------------------------


def test_qualidades_declaradas_do_melhor_para_o_pior() -> None:
    """A ordem de declaração É a ordem de qualidade usada por worst_quality —
    reordenar os membros muda o ranking em silêncio; este teste trava isso."""
    assert list(PriceQuality) == [
        PriceQuality.EXECUTAVEL,
        PriceQuality.INDICATIVO,
        PriceQuality.TEORICO,
    ]


EXEC, IND, TEO = PriceQuality.EXECUTAVEL, PriceQuality.INDICATIVO, PriceQuality.TEORICO


@pytest.mark.parametrize(
    ("pernas", "esperada"),
    [
        ((EXEC,), EXEC),
        ((IND,), IND),
        ((TEO,), TEO),
        ((EXEC, EXEC, EXEC, EXEC), EXEC),
        ((EXEC, IND), IND),
        ((IND, EXEC), IND),
        ((EXEC, TEO, IND), TEO),
        ((TEO, EXEC, EXEC, EXEC), TEO),
    ],
)
def test_estrutura_vale_a_pior_perna(
    pernas: tuple[PriceQuality, ...], esperada: PriceQuality
) -> None:
    assert worst_quality(pernas) is esperada


def test_pior_qualidade_aceita_iteravel_de_uma_passada() -> None:
    """Iterable, não Sequence: um gerador sobre as pernas é consumido uma vez só."""
    assert worst_quality(q for q in (EXEC, IND, EXEC)) is IND


def test_pior_qualidade_de_nenhuma_perna_e_erro() -> None:
    """Vazio não é EXECUTAVEL: rotularia como executável algo que não existe."""
    with pytest.raises(InvalidDomainValueError):
        worst_quality(())


@given(pernas=st.lists(st.sampled_from(PriceQuality), min_size=1, max_size=6))
def test_pior_qualidade_independe_da_ordem_das_pernas(pernas: list[PriceQuality]) -> None:
    assert worst_quality(pernas) is worst_quality(reversed(pernas))
    assert worst_quality(pernas) in pernas


# ---------------------------------------------------------------------------
# LegPremium — prêmio nunca sai sem rótulo
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("quality", list(PriceQuality))
@pytest.mark.parametrize("premium", [-0.01, float("nan"), float("inf")])
def test_premio_negativo_ou_nao_finito_e_irrepresentavel(
    premium: float, quality: PriceQuality
) -> None:
    with pytest.raises(InvalidDomainValueError):
        LegPremium(premium, quality)


@pytest.mark.parametrize("quality", [EXEC, IND])
def test_preco_observado_nunca_e_zero(quality: PriceQuality) -> None:
    """Lado ausente é None (ADR-0003): zero observado é sentinela vazada."""
    with pytest.raises(InvalidDomainValueError, match="ADR-0003"):
        LegPremium(0.0, quality)


def test_teorico_admite_zero() -> None:
    """BS de série muito fora do dinheiro pode valer zero — informação, não erro."""
    assert LegPremium(0.0, TEO).premium == 0.0


def test_premio_e_imutavel() -> None:
    """Par indivisível (ADR-0004): re-rotular um INDICATIVO como EXECUTAVEL
    depois de construído faria sair um número com o rótulo errado."""
    premio = LegPremium(1.0, IND)
    with pytest.raises(FrozenInstanceError):
        premio.quality = EXEC  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste


# ---------------------------------------------------------------------------
# executable_premium — a tabela da ADR-0004, linha a linha
# ---------------------------------------------------------------------------

BID, ASK, LAST = 1.20, 1.25, 1.22


@pytest.mark.parametrize(
    ("bid", "ask", "last", "trades", "side", "esperado"),
    [
        # bid e ask presentes: vendida usa bid, comprada usa ask — nunca o mid.
        (BID, ASK, LAST, 37, Side.SELL, LegPremium(BID, EXEC)),
        (BID, ASK, LAST, 37, Side.BUY, LegPremium(ASK, EXEC)),
        # só bid: EXECUTAVEL só para venda; a perna comprada fica sem preço.
        (BID, None, LAST, 37, Side.SELL, LegPremium(BID, EXEC)),
        (BID, None, LAST, 37, Side.BUY, None),
        # só ask: EXECUTAVEL só para compra; a perna vendida fica sem preço.
        (None, ASK, LAST, 37, Side.SELL, None),
        (None, ASK, LAST, 37, Side.BUY, LegPremium(ASK, EXEC)),
        # As mesmas linhas EXECUTAVEL sem negócio e sem last: o prêmio não
        # muda. Filtro de liquidez é parâmetro do comando (ADR-0004), não
        # condição escondida na regra de preço.
        (BID, ASK, None, 0, Side.SELL, LegPremium(BID, EXEC)),
        (BID, ASK, None, 0, Side.BUY, LegPremium(ASK, EXEC)),
        (BID, None, None, 0, Side.SELL, LegPremium(BID, EXEC)),
        (None, ASK, None, 0, Side.BUY, LegPremium(ASK, EXEC)),
        # nenhum lado, com negócio no pregão: last, INDICATIVO nos dois lados.
        (None, None, LAST, 37, Side.SELL, LegPremium(LAST, IND)),
        (None, None, LAST, 37, Side.BUY, LegPremium(LAST, IND)),
        # nenhum lado, sem negócio: TEORICO, calculado fora da regra pura.
        (None, None, LAST, 0, Side.SELL, None),
        (None, None, LAST, 0, Side.BUY, None),
    ],
    ids=[
        "book-completo-vendida",
        "book-completo-comprada",
        "so-bid-vendida",
        "so-bid-comprada",
        "so-ask-vendida",
        "so-ask-comprada",
        "book-completo-sem-negocio-vendida",
        "book-completo-sem-negocio-comprada",
        "so-bid-sem-negocio-vendida",
        "so-ask-sem-negocio-comprada",
        "book-vazio-com-negocio-vendida",
        "book-vazio-com-negocio-comprada",
        "book-vazio-sem-negocio-vendida",
        "book-vazio-sem-negocio-comprada",
    ],
)
def test_tabela_da_adr_0004(
    bid: float | None,
    ask: float | None,
    last: float | None,
    trades: int,
    side: Side,
    esperado: LegPremium | None,
) -> None:
    # `last` presente nas linhas com book prova que ele só é usado com o book
    # vazio; as linhas sem negócio provam que EXECUTAVEL não depende dele.
    quote = make_quote(bid=bid, ask=ask, last=last, trades=trades)
    assert executable_premium(quote, side) == esperado


def test_book_de_um_lado_so_nao_cai_para_o_last() -> None:
    """Só bid + perna comprada é "sem preço" na ADR-0004, mesmo com negócio no
    pregão: INDICATIVO é exclusivo do book vazio, não um fallback por perna."""
    quote = make_quote(bid=BID, ask=None, last=LAST, trades=37)
    assert executable_premium(quote, Side.BUY) is None
    assert not quote.is_book_empty


def test_last_sem_negocio_no_pregao_nao_e_indicativo() -> None:
    """trades == 0: o last pode ser de pregão anterior — vai para o TEORICO."""
    quote = make_quote(bid=None, ask=None, last=LAST, trades=0)
    assert executable_premium(quote, Side.SELL) is None
    assert quote.is_book_empty


def test_negocio_sem_last_nao_inventa_preco() -> None:
    quote = make_quote(bid=None, ask=None, last=None, trades=37)
    assert executable_premium(quote, Side.SELL) is None


@pytest.mark.parametrize(
    ("bid", "ask", "vazio"),
    [(BID, ASK, False), (BID, None, False), (None, ASK, False), (None, None, True)],
)
def test_book_vazio_so_sem_nenhum_lado(bid: float | None, ask: float | None, vazio: bool) -> None:
    assert make_quote(bid=bid, ask=ask).is_book_empty is vazio


# --- propriedades sobre cotações arbitrárias ---------------------------------
# Preços em centavos inteiros: valores exatos, a igualdade mede a regra.

_LADO = st.one_of(st.none(), st.integers(min_value=1, max_value=5_000).map(lambda c: c / 100))
# "Sem negócio" (trades == 0) como ramo próprio: sorteado só como o mínimo
# de um intervalo, raramente coincide com book vazio e last presente — a
# fronteira entre INDICATIVO e TEORICO ficaria fora da propriedade.
_TRADES = st.one_of(st.just(0), st.integers(min_value=1, max_value=500))


@st.composite
def st_quote(draw: st.DrawFn) -> OptionQuote:
    bid, ask = draw(_LADO), draw(_LADO)
    if bid is not None and ask is not None and bid > ask:
        bid, ask = ask, bid
    return make_quote(
        bid=bid,
        ask=ask,
        last=draw(_LADO),
        trades=draw(_TRADES),
    )


@given(quote=st_quote(), side=st.sampled_from(Side))
def test_preco_nunca_e_inventado_nem_omitido(quote: OptionQuote, side: Side) -> None:
    """Bicondicional, sem saída antecipada: toda cotação cai em exatamente
    uma linha da tabela, e o prêmio é sempre um preço observado da própria
    série (nunca mid, nunca interpolado).

    - lado agredido presente → esse lado, EXECUTAVEL (com qualquer
      ``trades`` e ``last``);
    - book vazio, ``trades > 0`` e ``last`` presente → ``last``, INDICATIVO;
    - qualquer outro caso → ``None``.
    """
    lado_agredido = quote.bid if side is Side.SELL else quote.ask
    resultado = executable_premium(quote, side)
    if lado_agredido is not None:
        assert resultado == LegPremium(lado_agredido, PriceQuality.EXECUTAVEL)
    elif quote.is_book_empty and quote.trades > 0 and quote.last is not None:
        assert resultado == LegPremium(quote.last, PriceQuality.INDICATIVO)
    else:
        assert resultado is None


@given(quote=st_quote())
def test_vender_nunca_recebe_mais_do_que_comprar_paga(quote: OptionQuote) -> None:
    """Com as duas pernas executáveis, prêmio da venda <= prêmio da compra —
    a assimetria que impede o ranking de premiar spread largo."""
    venda = executable_premium(quote, Side.SELL)
    compra = executable_premium(quote, Side.BUY)
    if venda is not None and compra is not None:
        assert venda.premium <= compra.premium

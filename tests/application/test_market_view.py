"""``MarketViewService`` com mercado falso: PETR4 a 30, sigma 0,30, pregão 2026-10-23."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET, StaticHolidayCalendar
from options_engine.adapters.outbound.tryd.settings import VENCIMENTOS_PADRAO
from options_engine.application.ports.inbound import (
    DEFAULT_CHAIN_EXPIRIES,
    MarketViewUseCase,
    WatchRow,
)
from options_engine.application.ports.outbound import CadastroFreshness
from options_engine.application.use_cases.market_view import MarketViewService
from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.model.chain import OptionChain, OptionQuote, RejectedSeries
from options_engine.domain.model.conventions import Compounding, DayCountConvention, RiskFreeRate
from options_engine.domain.model.enums import ExerciseStyle, OptionType
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    UnderlyingUnavailableError,
    UnknownSymbolError,
)
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.pricing.smile import SeriesMarket, build_smile, series_risk
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.domain._builders import make_contract, make_snapshot, make_terms

PREGAO = date(2026, 10, 23)
NOVEMBRO = date(2026, 11, 19)
DEZEMBRO = date(2026, 12, 18)
JANEIRO = date(2027, 1, 21)
INSTANTE = datetime(2026, 10, 23, 21, 0, tzinfo=UTC)  # 18h em São Paulo
CDI = RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252)
CALENDARIO = StaticHolidayCalendar.from_packaged_data()
SIGMA = 0.30
SPOT = 30.0


def _tau(vencimento: date) -> float:
    return CALENDARIO.business_days_between(PREGAO, vencimento) / 252.0


def _quote(
    symbol: str,
    strike: float,
    option_type: OptionType,
    expiry: date = NOVEMBRO,
    *,
    bid: float | str | None = "bs",
    ask: float | str | None = "bs",
) -> OptionQuote:
    preco = bs_price(
        SPOT, strike, _tau(expiry), CDI.as_continuous(), SIGMA, is_call=option_type.is_call
    )
    return OptionQuote(
        contract=make_contract(
            symbol=symbol,
            terms=make_terms(
                underlying="PETR4",
                strike=strike,
                option_type=option_type,
                expiry=expiry,
                exercise_style=ExerciseStyle.EUROPEAN
                if option_type is OptionType.PUT
                else ExerciseStyle.AMERICAN,
            ),
        ),
        bid=round(preco - 0.01, 2) if bid == "bs" else bid,  # type: ignore[arg-type]
        ask=round(preco + 0.01, 2) if ask == "bs" else ask,  # type: ignore[arg-type]
        last=round(preco, 2),
        trades=12,
        volume=1200.0 * preco,
        timestamp=INSTANTE,
    )


def _quotes() -> tuple[OptionQuote, ...]:
    """Fora de ordem de propósito: o serviço ordena."""
    return (
        _quote("PETRW300", 30.0, OptionType.PUT),
        _quote("PETRK310", 31.0, OptionType.CALL),
        _quote("PETRK290", 29.0, OptionType.CALL),
        _quote("PETRK300", 30.0, OptionType.CALL),
        _quote("PETRW290", 29.0, OptionType.PUT),
        _quote("PETRL300", 30.0, OptionType.CALL, DEZEMBRO),
        _quote("PETRX300", 30.0, OptionType.PUT, DEZEMBRO),
        _quote("PETRA300", 30.0, OptionType.CALL, JANEIRO),
    )


def _chain(
    quotes: tuple[OptionQuote, ...] | None = None,
    *,
    timestamp: datetime = INSTANTE,
    rejected: tuple[RejectedSeries, ...] = (),
) -> OptionChain:
    return OptionChain(
        underlying=make_snapshot(
            underlying_symbol="PETR4",
            spot=SPOT,
            bid=29.99,
            ask=30.01,
            mid=SPOT,
            rate=CDI.rate,
            compounding=CDI.compounding,
            vol=0.25,
            timestamp=timestamp,
        ),
        quotes=_quotes() if quotes is None else quotes,
        rejected_series=rejected,
    )


def _cotacao(symbol: str) -> UnderlyingQuote:
    return UnderlyingQuote(
        symbol=symbol,
        last=30.0,
        bid=29.99,
        ask=30.01,
        previous_close=29.5,
        trades=1000,
        volume=3.0e7,
        timestamp=INSTANTE,
        source=DataSource.AO_VIVO,
    )


@dataclass
class _Mercado:
    """``MarketPort`` em memória; ``healths`` é a sequência que ``health()`` devolve."""

    chains: dict[str, OptionChain] = field(default_factory=lambda: {"PETR4": _chain()})
    known: tuple[str, ...] = ("PETR4", "VALE3")
    healths: list[DataSource] = field(default_factory=list)
    unavailable: str | None = None
    watched: list[tuple[tuple[str, ...], tuple[str, ...]]] = field(default_factory=list)

    def health(self) -> DataSource:
        if len(self.healths) > 1:
            return self.healths.pop(0)
        return self.healths[0] if self.healths else DataSource.AO_VIVO

    def watch(self, underlyings: Sequence[str], chain_symbols: Sequence[str]) -> None:
        self.watched.append((tuple(underlyings), tuple(chain_symbols)))

    def get_quotes(self, symbols: Sequence[str]) -> Mapping[str, UnderlyingQuote | str]:
        return {
            s: (_cotacao(s) if s == "PETR4" else "aguardando dados")
            if s in self.known
            else "ativo desconhecido"
            for s in symbols
        }

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        if self.unavailable is not None:
            raise UnderlyingUnavailableError(self.unavailable)
        if underlying_symbol not in self.chains:
            raise UnknownSymbolError(f"desconhecido: {underlying_symbol!r}")
        return self.chains[underlying_symbol]


def _servico(
    mercado: _Mercado | None = None,
    *,
    freshness: CadastroFreshness | str = "nenhum cadastro importado",
    cotahist_range: tuple[date, date] | None = None,
) -> MarketViewService:
    return MarketViewService(
        _Mercado() if mercado is None else mercado,
        CALENDARIO,
        B3_UTC_OFFSET,
        freshness=lambda: freshness,
        cotahist_range=lambda: cotahist_range,
    )


def test_cumpre_o_protocol_do_use_case() -> None:
    assert isinstance(_servico(), MarketViewUseCase)


def test_padrao_de_vencimentos_e_o_mesmo_que_a_fonte_ao_vivo_assina() -> None:
    assert DEFAULT_CHAIN_EXPIRIES == VENCIMENTOS_PADRAO


def test_blocos_por_vencimento_com_os_dias_uteis_do_calendario() -> None:
    vista = _servico().chain("PETR4")
    assert [b.expiry for b in vista.expiries] == [NOVEMBRO, DEZEMBRO]
    assert [b.business_days for b in vista.expiries] == [
        CALENDARIO.business_days_between(PREGAO, NOVEMBRO),
        CALENDARIO.business_days_between(PREGAO, DEZEMBRO),
    ]
    assert vista.expiries[0].business_days == 18
    assert [b.expiry for b in _servico().chain("PETR4", expiries=3).expiries] == [
        NOVEMBRO,
        DEZEMBRO,
        JANEIRO,
    ]


def test_linhas_por_strike_e_no_mesmo_strike_a_call_antes_da_put() -> None:
    novembro = _servico().chain("PETR4").expiries[0]
    assert [r.symbol for r in novembro.rows] == [
        "PETRK290",
        "PETRW290",
        "PETRK300",
        "PETRW300",
        "PETRK310",
    ]


def test_cabecalho_da_cadeia_traz_spot_hora_e_rejeitadas() -> None:
    rejeitada = RejectedSeries("PETRK999", "sem estilo de exercício no cadastro")
    mercado = _Mercado(chains={"PETR4": _chain(rejected=(rejeitada,))})
    vista = _servico(mercado).chain("PETR4")
    assert (vista.symbol, vista.spot, vista.timestamp) == ("PETR4", SPOT, INSTANTE)
    assert vista.rejected == (rejeitada,)


def test_iv_e_delta_sao_os_do_series_risk_do_dominio() -> None:
    novembro = _servico().chain("PETR4").expiries[0]
    mercado = SeriesMarket(SPOT, CDI.as_continuous(), _tau(NOVEMBRO))
    do_vencimento = [q for q in _quotes() if q.contract.terms.expiry == NOVEMBRO]
    smile = build_smile(NOVEMBRO, do_vencimento, mercado)
    for quote in do_vencimento:
        esperado = series_risk(quote, smile, mercado)
        assert esperado is not None and esperado.implied_vol is not None
        (linha,) = [r for r in novembro.rows if r.symbol == quote.contract.symbol]
        assert linha.implied_vol is not None and linha.delta is not None
        assert_close(linha.implied_vol, esperado.implied_vol, rel=REL_SELF, abs_=ABS_SELF_FLOOR)
        assert_close(linha.delta, esperado.delta, rel=REL_SELF, abs_=ABS_SELF_FLOOR)
        assert abs(linha.implied_vol - SIGMA) < 0.01  # o book de 1 centavo mal mexe na vol


def test_serie_com_um_lado_so_nao_tem_iv_e_o_delta_vem_do_smile() -> None:
    so_compra = _quote("PETRK300", 30.0, OptionType.CALL, ask=None)
    quotes = (*(q for q in _quotes() if q.contract.symbol != "PETRK300"), so_compra)
    novembro = _servico(_Mercado(chains={"PETR4": _chain(quotes)})).chain("PETR4").expiries[0]
    (linha,) = [r for r in novembro.rows if r.symbol == "PETRK300"]
    assert linha.implied_vol is None
    assert (linha.bid, linha.ask) == (so_compra.bid, None)

    mercado = SeriesMarket(SPOT, CDI.as_continuous(), _tau(NOVEMBRO))
    do_vencimento = [q for q in quotes if q.contract.terms.expiry == NOVEMBRO]
    smile = build_smile(NOVEMBRO, do_vencimento, mercado)
    esperado = series_risk(so_compra, smile, mercado)
    assert esperado is not None and esperado.vol == smile.vol_at(30.0)
    assert linha.delta is not None
    assert_close(linha.delta, esperado.delta, rel=REL_SELF, abs_=ABS_SELF_FLOOR)


def test_serie_sem_vol_possivel_fica_sem_iv_e_sem_delta() -> None:
    sozinha = _quote("PETRK300", 30.0, OptionType.CALL, bid=None, ask=None)
    vista = _servico(_Mercado(chains={"PETR4": _chain((sozinha,))})).chain("PETR4")
    (linha,) = vista.expiries[0].rows
    assert (linha.implied_vol, linha.delta) == (None, None)


def test_linha_carrega_os_termos_o_book_e_a_liquidez_da_serie() -> None:
    quote = _quote("PETRW290", 29.0, OptionType.PUT)
    (linha,) = [r for r in _servico().chain("PETR4").expiries[0].rows if r.symbol == "PETRW290"]
    assert (linha.option_type, linha.strike, linha.exercise_style) == (
        OptionType.PUT,
        29.0,
        ExerciseStyle.EUROPEAN,
    )
    assert (linha.bid, linha.ask, linha.last) == (quote.bid, quote.ask, quote.last)
    assert (linha.trades, linha.volume) == (quote.trades, quote.volume)


def test_data_de_valoracao_e_a_da_cotacao_do_ativo_no_fuso_da_b3() -> None:
    # 01h UTC de 24/10 ainda é 22h de 23/10 em São Paulo: o pregão é o de 23/10.
    tarde = datetime(2026, 10, 24, 1, 0, tzinfo=UTC)
    vista = _servico(_Mercado(chains={"PETR4": _chain(timestamp=tarde)})).chain("PETR4")
    assert vista.expiries[0].business_days == 18


def test_vencimento_que_ja_passou_fica_fora_e_o_de_hoje_entra_com_tau_zero() -> None:
    vencido = _quote("PETRJ300", 30.0, OptionType.CALL, NOVEMBRO)
    no_dia = datetime(2026, 11, 19, 20, 0, tzinfo=UTC)  # 17h de 19/11 em São Paulo
    depois = datetime(2026, 11, 20, 20, 0, tzinfo=UTC)
    hoje = _servico(_Mercado(chains={"PETR4": _chain((vencido,), timestamp=no_dia)}))
    (bloco,) = hoje.chain("PETR4").expiries
    assert bloco.business_days == 0
    (linha,) = bloco.rows
    assert linha.implied_vol is None and linha.delta is not None  # degrau no vencimento
    ontem = _servico(_Mercado(chains={"PETR4": _chain((vencido,), timestamp=depois)}))
    assert ontem.chain("PETR4").expiries == ()


@pytest.mark.parametrize(
    ("antes", "depois", "rotulo"),
    [
        (DataSource.AO_VIVO, DataSource.AO_VIVO, DataSource.AO_VIVO),
        (DataSource.ATRASADO, DataSource.ATRASADO, DataSource.ATRASADO),
        (DataSource.AO_VIVO, DataSource.FIM_DE_DIA, DataSource.FIM_DE_DIA),
        (DataSource.FIM_DE_DIA, DataSource.AO_VIVO, DataSource.FIM_DE_DIA),
        (DataSource.AO_VIVO, DataSource.ATRASADO, DataSource.ATRASADO),
    ],
)
def test_rotulo_da_cadeia_e_a_saude_menos_fresca_entre_antes_e_depois(
    antes: DataSource, depois: DataSource, rotulo: DataSource
) -> None:
    assert _servico(_Mercado(healths=[antes, depois])).chain("PETR4").source is rotulo


def test_ativo_desconhecido_e_indisponivel_sobem_como_erro_de_dominio() -> None:
    with pytest.raises(UnknownSymbolError):
        _servico().chain("PETR44")
    with pytest.raises(UnderlyingUnavailableError, match="aguardando dados do Tryd"):
        _servico(_Mercado(unavailable="PETR4: aguardando dados do Tryd")).chain("PETR4")


def test_vencimentos_precisa_ser_ao_menos_um() -> None:
    with pytest.raises(InvalidDomainValueError, match="vencimentos"):
        _servico().chain("PETR4", expiries=0)


def test_so_aceita_a_convencao_de_dias_uteis() -> None:
    with pytest.raises(InvalidDomainValueError, match="BUSINESS_252"):
        MarketViewService(
            _Mercado(),
            CALENDARIO,
            B3_UTC_OFFSET,
            DayCountConvention.CALENDAR_365,
            freshness=lambda: "x",
            cotahist_range=lambda: None,
        )


def test_lista_traz_cotacao_ou_motivo_na_ordem_pedida() -> None:
    linhas = _servico().quotes(["PETR4", "PETR44", "VALE3"])
    assert [linha.symbol for linha in linhas] == ["PETR4", "PETR44", "VALE3"]
    assert linhas[0].quote == _cotacao("PETR4") and linhas[0].reason is None
    assert (linhas[1].quote, linhas[1].reason) == (None, "ativo desconhecido")
    assert (linhas[2].quote, linhas[2].reason) == (None, "aguardando dados")


def test_linha_exige_cotacao_ou_motivo() -> None:
    with pytest.raises(InvalidDomainValueError):
        WatchRow("PETR4", None, None)
    with pytest.raises(InvalidDomainValueError):
        WatchRow("PETR4", _cotacao("PETR4"), "aguardando dados")


def test_follow_assina_a_lista_e_a_cadeia_aberta() -> None:
    mercado = _Mercado()
    servico = _servico(mercado)
    servico.follow(["PETR4", "VALE3"], "PETR4")
    servico.follow(["PETR4"], None)
    assert mercado.watched == [(("PETR4", "VALE3"), ("PETR4",)), (("PETR4",), ())]


def test_status_com_cadastro_datado_e_faixa_dos_cotahist() -> None:
    idade = CadastroFreshness(date(2026, 10, 20), 3, False)
    faixa = (date(2026, 1, 2), PREGAO)
    status = _servico(
        _Mercado(healths=[DataSource.ATRASADO]), freshness=idade, cotahist_range=faixa
    ).status()
    assert status.source is DataSource.ATRASADO
    assert (status.cadastro, status.cadastro_reason) == (idade, None)
    assert status.cotahist_range == faixa


def test_status_sem_cadastro_traz_o_motivo() -> None:
    status = _servico(freshness="cadastro sem data no nome do arquivo").status()
    assert (status.cadastro, status.cadastro_reason) == (
        None,
        "cadastro sem data no nome do arquivo",
    )
    assert status.cotahist_range is None

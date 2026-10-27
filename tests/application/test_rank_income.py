"""``RankIncomeOpportunitiesService`` com fake em memória — casos do ROADMAP (Sprint 5).

Cadeias sintéticas de PETR4 (spot 30) com prêmios do kernel em sigma = 0,30
e book de 1 centavo de cada lado; pregão 2026-10-23 (18h em São Paulo),
vencimento 2026-11-19 (18 du) e, quando dito, 2026-10-23 (vence hoje).
"""

import math
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET, StaticHolidayCalendar
from options_engine.application.ports.inbound import (
    RankIncomeCommand,
    RankIncomeOpportunitiesUseCase,
)
from options_engine.application.use_cases.rank_income import RankIncomeOpportunitiesService
from options_engine.domain.income import IncomeStructure
from options_engine.domain.income.ranking import ExclusionScope, IncomeRanking, RankingCriterion
from options_engine.domain.kernel.black_scholes import bs_price
from options_engine.domain.model.chain import OptionChain, OptionQuote, PriceQuality, RejectedSeries
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.conventions import Compounding, DayCountConvention, RiskFreeRate
from options_engine.domain.model.enums import ExerciseStyle, OptionType, PricingApproximation
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    UnderlyingUnavailableError,
    UnknownSymbolError,
)
from options_engine.domain.pricing.black_scholes import BlackScholesPricingModel
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.domain._builders import make_contract, make_snapshot, make_terms
from tests.income._builders import make_cost_schedule, reference_cost_schedule

PREGAO = date(2026, 10, 23)
NOVEMBRO = date(2026, 11, 19)
INSTANTE = datetime(2026, 10, 23, 21, 0, tzinfo=UTC)  # 18h em São Paulo
CDI = RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252)
CALENDARIO = StaticHolidayCalendar.from_packaged_data()
SIGMA = 0.30


def _tau(vencimento: date) -> float:
    return CALENDARIO.business_days_between(PREGAO, vencimento) / 252.0


def _quote(
    symbol: str,
    strike: float,
    option_type: OptionType,
    *,
    expiry: date = NOVEMBRO,
    style: ExerciseStyle = ExerciseStyle.EUROPEAN,
    bid: float | str | None = "bs",
    ask: float | str | None = "bs",
    last: float | None = None,
    trades: int = 40,
    spot: float = 30.0,
) -> OptionQuote:
    preco = bs_price(
        spot,
        strike,
        _tau(expiry),
        CDI.as_continuous(),
        SIGMA,
        is_call=option_type is OptionType.CALL,
    )
    return OptionQuote(
        contract=make_contract(
            symbol=symbol,
            terms=make_terms(
                underlying="PETR4",
                strike=strike,
                option_type=option_type,
                expiry=expiry,
                exercise_style=style,
            ),
        ),
        bid=round(preco - 0.01, 2) if bid == "bs" else bid,  # type: ignore[arg-type]
        ask=round(preco + 0.01, 2) if ask == "bs" else ask,  # type: ignore[arg-type]
        last=last if last is not None else round(preco, 2),
        trades=trades,
        volume=100.0 * trades * preco,
        timestamp=INSTANTE,
    )


def _cadeia_completa(**overrides: OptionQuote) -> tuple[OptionQuote, ...]:
    """Calls 28..34 e puts 26..32 com book completo; ``overrides`` troca séries pelo ticker."""
    quotes = {
        f"PETRK{int(k * 10)}": _quote(f"PETRK{int(k * 10)}", k, OptionType.CALL)
        for k in (28.0, 29.0, 30.0, 31.0, 32.0, 33.0, 34.0)
    }
    quotes |= {
        f"PETRW{int(k * 10)}": _quote(f"PETRW{int(k * 10)}", k, OptionType.PUT)
        for k in (26.0, 27.0, 28.0, 29.0, 30.0, 31.0, 32.0)
    }
    quotes |= overrides
    return tuple(quotes.values())


def _chain(
    quotes: tuple[OptionQuote, ...],
    *,
    rejected: tuple[RejectedSeries, ...] = (),
    book_available: bool = True,
    timestamp: datetime = INSTANTE,
) -> OptionChain:
    return OptionChain(
        underlying=make_snapshot(
            underlying_symbol="PETR4",
            spot=30.0,
            bid=29.99,
            ask=30.01,
            mid=30.0,
            rate=CDI.rate,
            compounding=CDI.compounding,
            vol=0.25,
            timestamp=timestamp,
        ),
        quotes=quotes,
        rejected_series=rejected,
        underlying_book_available=book_available,
    )


@dataclass
class _FakeChains:
    """Cadeias por símbolo; ``unavailable`` levanta ``UnderlyingUnavailableError``."""

    chains: dict[str, OptionChain]
    unavailable: dict[str, str] | None = None
    consultas: int = 0

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        self.consultas += 1
        if self.unavailable and underlying_symbol in self.unavailable:
            raise UnderlyingUnavailableError(self.unavailable[underlying_symbol])
        if underlying_symbol not in self.chains:
            raise UnknownSymbolError(f"desconhecido: {underlying_symbol!r}")
        return self.chains[underlying_symbol]


def _service(fake: _FakeChains, **overrides: object) -> RankIncomeOpportunitiesService:
    campos: dict[str, object] = {
        "chains": fake,
        "calendar": CALENDARIO,
        "model": BlackScholesPricingModel(),
        "cost_schedules": (replace(reference_cost_schedule(), valid_from=date(2025, 8, 1)),),
        "valuation_timezone": B3_UTC_OFFSET,
    }
    campos.update(overrides)
    return RankIncomeOpportunitiesService(**campos)  # type: ignore[arg-type]  # justificativa: kwargs de teste


def _rodar(chain: OptionChain, **command: object) -> IncomeRanking:
    return _service(_FakeChains({"PETR4": chain})).execute(
        RankIncomeCommand(("PETR4",), **command)  # type: ignore[arg-type]  # justificativa: idem
    )


def _motivos(resultado: IncomeRanking) -> dict[str, str]:
    return {e.symbol: e.reason for e in resultado.exclusions}


# ---------------------------------------------------------------------------
# Positivos
# ---------------------------------------------------------------------------


def test_cumpre_o_protocol_do_use_case() -> None:
    assert isinstance(_service(_FakeChains({})), RankIncomeOpportunitiesUseCase)


def test_cadeia_completa_so_tem_executavel_no_ranking_ordenado_pelo_criterio() -> None:
    resultado = _rodar(_chain(_cadeia_completa()))
    assert resultado.ranked
    assert all(c.quality is PriceQuality.EXECUTAVEL for c in resultado.ranked)
    assert resultado.references == ()
    valores = [c.metrics.net_yield_annual_252 for c in resultado.ranked]
    assert valores == sorted(valores, reverse=True)  # type: ignore[type-var]
    assert {c.structure for c in resultado.ranked} == set(IncomeStructure)


def test_perna_vendida_sempre_na_faixa_de_delta() -> None:
    resultado = _rodar(_chain(_cadeia_completa()), delta_min=0.20, delta_max=0.30)
    for candidato in resultado.ranked:
        assert 0.20 <= abs(candidato.legs[0].delta) <= 0.30
    assert all("delta" not in e.reason for e in resultado.exclusions)  # filtro não polui


def test_put_coberta_rende_premio_sobre_strike_pelo_bid() -> None:
    resultado = _rodar(
        _chain(_cadeia_completa()), structures=frozenset({IncomeStructure.CASH_SECURED_PUT})
    )
    for candidato in resultado.ranked:
        (perna,) = candidato.legs
        quote_bid = perna.premium.premium
        assert_close(
            candidato.metrics.yield_period,
            quote_bid / perna.strike,
            rel=REL_SELF,
            abs_=ABS_SELF_FLOOR,
            label="prêmio / strike",
        )


def test_anualizacao_com_du_do_calendario_atravessando_feriado() -> None:
    """De 23/10 a 19/11/2026: 2/11 (Finados) não é dia útil — 18 du, não 19."""
    resultado = _rodar(
        _chain(_cadeia_completa()), structures=frozenset({IncomeStructure.CASH_SECURED_PUT})
    )
    candidato = resultado.ranked[0]
    assert candidato.metrics.business_days == 18
    esperado = (1.0 + candidato.metrics.yield_period) ** (252 / 18) - 1.0
    assert_close(candidato.metrics.yield_annual_252, esperado, rel=1e-12, abs_=1e-15, label="anual")  # type: ignore[arg-type]


def test_trava_de_credito_nas_duas_direcoes() -> None:
    resultado = _rodar(
        _chain(_cadeia_completa()), structures=frozenset({IncomeStructure.CREDIT_SPREAD})
    )
    tipos = {
        (c.legs[0].option_type, c.legs[1].strike - c.legs[0].strike > 0) for c in resultado.ranked
    }
    assert (OptionType.PUT, False) in tipos  # bull put: comprada abaixo
    assert (OptionType.CALL, True) in tipos  # bear call: comprada acima


def test_largura_da_trava_em_passos_de_strike() -> None:
    resultado = _rodar(
        _chain(_cadeia_completa()),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        spread_width_steps=2,
    )
    for candidato in resultado.ranked:
        assert abs(candidato.legs[1].strike - candidato.legs[0].strike) == 2.0


def test_resultado_e_deterministico() -> None:
    chain = _chain(_cadeia_completa())
    assert _rodar(chain) == _rodar(chain)


def test_resumo_do_ativo_com_pregao_spot_e_custos() -> None:
    (resumo,) = _rodar(_chain(_cadeia_completa(), book_available=False)).underlyings
    assert (resumo.symbol, resumo.session, resumo.spot, resumo.book_available) == (
        "PETR4",
        PREGAO,
        30.0,
        False,
    )
    assert resumo.cost_schedule.valid_from == date(2025, 8, 1)
    assert resumo.cdi == CDI


def test_data_de_valoracao_vem_do_pregao_no_fuso_da_b3() -> None:
    """02h UTC de 24/10 ainda é 23/10 em São Paulo: o pregão não muda."""
    tarde = datetime(2026, 10, 24, 2, 0, tzinfo=UTC)
    (resumo,) = _rodar(_chain(_cadeia_completa(), timestamp=tarde)).underlyings
    assert resumo.session == PREGAO


def test_call_americana_sai_com_marca_de_aproximacao() -> None:
    americana = _quote("PETRK320", 32.0, OptionType.CALL, style=ExerciseStyle.AMERICAN)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRK320=americana)),
        structures=frozenset({IncomeStructure.COVERED_CALL}),
        delta_min=0.0,
        delta_max=1.0,
    )
    marcada = next(c for c in resultado.ranked if c.legs[0].symbol == "PETRK320")
    assert marcada.approximations == (PricingApproximation.AMERICAN_CALL_AS_EUROPEAN,)


@pytest.mark.parametrize("criterio", list(RankingCriterion))
def test_qualquer_criterio_ordena_do_maior_para_o_menor(criterio: RankingCriterion) -> None:
    resultado = _rodar(_chain(_cadeia_completa()), sort_by=criterio)
    valores = [criterio.value_of(c.metrics) for c in resultado.ranked]
    assert valores == sorted(valores, reverse=True)  # type: ignore[type-var]


# ---------------------------------------------------------------------------
# Negativos
# ---------------------------------------------------------------------------


def test_ativo_desconhecido_e_indisponivel_viram_exclusao_e_o_resto_segue() -> None:
    fake = _FakeChains(
        {"PETR4": _chain(_cadeia_completa())}, unavailable={"BBAS3": "sem fechamento"}
    )
    resultado = _service(fake).execute(RankIncomeCommand(("XXXX99", "BBAS3", "PETR4")))
    motivos = _motivos(resultado)
    assert motivos["XXXX99"].startswith("ativo desconhecido")
    assert motivos["BBAS3"] == "sem fechamento"
    assert {e.scope for e in resultado.exclusions if e.symbol in ("XXXX99", "BBAS3")} == {
        ExclusionScope.UNDERLYING
    }
    assert resultado.ranked


def test_series_rejeitadas_pelo_adapter_aparecem_com_motivo() -> None:
    resultado = _rodar(
        _chain(_cadeia_completa(), rejected=(RejectedSeries("PETRK360", "sem estilo"),))
    )
    assert _motivos(resultado)["PETRK360"] == "sem estilo"


def test_put_americana_fica_fora() -> None:
    americana = _quote("PETRW290", 29.0, OptionType.PUT, style=ExerciseStyle.AMERICAN)
    resultado = _rodar(_chain(_cadeia_completa(PETRW290=americana)))
    assert _motivos(resultado)["PETRW290"] == "put americana não suportada (ADR-0002)"
    assert all(leg.symbol != "PETRW290" for c in resultado.ranked for leg in c.legs)


def test_sem_tabela_de_custos_vigente_e_erro() -> None:
    service = _service(
        _FakeChains({"PETR4": _chain(_cadeia_completa())}),
        cost_schedules=(make_cost_schedule(valid_from=date(2027, 1, 4)),),
    )
    with pytest.raises(InvalidDomainValueError, match="nenhuma tabela de custos vigente"):
        service.execute(RankIncomeCommand(("PETR4",)))


def test_painel_exige_dias_uteis() -> None:
    with pytest.raises(InvalidDomainValueError, match="BUSINESS_252"):
        _service(_FakeChains({}), day_count=DayCountConvention.CALENDAR_365)


# ---------------------------------------------------------------------------
# Borda
# ---------------------------------------------------------------------------


def test_vencimento_hoje_sem_anualizacao_vai_por_ultimo() -> None:
    hoje = _quote("PETRW300H", 30.5, OptionType.PUT, expiry=PREGAO, bid=0.52, ask=0.54)
    resultado = _rodar(
        _chain((*_cadeia_completa(), hoje)),
        structures=frozenset({IncomeStructure.CASH_SECURED_PUT}),
        delta_min=0.0,
        delta_max=1.0,
    )
    do_dia = [c for c in resultado.ranked if c.expiry == PREGAO]
    assert do_dia and all(c.metrics.business_days == 0 for c in do_dia)
    assert all(c.metrics.net_yield_annual_252 is None for c in do_dia)
    assert resultado.ranked[-len(do_dia) :] == tuple(do_dia)


def test_so_bid_na_perna_comprada_fica_fora_do_ranking() -> None:
    """A perna comprada agride o ask: sem ask, a estrutura não tem preço (ADR-0004)."""
    so_bid = _quote("PETRW280", 28.0, OptionType.PUT, ask=None)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW280=so_bid)),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        delta_min=0.0,
        delta_max=1.0,
    )
    assert all(c.legs[1].symbol != "PETRW280" for c in resultado.ranked)
    assert "PETRW280 sem ask para buy" in _motivos(resultado)["PETRW290/PETRW280"]


def test_credito_maior_ou_igual_a_largura_e_excluido_com_motivo() -> None:
    vendida = _quote("PETRW300", 30.0, OptionType.PUT, bid=1.50, ask=1.52)
    comprada = _quote("PETRW290", 29.0, OptionType.PUT, bid=0.38, ask=0.40)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW300=vendida, PETRW290=comprada)),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        delta_min=0.0,
        delta_max=1.0,
    )
    assert "dado inconsistente" in _motivos(resultado)["PETRW300/PETRW290"]
    assert "crédito" in _motivos(resultado)["PETRW300/PETRW290"]


def test_iv_sem_convergencia_e_fora_do_smile_nao_inventa_numero() -> None:
    """Mid abaixo do intrínseco (IV sem solução) e strike fora do smile: série sem delta."""
    abaixo = _quote("PETRW360", 36.0, OptionType.PUT, bid=0.50, ask=0.60)
    resultado = _rodar(_chain((*_cadeia_completa(), abaixo)))
    assert _motivos(resultado)["PETRW360"].startswith("sem delta")
    assert all(leg.symbol != "PETRW360" for c in resultado.ranked for leg in c.legs)


def test_serie_elegivel_ao_teorico_entra_so_nas_referencias() -> None:
    teorica = _quote("PETRW280", 28.0, OptionType.PUT, bid=None, ask=None, last=None, trades=0)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW280=teorica)),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        delta_min=0.0,
        delta_max=1.0,
    )
    referencia = next(c for c in resultado.references if c.legs[1].symbol == "PETRW280")
    assert referencia.quality is PriceQuality.TEORICO
    assert referencia.legs[1].premium.quality is PriceQuality.TEORICO
    assert all(c.quality is PriceQuality.EXECUTAVEL for c in resultado.ranked)


def test_book_vazio_com_negocio_e_indicativo() -> None:
    indicativa = _quote("PETRW290", 29.0, OptionType.PUT, bid=None, ask=None, last=0.31, trades=5)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW290=indicativa)),
        structures=frozenset({IncomeStructure.CASH_SECURED_PUT}),
        delta_min=0.0,
        delta_max=1.0,
    )
    referencia = next(c for c in resultado.references if c.legs[0].symbol == "PETRW290")
    assert referencia.quality is PriceQuality.INDICATIVO
    assert referencia.legs[0].premium.premium == 0.31


def test_sem_strike_para_a_perna_comprada() -> None:
    resultado = _rodar(
        _chain(_cadeia_completa()),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        delta_min=0.0,
        delta_max=1.0,
    )
    assert "sem strike 1 passo" in _motivos(resultado)["PETRW260/?"]


def test_strike_da_perna_comprada_com_serie_excluida_aponta_a_serie() -> None:
    americana = _quote("PETRW280", 28.0, OptionType.PUT, style=ExerciseStyle.AMERICAN)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW280=americana)),
        structures=frozenset({IncomeStructure.CREDIT_SPREAD}),
        delta_min=0.0,
        delta_max=1.0,
    )
    assert "strike 28 sem série analisada" in _motivos(resultado)["PETRW290/?"]


# ---------------------------------------------------------------------------
# Filtros de liquidez
# ---------------------------------------------------------------------------


def test_minimo_de_negocios_exclui_com_motivo() -> None:
    pouco = _quote("PETRW290", 29.0, OptionType.PUT, trades=2)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW290=pouco)),
        structures=frozenset({IncomeStructure.CASH_SECURED_PUT}),
        min_trades=10,
    )
    assert "PETRW290 com 2 negócios (mínimo 10)" in _motivos(resultado)["PETRW290"]


def test_spread_maximo_exclui_spread_largo_e_book_incompleto() -> None:
    largo = _quote("PETRW290", 29.0, OptionType.PUT, bid=0.20, ask=0.40)
    so_bid = _quote("PETRW280", 28.0, OptionType.PUT, ask=None)
    resultado = _rodar(
        _chain(_cadeia_completa(PETRW290=largo, PETRW280=so_bid)),
        structures=frozenset({IncomeStructure.CASH_SECURED_PUT}),
        delta_min=0.0,
        delta_max=1.0,
        max_spread_pct=0.10,
    )
    motivos = _motivos(resultado)
    assert "filtro de spread: PETRW290 com spread 0.6667" in motivos["PETRW290"]
    assert "sem book completo" in motivos["PETRW280"]
    for candidato in resultado.ranked:
        assert candidato.legs[0].spread_pct is not None
        assert candidato.legs[0].spread_pct <= 0.10


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "campos",
    [
        {"underlyings": ()},
        {"underlyings": ("PETR4", "PETR4")},
        {"underlyings": ("",)},
        {"structures": frozenset()},
        {"delta_min": 0.4, "delta_max": 0.3},
        {"delta_max": 1.5},
        {"expiries": 0},
        {"reference_shares": 0},
        {"spread_width_steps": 0},
        {"min_trades": -1},
        {"max_spread_pct": 0.0},
        {"max_spread_pct": math.nan},
    ],
)
def test_command_invalido(campos: dict[str, object]) -> None:
    base: dict[str, object] = {"underlyings": ("PETR4",), **campos}
    with pytest.raises(InvalidDomainValueError):
        RankIncomeCommand(**base)  # type: ignore[arg-type]  # justificativa: kwargs de teste


def test_defaults_da_mesa() -> None:
    command = RankIncomeCommand(("PETR4",))
    assert (command.delta_min, command.delta_max, command.expiries) == (0.15, 0.35, 2)
    assert (command.min_trades, command.max_spread_pct) == (None, None)
    assert command.sort_by is RankingCriterion.NET_ANNUAL_YIELD
    assert (command.reference_shares, command.spread_width_steps) == (100, 1)
    assert command.structures == frozenset(IncomeStructure)


def test_n_proximos_vencimentos() -> None:
    dezembro = date(2026, 12, 18)
    extra = tuple(
        _quote(f"PETRX{int(k * 10)}", k, OptionType.PUT, expiry=dezembro) for k in (28.0, 29.0)
    )
    um = _rodar(_chain((*_cadeia_completa(), *extra)), expiries=1)
    dois = _rodar(_chain((*_cadeia_completa(), *extra)), expiries=2)
    assert {c.expiry for c in um.ranked} == {NOVEMBRO}
    assert dezembro in {c.expiry for c in dois.ranked}


# ---------------------------------------------------------------------------
# Regras do modelo e teórico impossível
# ---------------------------------------------------------------------------


class _ModeloSemCalls(BlackScholesPricingModel):
    """Modelo de teste que não suporta call nenhuma."""

    def supports(self, terms: OptionTerms) -> bool:
        return terms.option_type is OptionType.PUT and super().supports(terms)


def test_termos_que_o_modelo_nao_suporta_ficam_fora_com_motivo() -> None:
    resultado = _service(
        _FakeChains({"PETR4": _chain(_cadeia_completa())}), model=_ModeloSemCalls()
    ).execute(RankIncomeCommand(("PETR4",)))
    assert "não suportados pelo modelo" in _motivos(resultado)["PETRK300"]
    assert all(c.legs[0].option_type is OptionType.PUT for c in resultado.ranked)


def test_call_americana_com_taxa_negativa_e_rejeitada_pelo_modelo() -> None:
    """ADR-0002, nota 1: o service herda a regra r >= 0 do PricingModel."""
    americana = _quote("PETRK320", 32.0, OptionType.CALL, style=ExerciseStyle.AMERICAN)
    chain = _chain(_cadeia_completa(PETRK320=americana))
    negativa = replace(
        chain,
        underlying=replace(chain.underlying, risk_free_rate=RiskFreeRate(-0.02, CDI.compounding)),
    )
    resultado = _rodar(negativa)
    assert "r >= 0" in _motivos(resultado)["PETRK320"]


def test_teorico_vencendo_hoje_nao_existe() -> None:
    """Com tau = 0 não há smile: série elegível ao teórico fica sem preço, com motivo."""
    sem_book = _quote(
        "PETRW305H", 30.5, OptionType.PUT, expiry=PREGAO, bid=None, ask=None, last=None, trades=0
    )
    resultado = _rodar(
        _chain((*_cadeia_completa(), sem_book)),
        structures=frozenset({IncomeStructure.CASH_SECURED_PUT}),
        delta_min=0.0,
        delta_max=1.0,
    )
    assert "elegível ao teórico, mas fora do smile" in _motivos(resultado)["PETRW305H"]

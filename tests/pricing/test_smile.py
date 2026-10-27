"""Smile por vencimento, preço TEÓRICO e risco por série (plano da fase 2 §3.1)."""

import math
from datetime import UTC, date, datetime

import pytest

from options_engine.domain.kernel.black_scholes import bs_outputs, bs_price
from options_engine.domain.kernel.distributions import norm_cdf
from options_engine.domain.model.chain import OptionQuote, PriceQuality
from options_engine.domain.model.enums import OptionType
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.pricing.smile import (
    SeriesMarket,
    SmilePoint,
    VolSmile,
    build_smile,
    mid_implied_vol,
    series_risk,
    theoretical_premium,
)
from tests._tolerances import ABS_SELF_FLOOR, REL_SELF, assert_close
from tests.domain._builders import make_contract, make_terms

VENCIMENTO = date(2026, 11, 19)
MERCADO = SeriesMarket(spot=30.0, rate_continuous=math.log(1.15), tau=18 / 252)
# Tolerância da vol recuperada de um mid com 2 casas: o arredondamento ao
# centavo do book (±0,005) dividido pelo vega de séries perto do dinheiro.
_ABS_VOL_DO_MID = 1e-3


def _quote(
    symbol: str,
    strike: float,
    option_type: OptionType,
    *,
    sigma: float | None = 0.30,
    bid: float | None = None,
    ask: float | None = None,
    last: float | None = None,
    trades: int = 10,
    expiry: date = VENCIMENTO,
) -> OptionQuote:
    """Book centrado no preço BS em ``sigma`` (meia-largura de 1 centavo), salvo override."""
    if sigma is not None and bid is None and ask is None:
        preco = bs_price(
            MERCADO.spot,
            strike,
            MERCADO.tau,
            MERCADO.rate_continuous,
            sigma,
            is_call=option_type is OptionType.CALL,
        )
        bid, ask = preco - 0.01, preco + 0.01
    return OptionQuote(
        contract=make_contract(
            symbol=symbol,
            terms=make_terms(strike=strike, option_type=option_type, expiry=expiry),
        ),
        bid=bid,
        ask=ask,
        last=last,
        trades=trades,
        volume=100.0 * trades,
        timestamp=datetime(2026, 10, 23, 21, 0, tzinfo=UTC),
    )


# ---------------------------------------------------------------------------
# VolSmile
# ---------------------------------------------------------------------------


def _smile(*pontos: tuple[float, float]) -> VolSmile:
    return VolSmile(VENCIMENTO, tuple(SmilePoint(k, v, f"S{k}") for k, v in pontos))


def test_interpolacao_linear_entre_vizinhos() -> None:
    smile = _smile((28.0, 0.34), (30.0, 0.30), (32.0, 0.32))
    meio, tres_quartos = smile.vol_at(29.0), smile.vol_at(31.5)
    assert meio is not None and tres_quartos is not None
    assert_close(meio, 0.32, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="meio")
    assert_close(tres_quartos, 0.315, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="3/4")
    assert smile.vol_at(30.0) == 0.30  # ponto exato, sem aritmética


@pytest.mark.parametrize("strike", [27.99, 32.01])
def test_sem_extrapolacao(strike: float) -> None:
    assert _smile((28.0, 0.34), (32.0, 0.32)).vol_at(strike) is None


def test_smile_vazio_nao_interpola() -> None:
    assert VolSmile(VENCIMENTO, ()).vol_at(30.0) is None


@pytest.mark.parametrize(
    "pontos", [((30.0, 0.3), (30.0, 0.31)), ((31.0, 0.3), (30.0, 0.31)), ((30.0, 0.0),)]
)
def test_smile_invalido(pontos: tuple[tuple[float, float], ...]) -> None:
    with pytest.raises(InvalidDomainValueError):
        _smile(*pontos)


# ---------------------------------------------------------------------------
# Vol implícita pelo mid e montagem do smile
# ---------------------------------------------------------------------------


def test_mid_recupera_a_vol_do_book() -> None:
    sigma = mid_implied_vol(_quote("PETRK300", 30.0, OptionType.CALL, sigma=0.30), MERCADO)
    assert sigma is not None
    assert_close(sigma, 0.30, rel=0.0, abs_=_ABS_VOL_DO_MID, label="vol do mid")


@pytest.mark.parametrize(
    ("bid", "ask"), [(0.80, None), (None, 0.90), (None, None)], ids=["so_bid", "so_ask", "vazio"]
)
def test_sem_book_completo_nao_ha_vol(bid: float | None, ask: float | None) -> None:
    quote = _quote("PETRK300", 30.0, OptionType.CALL, sigma=None, bid=bid, ask=ask)
    assert mid_implied_vol(quote, MERCADO) is None


def test_vencendo_hoje_nao_ha_vol() -> None:
    hoje = SeriesMarket(spot=30.0, rate_continuous=0.1, tau=0.0)
    assert mid_implied_vol(_quote("PETRK300", 30.0, OptionType.CALL), hoje) is None


def test_mid_abaixo_do_intrinseco_nao_vira_ponto() -> None:
    quote = _quote("PETRK250", 25.0, OptionType.CALL, sigma=None, bid=0.50, ask=0.60)
    assert mid_implied_vol(quote, MERCADO) is None


def test_mid_no_intrinseco_da_sigma_zero_e_fica_fora_do_smile() -> None:
    """IV 0 (regra 5 do implied_vol) não informa a vol: não vira ponto."""
    intrinseco = 30.0 - 25.0 * math.exp(-MERCADO.rate_continuous * MERCADO.tau)
    quote = _quote("PETRK250", 25.0, OptionType.CALL, sigma=None, bid=intrinseco, ask=intrinseco)
    assert mid_implied_vol(quote, MERCADO) is None


def test_smile_usa_a_serie_fora_do_dinheiro_em_cada_strike() -> None:
    quotes = [
        _quote("PETRW280", 28.0, OptionType.PUT, sigma=0.36),
        _quote("PETRK280", 28.0, OptionType.CALL, sigma=0.50),  # ITM: perde para a put
        _quote("PETRK310", 31.0, OptionType.CALL, sigma=0.31),
        _quote("PETRW310", 31.0, OptionType.PUT, sigma=0.50),  # ITM: perde para a call
        _quote("PETRK300", 30.0, OptionType.CALL, sigma=0.30),  # K >= spot: call
        _quote("PETRW300", 30.0, OptionType.PUT, sigma=0.45),
    ]
    smile = build_smile(VENCIMENTO, quotes, MERCADO)
    assert [p.symbol for p in smile.points] == ["PETRW280", "PETRK300", "PETRK310"]
    for ponto, esperada in zip(smile.points, (0.36, 0.30, 0.31), strict=True):
        assert_close(ponto.implied_vol, esperada, rel=0.0, abs_=_ABS_VOL_DO_MID, label=ponto.symbol)


def test_smile_aceita_um_tipo_so_e_ignora_outro_vencimento() -> None:
    quotes = [
        _quote("PETRK280", 28.0, OptionType.CALL, sigma=0.35),
        _quote("PETRL300", 30.0, OptionType.CALL, sigma=0.30, expiry=date(2026, 12, 18)),
    ]
    smile = build_smile(VENCIMENTO, quotes, MERCADO)
    assert [p.symbol for p in smile.points] == ["PETRK280"]


def test_series_sem_vol_nao_entram_no_smile() -> None:
    quotes = [_quote("PETRK320", 32.0, OptionType.CALL, sigma=None, bid=0.4, ask=None)]
    assert build_smile(VENCIMENTO, quotes, MERCADO).points == ()


# ---------------------------------------------------------------------------
# Preço TEÓRICO
# ---------------------------------------------------------------------------


def test_teorico_pela_vol_interpolada() -> None:
    smile = _smile((26.0, 0.40), (30.0, 0.30))
    elegivel = _quote("PETRW270", 27.0, OptionType.PUT, sigma=None, trades=0)
    premio = theoretical_premium(elegivel, smile, MERCADO)
    assert premio is not None
    assert premio.quality is PriceQuality.TEORICO
    esperado = bs_price(30.0, 27.0, MERCADO.tau, MERCADO.rate_continuous, 0.375, is_call=False)
    assert_close(premio.premium, esperado, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="teórico")


def test_teorico_fora_do_smile_nao_existe() -> None:
    elegivel = _quote("PETRW250", 25.0, OptionType.PUT, sigma=None, trades=0)
    assert theoretical_premium(elegivel, _smile((26.0, 0.40), (30.0, 0.30)), MERCADO) is None


@pytest.mark.parametrize(
    "overrides",
    [{"last": 0.62, "trades": 3}, {"bid": 0.50}, {"trades": 2}],
    ids=["com_negocio", "com_bid", "trades_sem_last"],
)
def test_teorico_so_para_serie_elegivel(overrides: dict[str, object]) -> None:
    campos: dict[str, object] = {"sigma": None, "trades": 0, **overrides}
    quote = _quote("PETRW270", 27.0, OptionType.PUT, **campos)  # type: ignore[arg-type]
    assert not quote.is_theoretical_eligible
    assert theoretical_premium(quote, _smile((26.0, 0.40), (30.0, 0.30)), MERCADO) is None


# ---------------------------------------------------------------------------
# Delta e N(d2)
# ---------------------------------------------------------------------------


def test_risco_com_a_vol_da_propria_serie() -> None:
    quote = _quote("PETRK310", 31.0, OptionType.CALL, sigma=0.31)
    risco = series_risk(quote, _smile((30.0, 0.50), (32.0, 0.50)), MERCADO)
    assert risco is not None and risco.implied_vol is not None
    assert risco.vol == risco.implied_vol
    saidas = bs_outputs(30.0, 31.0, MERCADO.tau, MERCADO.rate_continuous, risco.vol, is_call=True)
    assert risco.delta == saidas.delta
    assert 0.0 < risco.exercise_probability < risco.delta  # N(d2) < N(d1) na call


def test_risco_cai_para_o_smile_sem_vol_da_serie() -> None:
    quote = _quote("PETRW270", 27.0, OptionType.PUT, sigma=None, trades=0)
    risco = series_risk(quote, _smile((26.0, 0.40), (30.0, 0.30)), MERCADO)
    assert risco is not None
    assert risco.implied_vol is None
    assert risco.vol is not None
    assert_close(risco.vol, 0.375, rel=REL_SELF, abs_=ABS_SELF_FLOOR, label="vol do smile")
    assert -1.0 < risco.delta < 0.0
    sqrt_tau = math.sqrt(MERCADO.tau)
    d2 = (math.log(30.0 / 27.0) + (MERCADO.rate_continuous - 0.5 * 0.375**2) * MERCADO.tau) / (
        0.375 * sqrt_tau
    )
    assert_close(risco.exercise_probability, norm_cdf(-d2), rel=1e-12, abs_=1e-15, label="N(-d2)")


def test_sem_vol_da_serie_nem_do_smile_nao_ha_risco() -> None:
    quote = _quote("PETRW250", 25.0, OptionType.PUT, sigma=None, trades=0)
    assert series_risk(quote, VolSmile(VENCIMENTO, ()), MERCADO) is None


@pytest.mark.parametrize(
    ("strike", "option_type", "delta", "probabilidade"),
    [
        (28.0, OptionType.CALL, 1.0, 1.0),
        (32.0, OptionType.CALL, 0.0, 0.0),
        (30.0, OptionType.CALL, 0.5, 0.5),
        (32.0, OptionType.PUT, -1.0, 1.0),
    ],
)
def test_vencendo_hoje_e_degrau_sem_vol(
    strike: float, option_type: OptionType, delta: float, probabilidade: float
) -> None:
    hoje = SeriesMarket(spot=30.0, rate_continuous=0.1, tau=0.0)
    quote = _quote("X", strike, option_type, sigma=None, bid=1.0, ask=1.1)
    risco = series_risk(quote, VolSmile(VENCIMENTO, ()), hoje)
    assert risco is not None
    assert (risco.delta, risco.exercise_probability, risco.vol) == (delta, probabilidade, None)


@pytest.mark.parametrize(
    "campos", [{"spot": 0.0}, {"rate_continuous": math.nan}, {"tau": -1.0}, {"tau": math.inf}]
)
def test_mercado_invalido(campos: dict[str, float]) -> None:
    base = {"spot": 30.0, "rate_continuous": 0.1, "tau": 0.1, **campos}
    with pytest.raises(InvalidDomainValueError):
        SeriesMarket(**base)

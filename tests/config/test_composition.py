"""Composition root — wiring correto e integração leve com o mock real."""

from datetime import UTC, date, datetime, timedelta

from options_engine.adapters.outbound.clock import FixedClock
from options_engine.application.ports.inbound import (
    AnalyzeStrategyPayoffUseCase,
    PriceOptionCommand,
    PriceOptionUseCase,
    StressTestUseCase,
)
from options_engine.config.composition import DEFAULT_UNDERLYING, Application, build_application
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import OptionType
from tests.domain._builders import VENCIMENTO_PADRAO

INSTANTE = datetime(2026, 7, 3, 14, 0, tzinfo=UTC)


def _app(seed: int = 42) -> Application:
    return build_application(seed=seed, clock=FixedClock(INSTANTE))


def _terms() -> OptionTerms:
    return OptionTerms(
        underlying=DEFAULT_UNDERLYING,
        strike=30.0,
        expiry=VENCIMENTO_PADRAO,
        option_type=OptionType.CALL,
    )


def test_aplicacao_expoe_os_contratos_inbound() -> None:
    app = _app()
    assert isinstance(app.price_option, PriceOptionUseCase)
    assert isinstance(app.analyze_payoff, AnalyzeStrategyPayoffUseCase)
    assert isinstance(app.stress_test, StressTestUseCase)


def test_clock_default_e_o_relogio_de_producao() -> None:
    """Sem clock injetado, build_application usa SystemClock — o caminho
    real de produção, que o smoke (sempre com FixedClock) nunca exercita.

    Vencimento calculado a partir de ``date.today()`` (não o fixo dos
    builders): com SystemClock real, um vencimento fixo no passado quebraria
    este teste em qualquer execução após aquela data."""
    app = build_application(seed=42)
    termos = OptionTerms(
        underlying=DEFAULT_UNDERLYING,
        strike=30.0,
        expiry=date.today() + timedelta(days=180),
        option_type=OptionType.CALL,
    )
    result = app.price_option.execute(PriceOptionCommand(terms=termos))
    assert result.price > 0.0
    assert result.time_to_expiry.year_fraction > 0.0


def test_integracao_leve_precifica_via_mock_real() -> None:
    """Fio inteiro: command → snapshot GBM → calendário empacotado → kernel."""
    result = _app().price_option.execute(PriceOptionCommand(terms=_terms()))
    assert result.model_id == "black-scholes-v1"
    assert result.price > 0.0
    assert result.snapshot.underlying_symbol == DEFAULT_UNDERLYING
    # Valoração 2026-07-03 (sex) → vencimento 2026-12-18: tau > 0 em base 252.
    assert result.time_to_expiry.year_fraction > 0.0


def test_mesma_seed_e_mesmo_relogio_reproduzem_o_preco_bit_a_bit() -> None:
    """A promessa do smoke (ROADMAP S3): saída reprodutível dada a seed."""
    comando = PriceOptionCommand(terms=_terms())
    primeiro = _app(seed=42).price_option.execute(comando)
    segundo = _app(seed=42).price_option.execute(comando)
    assert primeiro == segundo


def test_seeds_distintas_produzem_snapshots_distintos() -> None:
    comando = PriceOptionCommand(terms=_terms())
    assert (
        _app(seed=42).price_option.execute(comando).snapshot.spot
        != _app(seed=43).price_option.execute(comando).snapshot.spot
    )

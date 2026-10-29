"""CLI: smoke do hexágono e o subcomando ``painel`` (ROADMAP S3 e S5).

``python -m options_engine [seed]`` (inalterado): precifica uma call e um
iron condor de crédito via mock GBM, imprime payoff e estresse nomeado.
Saída 100% reprodutível dada a seed: relógio CONGELADO em 2026-07-03
(pregão de sexta) e toda aleatoriedade vem da ``SeededRandomSource``.

``python -m options_engine painel --pregao AAAA-MM-DD --cotahist ARQ [ARQ ...]
--cadastro CSV --ativos PETR4,VALE3 --saida painel.html [...]``: gera o
Painel de Renda (ADR-0007) a partir dos arquivos baixados da B3. Erro de
arquivo (ausente, fora do layout) ou de domínio vira mensagem clara no
stderr e código de saída != 0, sem traceback.

``python -m options_engine app [--porta 8765] [--sem-janela] [--sem-ponte]``:
sobe o app local (Painel de Opções) em ``127.0.0.1`` e o abre numa janela de
app. Precisa do extra ``app`` e do frontend compilado; sem eles, mensagem e
código 2. O FastAPI só é importado aqui dentro: o resto do CLI roda sem ele.

Adapter inbound de console: consome os Protocols inbound montados pelo
composition root; mora fora das camadas porque é quem chama o ``config``.
"""

import argparse
import os
import platform
import shutil
import sys
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from options_engine.adapters.inbound.html_report import render_income_report
from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.adapters.outbound.clock import FixedClock
from options_engine.adapters.outbound.cotahist import SourceFileError
from options_engine.application.ports.inbound import PriceOptionCommand, RankIncomeCommand
from options_engine.config.composition import (
    DEFAULT_CDI_ANNUAL,
    DEFAULT_UNDERLYING,
    build_application,
    build_income_panel,
)
from options_engine.domain.income.ranking import RankingCriterion
from options_engine.domain.model.contracts import OptionTerms
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import DomainError
from options_engine.domain.model.factories import iron_condor
from options_engine.domain.model.scenarios import SpotAxis, StressScenario
from options_engine.domain.model.strategy import StrategyLeg

DEFAULT_SEED = 42
VALUATION_INSTANT = datetime(2026, 7, 3, 14, 0, tzinfo=B3_UTC_OFFSET)
EXPIRY = date(2026, 12, 18)

# Condor de crédito canônico da suíte de domínio: crédito líquido 1.00 por
# unidade ((0.80 + 0.85) - (0.30 + 0.35)) → breakevens em forma fechada
# K2 - 1 = 27 e K3 + 1 = 33.
CONDOR_STRIKES = (26.0, 28.0, 32.0, 34.0)
CONDOR_PREMIUMS = (0.30, 0.80, 0.85, 0.35)
CONDOR_QUANTITY = 10

PAYOFF_AXIS = SpotAxis(spot_min=24.0, spot_max=36.0, steps=13)
SCENARIOS = (
    StressScenario(label="base"),
    StressScenario(label="crise: spot -20%, vol +10 pts", spot_shift=0.80, vol_shift=0.10),
    StressScenario(label="rally: spot +15%, vol -5 pts", spot_shift=1.15, vol_shift=-0.05),
    StressScenario(label="aperto: taxa +200 bps", rate_shift=0.02),
)


def _condor_legs() -> list[StrategyLeg]:
    tipos = (OptionType.PUT, OptionType.PUT, OptionType.CALL, OptionType.CALL)
    lados = (Side.BUY, Side.SELL, Side.SELL, Side.BUY)  # asas compradas, corpo vendido
    return [
        StrategyLeg(
            symbol=f"PETR{'C' if tipo is OptionType.CALL else 'P'}{round(strike * 100)}",
            terms=OptionTerms(
                underlying=DEFAULT_UNDERLYING,
                strike=strike,
                expiry=EXPIRY,
                option_type=tipo,
            ),
            side=lado,
            quantity=CONDOR_QUANTITY,
            premium=premium,
        )
        for strike, premium, tipo, lado in zip(
            CONDOR_STRIKES, CONDOR_PREMIUMS, tipos, lados, strict=True
        )
    ]


def main(argv: Sequence[str] | None = None) -> int:
    """Despacha ``painel`` ou roda o smoke; devolve o código de saída."""
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "painel":
        return painel(args[1:])
    if args and args[0] == "app":
        return app(args[1:])
    smoke(args)
    return 0


def smoke(args: Sequence[str]) -> None:
    seed = int(args[0]) if args else DEFAULT_SEED
    app = build_application(seed=seed, clock=FixedClock(VALUATION_INSTANT))

    print(f"options-engine smoke — seed={seed}, valoração={VALUATION_INSTANT.date()}")
    print()

    # 1. Uma call europeia seca via PriceOptionUseCase.
    terms = OptionTerms(
        underlying=DEFAULT_UNDERLYING, strike=30.0, expiry=EXPIRY, option_type=OptionType.CALL
    )
    result = app.price_option.execute(PriceOptionCommand(terms=terms))
    snapshot = result.snapshot
    print(f"[price] call {DEFAULT_UNDERLYING} K={terms.strike} exp={terms.expiry}")
    print(
        f"  snapshot: spot={snapshot.spot:.4f} bid={snapshot.bid:.4f} "
        f"ask={snapshot.ask:.4f} vol={snapshot.volatility.value:.2%}"
    )
    print(
        f"  tau={result.time_to_expiry.year_fraction:.6f} "
        f"({result.time_to_expiry.convention.name}) modelo={result.model_id}"
    )
    greeks = result.greeks
    print(f"  preço={result.price:.4f}")
    print(
        f"  gregas: delta={greeks.delta:.4f} gamma={greeks.gamma:.4f} "
        f"theta/ano={greeks.theta_per_year:.4f} vega={greeks.vega_per_vol_unit:.4f} "
        f"rho={greeks.rho:.4f}"
    )
    print()

    # 2. Iron condor de crédito: payoff no vencimento via SpotAxis.
    condor = iron_condor(_condor_legs())
    profile = app.analyze_payoff.execute(condor, PAYOFF_AXIS)
    print(f"[payoff] {condor.name} — strikes {CONDOR_STRIKES}, qty {CONDOR_QUANTITY}")
    assert profile.pnl is not None and profile.breakevens is not None  # prêmios informados
    print(f"  breakevens={tuple(f'{b:.2f}' for b in profile.breakevens)}")
    print(f"  max_gain={profile.max_gain:.2f} max_loss={profile.max_loss:.2f}")
    print("  spot    payoff bruto   P&L")
    for spot, bruto, pnl in zip(profile.spots, profile.payoff_at_expiry, profile.pnl, strict=True):
        print(f"  {spot:5.2f}  {bruto:12.2f}  {pnl:8.2f}")
    print()

    # 3. Estresse por cenários nomeados (mark-to-model com tau remanescente).
    report = app.stress_test.execute(condor, SCENARIOS)
    print(f"[stress] {report.strategy_name} — base={report.base_value:.4f}")
    for outcome in report.outcomes:
        variacao = report.change_from_base(outcome)
        # Saída ASCII-safe: o console default do Windows (cp1252) não tem Δ.
        print(f"  {outcome.scenario.label:<32} valor={outcome.value:9.4f}  var={variacao:+9.4f}")


# ---------------------------------------------------------------------------
# Painel de Renda
# ---------------------------------------------------------------------------


def _ativos(texto: str) -> tuple[str, ...]:
    ativos = tuple(a.strip().upper() for a in texto.split(",") if a.strip())
    if not ativos:
        raise argparse.ArgumentTypeError("informe ao menos um ativo, ex.: PETR4,VALE3")
    return ativos


def _parser_painel() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m options_engine painel",
        description=(
            "Painel de Renda com opções (HTML estático) a partir do COTAHIST e do Cadastro "
            "de Instrumentos baixados manualmente da B3."
        ),
    )
    p.add_argument("--pregao", required=True, type=date.fromisoformat, help="AAAA-MM-DD")
    p.add_argument("--cotahist", required=True, nargs="+", type=Path, metavar="ARQ")
    p.add_argument("--cadastro", required=True, type=Path, metavar="CSV")
    p.add_argument("--ativos", required=True, type=_ativos, help="ex.: PETR4,VALE3")
    p.add_argument("--saida", required=True, type=Path, metavar="HTML")
    p.add_argument(
        "--cdi",
        type=float,
        default=DEFAULT_CDI_ANNUAL,
        help=f"CDI efetivo anual em decimal (default {DEFAULT_CDI_ANNUAL})",
    )
    p.add_argument("--delta-min", type=float, help="módulo do delta da perna vendida (0.15)")
    p.add_argument("--delta-max", type=float, help="módulo do delta da perna vendida (0.35)")
    p.add_argument("--vencimentos", type=int, help="próximos vencimentos com du >= 0 (2)")
    p.add_argument("--min-negocios", type=int, help="mínimo de negócios por perna (sem filtro)")
    p.add_argument(
        "--spread-max",
        type=float,
        metavar="PCT",
        help="spread máximo por perna, em %% do mid: 10 = 10%% (sem filtro)",
    )
    p.add_argument(
        "--ordenar",
        choices=[c.value for c in RankingCriterion],
        help=f"critério do ranking ({RankingCriterion.NET_ANNUAL_YIELD.value})",
    )
    p.add_argument("--acoes", type=int, help="tamanho de referência por estrutura (100)")
    p.add_argument("--cache", type=Path, metavar="ARQ", help="cache sqlite por pregão")
    p.add_argument(
        "--gerado-em",
        type=date.fromisoformat,
        help="data de geração exibida no painel (omitida por padrão: saída reprodutível)",
    )
    return p


def _command(args: argparse.Namespace) -> RankIncomeCommand:
    """Só os parâmetros dados entram: os defaults são os do command (decisão da mesa)."""
    opcionais = {
        "delta_min": args.delta_min,
        "delta_max": args.delta_max,
        "expiries": args.vencimentos,
        "min_trades": args.min_negocios,
        "max_spread_pct": None if args.spread_max is None else args.spread_max / 100.0,
        "sort_by": None if args.ordenar is None else RankingCriterion(args.ordenar),
        "reference_shares": args.acoes,
    }
    dados = {nome: valor for nome, valor in opcionais.items() if valor is not None}
    return RankIncomeCommand(underlyings=args.ativos, **dados)


def _decimal_br(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _parametros(args: argparse.Namespace, command: RankIncomeCommand) -> dict[str, str]:
    """Os parâmetros como o painel os mostra — nomes de arquivo, não caminhos."""
    sem_filtro = "sem filtro"
    spread = command.max_spread_pct
    return {
        "Pregão": args.pregao.strftime("%d/%m/%Y"),
        "Arquivos COTAHIST": ", ".join(p.name for p in args.cotahist),
        "Cadastro de instrumentos": args.cadastro.name,
        "Ativos": ", ".join(command.underlyings),
        "CDI efetivo anual": f"{_decimal_br(args.cdi * 100)}%",
        "Faixa de delta (módulo)": (
            f"{_decimal_br(command.delta_min)} a {_decimal_br(command.delta_max)}"
        ),
        "Vencimentos": str(command.expiries),
        "Mínimo de negócios": sem_filtro if command.min_trades is None else str(command.min_trades),
        "Spread máximo": sem_filtro if spread is None else f"{_decimal_br(spread * 100)}%",
        "Ações por estrutura": str(command.reference_shares),
    }


def painel(argv: Sequence[str]) -> int:
    """Gera o painel; 0 em sucesso, 1 em erro de domínio, 2 em erro de arquivo."""
    args = _parser_painel().parse_args(list(argv))
    try:
        command = _command(args)
        use_case = build_income_panel(
            session_date=args.pregao,
            cotahist_paths=args.cotahist,
            instruments_path=args.cadastro,
            cdi_annual=args.cdi,
            cache_path=args.cache,
        )
        ranking = use_case.execute(command)
    except (SourceFileError, OSError) as erro:
        print(f"erro de arquivo: {erro}", file=sys.stderr)
        return 2
    except DomainError as erro:
        print(f"erro: {erro}", file=sys.stderr)
        return 1
    html = render_income_report(ranking, _parametros(args, command), generated_on=args.gerado_em)
    try:
        args.saida.write_text(html, encoding="utf-8", newline="\n")
    except OSError as erro:
        print(f"erro de arquivo: não foi possível gravar {args.saida}: {erro}", file=sys.stderr)
        return 2
    print(
        f"painel gravado em {args.saida}: {len(ranking.ranked)} no ranking, "
        f"{len(ranking.references)} referências, {len(ranking.exclusions)} exclusões"
    )
    return 0


def app(args: Sequence[str]) -> int:
    """Sobe o app local e abre a janela; volta quando o servidor para (Ctrl+C)."""
    from options_engine.adapters.inbound.web import launch

    parser = argparse.ArgumentParser(
        prog="python -m options_engine app",
        description="Painel de Opções: app local com cotações do Tryd e arquivos da B3.",
    )
    parser.add_argument("--porta", type=int, default=launch.DEFAULT_PORT)
    parser.add_argument("--sem-janela", action="store_true", help="não abre a janela de app")
    parser.add_argument("--sem-ponte", action="store_true", help="não sobe a ponte do Tryd")
    opcoes = parser.parse_args(args)

    static_dir = launch.default_static_dir()
    if not (static_dir / "index.html").is_file():
        print(
            "erro: o frontend não está compilado; rode `npm --prefix frontend run build`",
            file=sys.stderr,
        )
        return 2
    try:
        from options_engine.config.web_app import build_web_app
    except ImportError as erro:
        print(
            f'erro: o app precisa do extra "app" (pip install -e ".[app]"): {erro}',
            file=sys.stderr,
        )
        return 2

    sistema = platform.system()
    config_dir = launch.platform_config_dir(sistema, os.environ, Path.home())
    porta = launch.find_free_port(opcoes.porta)
    url = f"http://{launch.HOST}:{porta}/"
    web = build_web_app(
        config_dir=config_dir,
        static_dir=static_dir,
        bridge=not opcoes.sem_ponte,
        machine_name=platform.node() or "este PC",
    )
    janela = launch.app_window_command(
        sistema, url, shutil.which, launch.has_flatpak_app, launch.windows_edge_paths(os.environ)
    )
    print(f"Painel de Opções em {url} (configuração em {config_dir})")
    on_ready = None if opcoes.sem_janela else (lambda: launch.open_window(janela, url))
    launch.serve(web, porta, on_ready)
    return 0


if __name__ == "__main__":
    sys.exit(main())

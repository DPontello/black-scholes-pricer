"""``RankIncomeOpportunitiesService`` — ranking das oportunidades de renda do pregão (plano §3.3).

Para cada ativo pedido, na ordem do usuário:

1. Cadeia pelo ``OptionChainPort``; ativo desconhecido ou indisponível vira
   exclusão com motivo, e as séries que o adapter rejeitou também.
2. Data de valoração = data do pregão da cadeia (timestamp do snapshot no
   fuso de valoração), nunca o relógio; tabela de custos vigente nela.
3. Os N próximos vencimentos com du >= 0; por vencimento, o smile (mid das
   séries com book completo) e a análise de cada série: put americana fica
   fora (ADR-0002); sem vol da série nem do smile, a série fica sem delta e
   fora; o resto é precificado pelo ``PricingModel`` com a vol escolhida —
   ele aplica as regras de exercício (ADR-0002, r >= 0) e dá o delta.
4. Estruturas com a perna vendida dentro da faixa de delta (módulo): put
   coberta, venda coberta e travas de crédito (bull put e bear call, com a
   comprada ``spread_width_steps`` strikes mais fora do dinheiro). Prêmio
   por lado (``executable_premium``), TEÓRICO quando a série é elegível.
5. Filtros de liquidez (negócios, spread %) em todas as pernas; dado
   inconsistente nas métricas, perna sem preço ou sem strike para a perna
   comprada viram exclusão com motivo. Fora da faixa de delta é filtro, não
   exclusão: não polui a lista.
6. Ranking só com EXECUTAVEL; INDICATIVO e TEORICO vão para as referências.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, tzinfo

from options_engine.application.ports.inbound import RankIncomeCommand
from options_engine.application.ports.outbound import OptionChainPort, TradingCalendar
from options_engine.application.use_cases._time import resolve_time_to_expiry
from options_engine.domain.income.costs import CostSchedule, schedule_on
from options_engine.domain.income.metrics import (
    IncomeMetrics,
    IncomeStructure,
    cash_secured_put_metrics,
    covered_call_metrics,
    credit_spread_metrics,
)
from options_engine.domain.income.profile import IncomeProfile, PositionLeg, income_profile
from options_engine.domain.income.ranking import (
    CandidateLeg,
    Exclusion,
    ExclusionScope,
    IncomeCandidate,
    IncomeRanking,
    UnderlyingSummary,
    rank_candidates,
)
from options_engine.domain.model.chain import (
    LegPremium,
    OptionChain,
    OptionQuote,
    executable_premium,
)
from options_engine.domain.model.conventions import DayCountConvention, TimeToExpiry, Volatility
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.errors import (
    InvalidDomainValueError,
    InvalidStrategyError,
    UnderlyingUnavailableError,
    UnknownSymbolError,
    UnsupportedExerciseStyleError,
)
from options_engine.domain.model.factories import vertical_spread
from options_engine.domain.model.strategy import StrategyLeg
from options_engine.domain.pricing.model import PricingModel, PricingRequest
from options_engine.domain.pricing.smile import (
    SeriesMarket,
    VolSmile,
    build_smile,
    series_risk,
    theoretical_premium,
)

__all__ = ["RankIncomeOpportunitiesService"]


@dataclass(frozen=True, slots=True)
class _Serie:
    """Série analisada de um vencimento: cotação, delta, N(d2), vol e spread."""

    quote: OptionQuote
    delta: float
    exercise_probability: float
    implied_vol: float | None

    @property
    def symbol(self) -> str:
        return self.quote.contract.symbol

    @property
    def strike(self) -> float:
        return self.quote.contract.terms.strike

    @property
    def spread_pct(self) -> float | None:
        bid, ask = self.quote.bid, self.quote.ask
        if bid is None or ask is None:
            return None
        return (ask - bid) / ((ask + bid) / 2.0)


@dataclass(frozen=True, slots=True)
class _Vencimento:
    """O que as estruturas de um vencimento precisam: du, mercado, smile e as séries."""

    expiry: date
    business_days: int
    market: SeriesMarket
    smile: VolSmile
    calls: tuple[_Serie, ...]
    puts: tuple[_Serie, ...]
    call_strikes: tuple[float, ...]
    put_strikes: tuple[float, ...]


class RankIncomeOpportunitiesService:
    """Implementa ``RankIncomeOpportunitiesUseCase`` — wiring manual no composition root."""

    def __init__(
        self,
        *,
        chains: OptionChainPort,
        calendar: TradingCalendar,
        model: PricingModel,
        cost_schedules: Sequence[CostSchedule],
        valuation_timezone: tzinfo,
        day_count: DayCountConvention = DayCountConvention.BUSINESS_252,
    ) -> None:
        if day_count is not DayCountConvention.BUSINESS_252:
            raise InvalidDomainValueError(
                f"o painel anualiza em dias úteis (ADR-0005): exige BUSINESS_252; "
                f"recebido {day_count.name}"
            )
        self._chains = chains
        self._calendar = calendar
        self._model = model
        self._schedules = tuple(cost_schedules)
        self._timezone = valuation_timezone
        self._day_count = day_count

    def execute(self, command: RankIncomeCommand) -> IncomeRanking:
        candidatos: list[IncomeCandidate] = []
        exclusoes: list[Exclusion] = []
        resumos: list[UnderlyingSummary] = []
        for simbolo in command.underlyings:
            try:
                chain = self._chains.get_chain(simbolo)
            except UnknownSymbolError as erro:
                exclusoes.append(
                    Exclusion(ExclusionScope.UNDERLYING, simbolo, f"ativo desconhecido: {erro}")
                )
                continue
            except UnderlyingUnavailableError as erro:
                exclusoes.append(Exclusion(ExclusionScope.UNDERLYING, simbolo, str(erro)))
                continue
            resumo, do_ativo, fora = self._ativo(chain, command)
            resumos.append(resumo)
            candidatos.extend(do_ativo)
            exclusoes.extend(fora)
        ranking, referencias = rank_candidates(candidatos, command.sort_by)
        return IncomeRanking(
            criterion=command.sort_by,
            ranked=ranking,
            references=referencias,
            exclusions=tuple(exclusoes),
            underlyings=tuple(resumos),
        )

    # ------------------------------------------------------------------
    # Ativo e vencimentos
    # ------------------------------------------------------------------

    def _ativo(
        self, chain: OptionChain, command: RankIncomeCommand
    ) -> tuple[UnderlyingSummary, list[IncomeCandidate], list[Exclusion]]:
        snapshot = chain.underlying
        pregao = snapshot.timestamp.astimezone(self._timezone).date()
        tabela = schedule_on(self._schedules, pregao)
        resumo = UnderlyingSummary(
            symbol=snapshot.underlying_symbol,
            session=pregao,
            spot=snapshot.spot,
            realized_vol=snapshot.volatility.value,
            book_available=chain.underlying_book_available,
            cdi=snapshot.risk_free_rate,
            cost_schedule=tabela,
        )
        exclusoes = [
            Exclusion(ExclusionScope.SERIES, r.symbol, r.reason) for r in chain.rejected_series
        ]
        candidatos: list[IncomeCandidate] = []
        vencimentos = sorted(
            {q.contract.terms.expiry for q in chain.quotes if q.contract.terms.expiry >= pregao}
        )[: command.expiries]
        for vencimento in vencimentos:
            dados = self._vencimento(chain, pregao, vencimento, exclusoes)
            candidatos.extend(self._estruturas(chain, dados, resumo, tabela, command, exclusoes))
        return resumo, candidatos, exclusoes

    def _vencimento(
        self, chain: OptionChain, pregao: date, vencimento: date, exclusoes: list[Exclusion]
    ) -> _Vencimento:
        snapshot = chain.underlying
        tau = resolve_time_to_expiry(vencimento, pregao, self._calendar, self._day_count)
        mercado = SeriesMarket(
            snapshot.spot, snapshot.risk_free_rate.as_continuous(), tau.year_fraction
        )
        do_vencimento = [q for q in chain.quotes if q.contract.terms.expiry == vencimento]
        smile = build_smile(vencimento, do_vencimento, mercado)
        analisadas: list[_Serie] = []
        for quote in do_vencimento:
            serie = self._serie(chain, quote, smile, mercado, tau)
            if isinstance(serie, Exclusion):
                exclusoes.append(serie)
            else:
                analisadas.append(serie)
        por_strike = sorted(analisadas, key=lambda s: (s.strike, s.symbol))

        def strikes(tipo: OptionType) -> tuple[float, ...]:
            return tuple(
                sorted(
                    {
                        q.contract.terms.strike
                        for q in do_vencimento
                        if q.contract.terms.option_type is tipo
                    }
                )
            )

        return _Vencimento(
            expiry=vencimento,
            business_days=self._calendar.business_days_between(pregao, vencimento),
            market=mercado,
            smile=smile,
            calls=tuple(
                s for s in por_strike if s.quote.contract.terms.option_type is OptionType.CALL
            ),
            puts=tuple(
                s for s in por_strike if s.quote.contract.terms.option_type is OptionType.PUT
            ),
            call_strikes=strikes(OptionType.CALL),
            put_strikes=strikes(OptionType.PUT),
        )

    def _serie(
        self,
        chain: OptionChain,
        quote: OptionQuote,
        smile: VolSmile,
        mercado: SeriesMarket,
        tau: TimeToExpiry,
    ) -> _Serie | Exclusion:
        termos = quote.contract.terms
        simbolo = quote.contract.symbol
        if not self._model.supports(termos):
            if (
                termos.option_type is OptionType.PUT
                and termos.exercise_style is ExerciseStyle.AMERICAN
            ):
                motivo = "put americana não suportada (ADR-0002)"
            else:
                motivo = f"termos não suportados pelo modelo {self._model.model_id!r}"
            return Exclusion(ExclusionScope.SERIES, simbolo, motivo)
        risco = series_risk(quote, smile, mercado)
        if risco is None:
            return Exclusion(
                ExclusionScope.SERIES,
                simbolo,
                "sem delta: sem vol implícita da série nem do smile (fora do smile)",
            )
        vol = risco.vol if risco.vol is not None else chain.underlying.volatility.value
        snapshot = replace(chain.underlying, volatility=Volatility(vol, self._day_count))
        try:
            (resultado,) = self._model.price_many(
                [PricingRequest(terms=termos, snapshot=snapshot, time_to_expiry=tau)]
            )
        except UnsupportedExerciseStyleError as erro:
            return Exclusion(ExclusionScope.SERIES, simbolo, str(erro))
        return _Serie(
            quote=quote,
            delta=resultado.greeks.delta,
            exercise_probability=risco.exercise_probability,
            implied_vol=risco.implied_vol,
        )

    # ------------------------------------------------------------------
    # Estruturas
    # ------------------------------------------------------------------

    def _estruturas(
        self,
        chain: OptionChain,
        dados: _Vencimento,
        resumo: UnderlyingSummary,
        tabela: CostSchedule,
        command: RankIncomeCommand,
        exclusoes: list[Exclusion],
    ) -> list[IncomeCandidate]:
        candidatos: list[IncomeCandidate] = []

        def na_faixa(serie: _Serie) -> bool:
            return command.delta_min <= abs(serie.delta) <= command.delta_max

        def montar(
            estrutura: IncomeStructure, pernas: tuple[tuple[_Serie, Side], ...], rotulo: str
        ) -> None:
            candidato = self._candidato(
                chain, dados, resumo, tabela, command, estrutura, pernas, rotulo
            )
            if isinstance(candidato, Exclusion):
                exclusoes.append(candidato)
            else:
                candidatos.append(candidato)

        def trava(
            vendida: _Serie, series: tuple[_Serie, ...], strikes: tuple[float, ...], passos: int
        ) -> None:
            comprada = self._mais_fora(series, strikes, vendida, passos)
            if isinstance(comprada, str):
                exclusoes.append(
                    Exclusion(ExclusionScope.STRUCTURE, f"{vendida.symbol}/?", comprada)
                )
                return
            montar(
                IncomeStructure.CREDIT_SPREAD,
                ((vendida, Side.SELL), (comprada, Side.BUY)),
                f"{vendida.symbol}/{comprada.symbol}",
            )

        passos = command.spread_width_steps
        for put in dados.puts:
            if not na_faixa(put):
                continue
            if IncomeStructure.CASH_SECURED_PUT in command.structures:
                montar(IncomeStructure.CASH_SECURED_PUT, ((put, Side.SELL),), put.symbol)
            if IncomeStructure.CREDIT_SPREAD in command.structures:
                trava(put, dados.puts, dados.put_strikes, -passos)
        for call in dados.calls:
            if not na_faixa(call):
                continue
            if IncomeStructure.COVERED_CALL in command.structures:
                montar(IncomeStructure.COVERED_CALL, ((call, Side.SELL),), call.symbol)
            if IncomeStructure.CREDIT_SPREAD in command.structures:
                trava(call, dados.calls, dados.call_strikes, passos)
        return candidatos

    @staticmethod
    def _mais_fora(
        analisadas: tuple[_Serie, ...], strikes: tuple[float, ...], vendida: _Serie, passos: int
    ) -> _Serie | str:
        """A série ``|passos|`` strikes adiante (negativo = menores); senão o motivo.

        Os strikes contam TODAS as séries do vencimento e tipo: se a do strike
        escolhido foi excluída (sem delta, put americana...), o motivo aponta
        ela, em vez de fingir que o strike não existe.
        """
        indice = strikes.index(vendida.strike) + passos
        if not 0 <= indice < len(strikes):
            return f"sem strike {abs(passos)} passo(s) mais fora do dinheiro para a perna comprada"
        alvo = strikes[indice]
        for serie in analisadas:
            if serie.strike == alvo:
                return serie
        return (
            f"perna comprada no strike {alvo:g} sem série analisada "
            f"(ver a exclusão da série desse strike)"
        )

    def _premio(self, serie: _Serie, lado: Side, dados: _Vencimento) -> LegPremium | str:
        """Prêmio pelo lado do book, TEÓRICO se elegível; senão o motivo da falta de preço."""
        premio = executable_premium(serie.quote, lado)
        if premio is not None:
            return premio
        if serie.quote.is_theoretical_eligible:
            teorico = theoretical_premium(serie.quote, dados.smile, dados.market)
            if teorico is not None:
                return teorico
            return f"perna sem preço: {serie.symbol} elegível ao teórico, mas fora do smile"
        lado_nome = "bid" if lado is Side.SELL else "ask"
        return f"perna sem preço: {serie.symbol} sem {lado_nome} para {lado.name.lower()}"

    def _filtros(self, serie: _Serie, command: RankIncomeCommand) -> str | None:
        if command.min_trades is not None and serie.quote.trades < command.min_trades:
            return (
                f"filtro de liquidez: {serie.symbol} com {serie.quote.trades} negócios "
                f"(mínimo {command.min_trades})"
            )
        if command.max_spread_pct is not None:
            spread = serie.spread_pct
            if spread is None:
                return f"filtro de spread: {serie.symbol} sem book completo para medir o spread"
            if spread > command.max_spread_pct:
                return (
                    f"filtro de spread: {serie.symbol} com spread {spread:.4f} "
                    f"(máximo {command.max_spread_pct:.4f})"
                )
        return None

    def _candidato(
        self,
        chain: OptionChain,
        dados: _Vencimento,
        resumo: UnderlyingSummary,
        tabela: CostSchedule,
        command: RankIncomeCommand,
        estrutura: IncomeStructure,
        pernas: tuple[tuple[_Serie, Side], ...],
        rotulo: str,
    ) -> IncomeCandidate | Exclusion:
        def fora(motivo: str) -> Exclusion:
            return Exclusion(ExclusionScope.STRUCTURE, rotulo, motivo)

        precificadas: list[tuple[_Serie, Side, LegPremium]] = []
        for serie, lado in pernas:
            filtro = self._filtros(serie, command)
            if filtro is not None:
                return fora(filtro)
            premio = self._premio(serie, lado, dados)
            if isinstance(premio, str):
                return fora(premio)
            precificadas.append((serie, lado, premio))
        try:
            metricas = self._metricas(chain, dados, tabela, command, estrutura, precificadas)
        except (InvalidDomainValueError, InvalidStrategyError) as erro:
            return fora(f"dado inconsistente: {erro}")
        return IncomeCandidate(
            underlying=resumo.symbol,
            structure=estrutura,
            expiry=dados.expiry,
            legs=tuple(self._perna(s, lado, p) for s, lado, p in precificadas),
            metrics=metricas,
            underlying_book_available=resumo.book_available,
            profile=self._perfil(chain, tabela, command, estrutura, precificadas, metricas),
        )

    @staticmethod
    def _perfil(
        chain: OptionChain,
        tabela: CostSchedule,
        command: RankIncomeCommand,
        estrutura: IncomeStructure,
        precificadas: list[tuple[_Serie, Side, LegPremium]],
        metricas: IncomeMetrics,
    ) -> IncomeProfile:
        """Pontos do gráfico de payoff, pelo mesmo modelo de custos das métricas."""
        spot = chain.underlying.spot
        return income_profile(
            [
                PositionLeg(
                    serie.quote.contract.terms.option_type, lado, serie.strike, premio.premium
                )
                for serie, lado, premio in precificadas
            ],
            current_spot=spot,
            schedule=tabela,
            shares=command.reference_shares,
            stock_purchase_price=spot if estrutura is IncomeStructure.COVERED_CALL else None,
            breakevens=(metricas.breakeven, metricas.net_breakeven),
        )

    def _metricas(
        self,
        chain: OptionChain,
        dados: _Vencimento,
        tabela: CostSchedule,
        command: RankIncomeCommand,
        estrutura: IncomeStructure,
        precificadas: list[tuple[_Serie, Side, LegPremium]],
    ) -> IncomeMetrics:
        du = dados.business_days
        cdi = chain.underlying.risk_free_rate
        acoes = command.reference_shares
        vendida, _, premio = precificadas[0]
        if estrutura is IncomeStructure.CASH_SECURED_PUT:
            return cash_secured_put_metrics(
                strike=vendida.strike,
                premium_per_share=premio.premium,
                business_days=du,
                cdi=cdi,
                cost_schedule=tabela,
                reference_shares=acoes,
            )
        if estrutura is IncomeStructure.COVERED_CALL:
            return covered_call_metrics(
                spot=chain.underlying.spot,
                strike=vendida.strike,
                premium_per_share=premio.premium,
                business_days=du,
                cdi=cdi,
                cost_schedule=tabela,
                reference_shares=acoes,
            )
        legs = [
            StrategyLeg(
                symbol=serie.symbol,
                terms=serie.quote.contract.terms,
                side=lado,
                quantity=acoes,
                premium=p.premium,
            )
            for serie, lado, p in precificadas
        ]
        return credit_spread_metrics(
            vertical_spread(legs),
            business_days=du,
            cdi=cdi,
            cost_schedule=tabela,
            reference_shares=acoes,
        )

    @staticmethod
    def _perna(serie: _Serie, lado: Side, premio: LegPremium) -> CandidateLeg:
        termos = serie.quote.contract.terms
        return CandidateLeg(
            symbol=serie.symbol,
            option_type=termos.option_type,
            side=lado,
            strike=termos.strike,
            expiry=termos.expiry,
            exercise_style=termos.exercise_style,
            premium=premio,
            delta=serie.delta,
            exercise_probability=serie.exercise_probability,
            implied_vol=serie.implied_vol,
            trades=serie.quote.trades,
            volume=serie.quote.volume,
            spread_pct=serie.spread_pct,
        )

"""Família Volatilidade do book (spec da semana 3, §3.3).

Vol alta (e neutra, rotulada "sem sinal claro"): iron condor vendido (vendidas na faixa de delta,
compradas um strike mais fora), borboleta comprada (miolo no dinheiro, asas a 1 e a 2 strikes) e,
só com a perda ilimitada liberada no preset, strangle vendido. Vol baixa (e neutra): straddle
comprado no dinheiro e strangle comprado na faixa de delta.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final

from options_engine.domain.analytics.volatility import VolContext, VolRegime
from options_engine.domain.book.model import (
    BookExclusion,
    BookItem,
    BookLabel,
    FamilyResult,
    Metric,
    MetricUnit,
)
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.book.scan import (
    Outcome,
    PricedLeg,
    ScannedExpiry,
    ScannedSeries,
    approximation_labels,
    book_legs,
    evaluate,
    keeps_liquidity,
    price_leg,
    scan_chain,
    std_devs_to,
)
from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.templates import Family

__all__ = ["volatility_items"]

_LOTE: Final = 100
_C, _P = OptionType.CALL, OptionType.PUT
_B, _S = Side.BUY, Side.SELL


def volatility_items(
    chain: OptionChain,
    context: VolContext,
    settings: BookSettings,
    schedule: CostSchedule,
    business_days: Mapping[date, int],
) -> FamilyResult:
    """Vendas de vol (maior ganho/risco primeiro) e compras (menor movimento até o breakeven
    primeiro), conforme o regime de vol do ativo."""
    vencimentos, exclusoes = scan_chain(chain, business_days, settings.expiries)
    fora = list(exclusoes)
    vendas: list[BookItem] = []
    compras: list[BookItem] = []
    for vencimento in vencimentos:
        montador = _Montador(chain, context, settings, schedule, vencimento, fora)
        if context.regime is not VolRegime.BAIXA:
            vendas += montador.iron_condors() + montador.borboletas()
            if settings.allow_unlimited_loss:
                vendas += montador.strangles_vendidos()
        if context.regime is not VolRegime.ALTA:
            compras += montador.straddles() + montador.strangles_comprados()
    return FamilyResult.combine(
        FamilyResult.of(vendas, fora), FamilyResult.of(compras, ascending=True)
    )


@dataclass(frozen=True, slots=True)
class _Montador:
    chain: OptionChain
    context: VolContext
    settings: BookSettings
    schedule: CostSchedule
    expiry: ScannedExpiry
    exclusions: list[BookExclusion]

    # --- estruturas ---------------------------------------------------------------------------

    def iron_condors(self) -> list[BookItem]:
        itens = []
        puts = [(p, self._mais_fora(p, -1)) for p in self.expiry.in_delta_range(_P, self.settings)]
        calls = [(c, self._mais_fora(c, 1)) for c in self.expiry.in_delta_range(_C, self.settings)]
        for vendida_put, comprada_put in puts:
            for vendida_call, comprada_call in calls:
                if comprada_put is None or comprada_call is None:
                    continue
                if vendida_put.strike >= vendida_call.strike:
                    continue
                pernas = self._precificar(
                    (comprada_put, _B, _LOTE),
                    (vendida_put, _S, _LOTE),
                    (vendida_call, _S, _LOTE),
                    (comprada_call, _B, _LOTE),
                )
                item = pernas and self._limitada(
                    "iron_condor_vendido",
                    pernas,
                    "o iron condor recebe {credito} para arriscar {risco}",
                )
                if item:
                    itens.append(item)
        return itens

    def borboletas(self) -> list[BookItem]:
        itens: list[BookItem] = []
        miolo = self.expiry.at_the_money(_C)
        if miolo is None:
            return itens
        for largura in (1, 2):
            baixa, alta = (
                self.expiry.neighbor(miolo, -largura),
                self.expiry.neighbor(miolo, largura),
            )
            if baixa is None or alta is None:
                continue
            pernas = self._precificar((baixa, _B, _LOTE), (miolo, _S, 2 * _LOTE), (alta, _B, _LOTE))
            item = pernas and self._limitada(
                "borboleta_comprada", pernas, "a borboleta custa {debito} para ganhar até {ganho}"
            )
            if item:
                itens.append(item)
        return itens

    def strangles_vendidos(self) -> list[BookItem]:
        itens = []
        for put in self.expiry.in_delta_range(_P, self.settings):
            for call in self.expiry.in_delta_range(_C, self.settings):
                if put.strike >= call.strike:
                    continue
                pernas = self._precificar((put, _S, _LOTE), (call, _S, _LOTE))
                item = pernas and self._strangle_vendido(pernas)
                if item:
                    itens.append(item)
        return itens

    def straddles(self) -> list[BookItem]:
        puts = {p.strike: p for p in self.expiry.puts}
        com_put = [c for c in self.expiry.calls if c.strike in puts]
        if not com_put:
            return []
        spot = self.expiry.market.spot
        call = min(com_put, key=lambda c: (abs(c.strike - spot), c.strike))
        pernas = self._precificar((call, _B, _LOTE), (puts[call.strike], _B, _LOTE))
        item = pernas and self._compra("straddle_comprado", pernas, "o straddle comprado")
        return [item] if item else []

    def strangles_comprados(self) -> list[BookItem]:
        itens = []
        for put in self.expiry.in_delta_range(_P, self.settings):
            for call in self.expiry.in_delta_range(_C, self.settings):
                if put.strike >= call.strike:
                    continue
                pernas = self._precificar((put, _B, _LOTE), (call, _B, _LOTE))
                item = pernas and self._compra("strangle_comprado", pernas, "o strangle comprado")
                if item:
                    itens.append(item)
        return itens

    # --- critérios ----------------------------------------------------------------------------

    def _limitada(self, chave: str, pernas: list[PricedLeg], frase: str) -> BookItem | None:
        """Ganho e perda limitados: critério ganho/risco, risco até o máximo do preset."""
        resultado = self._avaliar(chave, pernas)
        ganho, perda = resultado.net_max_gain, resultado.net_max_loss
        caixa = _caixa(resultado.net_premium)
        if (
            ganho is None
            or perda is None
            or ganho <= 0.0
            or -perda > self.settings.max_risk
            or ("{credito}" in frase) != (caixa.key == "credito")
        ):
            return None
        criterio = Metric(
            "ganho_risco", "ganho máximo / perda máxima, líquidos", ganho / -perda, MetricUnit.RATIO
        )
        apoio = [
            caixa,
            Metric("ganho", "ganho máximo líquido", ganho, MetricUnit.CURRENCY),
            Metric("risco", "perda máxima líquida", -perda, MetricUnit.CURRENCY),
            *self._breakevens(resultado),
            _prob(resultado),
        ]
        return self._item(
            chave,
            pernas,
            criterio,
            apoio,
            f"{frase} (ganho/risco {{ganho_risco}}), com {{prob_lucro}} de probabilidade de lucro.",
        )

    def _strangle_vendido(self, pernas: list[PricedLeg]) -> BookItem | None:
        resultado = self._avaliar("strangle_vendido", pernas)
        ganho = resultado.net_max_gain
        distancia = self._distancia(resultado)
        if ganho is None or ganho <= 0.0 or distancia is None:
            return None
        criterio = Metric(
            "dist_be", "distância ao breakeven mais perto", distancia, MetricUnit.STD_DEVS
        )
        apoio = [
            _caixa(resultado.net_premium),
            Metric("ganho", "ganho máximo líquido", ganho, MetricUnit.CURRENCY),
            _prob(resultado),
        ]
        return self._item(
            "strangle_vendido",
            pernas,
            criterio,
            apoio,
            "o strangle vendido recebe {credito} e só perde se o ativo andar mais de {dist_be} até "
            "um breakeven, com {prob_lucro} de probabilidade de lucro; a perda é ilimitada.",
            (BookLabel.PERDA_ILIMITADA,),
        )

    def _compra(self, chave: str, pernas: list[PricedLeg], nome: str) -> BookItem | None:
        """Compra de vol: critério o movimento até o breakeven mais perto (menor é melhor)."""
        resultado = self._avaliar(chave, pernas)
        perda, distancia = resultado.net_max_loss, self._distancia(resultado)
        debito = -resultado.net_premium
        if perda is None or distancia is None or debito <= 0.0 or -perda > self.settings.max_risk:
            return None
        spot = self.chain.underlying.spot
        criterio = Metric(
            "dist_be", "movimento até o breakeven mais perto", distancia, MetricUnit.STD_DEVS
        )
        apoio = [
            Metric("debito", "débito", debito, MetricUnit.CURRENCY),
            Metric("custo_pct", "custo em % do ativo", debito / (spot * _LOTE), MetricUnit.PERCENT),
            Metric("risco", "perda máxima líquida", -perda, MetricUnit.CURRENCY),
            _prob(resultado),
        ]
        return self._item(
            chave,
            pernas,
            criterio,
            apoio,
            f"{nome} custa {{debito}} ({{custo_pct}} do ativo) e precisa de um movimento de "
            "{dist_be} até o breakeven mais perto, com {prob_lucro} de probabilidade de lucro.",
        )

    # --- apoio --------------------------------------------------------------------------------

    def _mais_fora(self, vendida: ScannedSeries, passos: int) -> ScannedSeries | None:
        comprada = self.expiry.neighbor(vendida, passos)
        if comprada is None:
            self.exclusions.append(
                BookExclusion(
                    f"{vendida.symbol}/?",
                    "sem strike 1 passo mais fora do dinheiro para a perna comprada",
                )
            )
        return comprada

    def _precificar(self, *pernas: tuple[ScannedSeries, Side, int]) -> list[PricedLeg] | None:
        precificadas = []
        for serie, lado, quantidade in pernas:
            perna = price_leg(self.expiry, serie, lado, quantidade)
            if isinstance(perna, str):
                rotulo = "/".join(s.symbol for s, _, _ in pernas)
                self.exclusions.append(BookExclusion(rotulo, perna))
                return None
            precificadas.append(perna)
        return precificadas if keeps_liquidity(precificadas, self.settings) else None

    def _avaliar(self, chave: str, pernas: Sequence[PricedLeg]) -> Outcome:
        return evaluate(chave, pernas, self.chain, self.expiry, self.schedule)

    def _distancia(self, resultado: Outcome) -> float | None:
        distancias = [self._dp(be) for be in resultado.breakevens if be > 0.0]
        return min(distancias) if distancias else None

    def _dp(self, nivel: float) -> float:
        return std_devs_to(
            nivel, self.chain.underlying.spot, self.context.iv30, self.expiry.business_days
        )

    def _breakevens(self, resultado: Outcome) -> list[Metric]:
        spot = self.chain.underlying.spot
        abaixo = [be for be in resultado.breakevens if 0.0 < be < spot]
        acima = [be for be in resultado.breakevens if be >= spot]
        metricas = []
        if abaixo:
            metricas.append(
                Metric("be_baixo", "breakeven de baixo", self._dp(max(abaixo)), MetricUnit.STD_DEVS)
            )
        if acima:
            metricas.append(
                Metric("be_alto", "breakeven de cima", self._dp(min(acima)), MetricUnit.STD_DEVS)
            )
        return metricas

    def _item(
        self,
        chave: str,
        pernas: Sequence[PricedLeg],
        criterio: Metric,
        apoio: Sequence[Metric],
        frase: str,
        rotulos: tuple[BookLabel, ...] = (),
    ) -> BookItem:
        contexto = self.context
        vol = [
            Metric("iv30", "IV 30", contexto.iv30, MetricUnit.PERCENT),
            Metric("hv21", "HV 21", contexto.hv21, MetricUnit.PERCENT),
        ]
        if contexto.iv_rank is not None:
            vol.append(Metric("iv_rank", "IV rank", contexto.iv_rank, MetricUnit.PERCENT))
            abertura = "IV rank {iv_rank}, IV 30 de {iv30} e HV 21 de {hv21}: "
        else:
            abertura = "IV 30 de {iv30} e HV 21 de {hv21}, sem IV rank: "
        return BookItem(
            family=Family.VOLATILIDADE,
            template_key=chave,
            underlying=contexto.underlying,
            expiry=self.expiry.expiry,
            business_days=self.expiry.business_days,
            legs=book_legs(pernas),
            stock=None,
            criterion=criterio,
            metrics=(*apoio, *vol),
            reason=abertura + frase,
            labels=(*_rotulos(contexto), *rotulos, *approximation_labels(pernas)),
        )


def _caixa(net_premium: float) -> Metric:
    if net_premium > 0.0:
        return Metric("credito", "crédito", net_premium, MetricUnit.CURRENCY)
    return Metric("debito", "débito", -net_premium, MetricUnit.CURRENCY)


def _prob(resultado: Outcome) -> Metric:
    return Metric(
        "prob_lucro", "probabilidade de lucro", resultado.probability_of_profit, MetricUnit.PERCENT
    )


def _rotulos(context: VolContext) -> tuple[BookLabel, ...]:
    rotulos = []
    if context.regime is VolRegime.NEUTRA:
        rotulos.append(BookLabel.SEM_SINAL_CLARO)
    if context.regime_from_hv:
        rotulos.append(BookLabel.REGIME_PELA_HV)
    if context.extrapolated:
        rotulos.append(BookLabel.IV_EXTRAPOLADA)
    return tuple(rotulos)

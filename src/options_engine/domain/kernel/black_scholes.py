"""Kernel Black-Scholes(-Merton) europeu — functional core.

Funções puras sobre floats. stdlib only. Sem I/O, sem objetos ricos, sem
estado. O contrato de domínio voltado ao público (``PricingModel``) é
batch-first e vive em ``domain/pricing`` (Sprint 2/3); as funções escalares
deste módulo são detalhe interno de implementação — os intermediários nunca
vazam pelo port.

Unidades canônicas (fazem parte do contrato — ver docs/ARCHITECTURE.md):
    s      spot, > 0
    k      strike, > 0
    tau    tempo até o vencimento em ANOS, >= 0. A conversão dias -> ano é
           responsabilidade de camadas superiores (``DayCountConvention``,
           default ratificado: BUSINESS_252).
    r      taxa livre de risco com capitalização CONTÍNUA, decimal. CDI
           (efetiva anual base 252) deve ser convertido antes, via
           ``RiskFreeRate.as_continuous()`` (Sprint 2).
    sigma  volatilidade anualizada, decimal (0.20 == 20%), >= 0, na MESMA
           base de anualização de ``tau``.
    q      carry/dividend yield contínuo, decimal (default 0.0).
    theta  por ANO calendário (exibição por dia é conversão do adapter).
    vega   por 1.00 de sigma (exibição por ponto de vol é do adapter).
    rho    por 1.00 de taxa.

Contrato de fronteira (tabela normativa em docs/ARCHITECTURE.md):
    Entradas ilegais -> ``InvalidKernelInputError`` (filha de ``DomainError``):
        qualquer input não finito; s<=0; k<=0; sigma<0; tau<0; e
        |r|·tau >= 700 ou |q|·tau >= 700 (fator de desconto fora da faixa
        representável de ``exp`` em float64 — sem esta guarda, um
        ``OverflowError`` cru atravessaria a fronteira do domínio).
    tau == 0   -> payoff intrínseco; delta = degrau (±0.5 em s == k, por
        convenção); gamma/vega/theta/rho = 0 por convenção documentada —
        gamma ATM no vencimento é matematicamente um delta de Dirac;
        reportar 0 é decisão, não acidente.
    sigma == 0 -> ativo determinístico: intrínseco descontado sobre o
        forward F = s·e^((r-q)·tau); gregas como limites analíticos da
        fórmula (contínuos com sigma -> 0+).
    sigma·sqrt(tau) em underflow (sigma > 0 e tau > 0, mas o produto vale
        0.0 em float64) -> mesmo ramo determinístico: sem difusão
        representável, o limite correto é o intrínseco descontado.
    preço >= 0.0 sempre (VV-PLAN §6, linha Deep OTM): piso em zero contra o
        ruído de cancelamento em float — ver ``bs_outputs`` e
        ``_deterministic``.

O par (preço, 5 gregas) é derivado de UM único conjunto de intermediários
(d1, d2, N(d1), N(d2), n(d1), fatores de desconto) — risco B3: recomputar
log/sqrt/erf por grega custaria ~6x sem nenhum ganho.

Nota de modelagem: ``is_call: bool`` keyword-only é a representação do
functional core; o antipadrão condenado no domínio é ``is_call`` em objetos
de negócio — lá o tipo é o enum ``OptionType``, traduzido para bool na
fronteira do shell (Sprint 2).

Referências: Hull, *Options, Futures and Other Derivatives*, 10ª ed.,
caps. 15/19; Haug, *The Complete Guide to Option Pricing Formulas*, 2ª ed.
"""

from math import exp, isfinite, log, sqrt
from typing import NamedTuple

from options_engine.domain.kernel.distributions import norm_cdf, norm_pdf
from options_engine.domain.model.errors import InvalidKernelInputError

__all__ = ["BSOutputs", "bs_outputs", "bs_price", "d1_d2"]


class BSOutputs(NamedTuple):
    """Preço e gregas em unidades canônicas (ver docstring do módulo)."""

    price: float
    delta: float
    gamma: float
    theta_per_year: float
    vega_per_vol_unit: float
    rho: float


def _check_inputs(s: float, k: float, tau: float, r: float, sigma: float, q: float) -> None:
    if not (
        isfinite(s)
        and isfinite(k)
        and isfinite(tau)
        and isfinite(r)
        and isfinite(sigma)
        and isfinite(q)
    ):
        raise InvalidKernelInputError(
            f"todos os inputs devem ser finitos; recebido "
            f"s={s!r}, k={k!r}, tau={tau!r}, r={r!r}, sigma={sigma!r}, q={q!r}"
        )
    # As condições usam a forma `not (x > 0)` em vez de `x <= 0` de propósito:
    # comparações com NaN são sempre False, logo NaN também seria rejeitado
    # mesmo sem a guarda de finitude acima (defesa em profundidade).
    if not (s > 0.0) or not (k > 0.0):
        raise InvalidKernelInputError(f"spot e strike devem ser > 0; recebido s={s!r}, k={k!r}")
    if not (sigma >= 0.0):
        raise InvalidKernelInputError(f"sigma deve ser >= 0; recebido {sigma!r}")
    if not (tau >= 0.0):
        raise InvalidKernelInputError(f"tau deve ser >= 0; recebido {tau!r}")
    if abs(r) * tau >= 700.0 or abs(q) * tau >= 700.0:
        raise InvalidKernelInputError(
            f"fator de desconto fora da faixa representável de exp em float64 "
            f"(|r|*tau ou |q|*tau >= 700); recebido r={r!r}, q={q!r}, tau={tau!r}"
        )


def _expired(s: float, k: float, *, is_call: bool) -> BSOutputs:
    """tau == 0: payoff intrínseco; gregas por convenção documentada."""
    if is_call:
        price = max(s - k, 0.0)
        delta = 1.0 if s > k else (0.5 if s == k else 0.0)
    else:
        price = max(k - s, 0.0)
        delta = -1.0 if s < k else (-0.5 if s == k else 0.0)
    return BSOutputs(price, delta, 0.0, 0.0, 0.0, 0.0)


def _deterministic(
    s: float, k: float, tau: float, r: float, q: float, *, is_call: bool
) -> BSOutputs:
    """sigma == 0: o subjacente cresce ao drift (r - q) com certeza.

    Preço = intrínseco descontado sobre o forward; gregas são os limites
    analíticos da fórmula BS quando sigma -> 0+ (continuidade verificada em
    teste contra sigma = 1e-8).

    O preço tem piso em zero porque o ramo é decidido por ``forward > k`` (ou
    ``<``) mas precificado por ``s*df_q - k*df_r``: caminhos aritméticos
    distintos. Com o forward a poucos ulps do strike, a diferença arredonda
    para um negativo de alguns ulps (~1e-15 com s ~ 30), violando
    ``e^(-r*tau)*max(F - k, 0) >= 0`` do contrato.
    """
    df_r = exp(-r * tau)
    df_q = exp(-q * tau)
    forward = s * exp((r - q) * tau)
    if is_call:
        if forward > k:
            return BSOutputs(
                price=max(s * df_q - k * df_r, 0.0),
                delta=df_q,
                gamma=0.0,
                theta_per_year=q * s * df_q - r * k * df_r,
                vega_per_vol_unit=0.0,
                rho=k * tau * df_r,
            )
        delta = 0.5 * df_q if forward == k else 0.0
        return BSOutputs(0.0, delta, 0.0, 0.0, 0.0, 0.0)
    if forward < k:
        return BSOutputs(
            price=max(k * df_r - s * df_q, 0.0),
            delta=-df_q,
            gamma=0.0,
            theta_per_year=r * k * df_r - q * s * df_q,
            vega_per_vol_unit=0.0,
            rho=-k * tau * df_r,
        )
    delta = -0.5 * df_q if forward == k else 0.0
    return BSOutputs(0.0, delta, 0.0, 0.0, 0.0, 0.0)


def _d1_d2(
    s: float, k: float, tau: float, r: float, sigma: float, q: float, sig_sqrt_tau: float
) -> tuple[float, float]:
    """Fonte ÚNICA da fórmula de d1/d2 — compartilhada por ``d1_d2`` e ``bs_outputs``.

    Achado da revisão adversarial: com a fórmula duplicada, um erro de sinal
    em q apenas na API pública sobreviveria à suíte inteira.
    """
    d1 = (log(s / k) + (r - q + 0.5 * sigma * sigma) * tau) / sig_sqrt_tau
    return d1, d1 - sig_sqrt_tau


def d1_d2(
    s: float, k: float, tau: float, r: float, sigma: float, q: float = 0.0
) -> tuple[float, float]:
    """(d1, d2) de Black-Scholes-Merton. Pré-condição: sigma·sqrt(tau) > 0."""
    _check_inputs(s, k, tau, r, sigma, q)
    sig_sqrt_tau = sigma * sqrt(tau)
    if sig_sqrt_tau == 0.0:  # tau == 0, sigma == 0 ou underflow do produto
        raise InvalidKernelInputError(
            f"d1/d2 exigem sigma*sqrt(tau) > 0; recebido tau={tau!r}, sigma={sigma!r}"
        )
    return _d1_d2(s, k, tau, r, sigma, q, sig_sqrt_tau)


def bs_outputs(
    s: float,
    k: float,
    tau: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    *,
    is_call: bool,
) -> BSOutputs:
    """Preço e gregas de uma opção europeia (Black-Scholes-Merton).

    Levanta ``InvalidKernelInputError`` para entradas ilegais; trata os
    limites legais tau == 0 e sigma == 0 com ramos em forma fechada (ver
    contrato de fronteira no docstring do módulo).
    """
    _check_inputs(s, k, tau, r, sigma, q)
    if tau == 0.0:
        return _expired(s, k, is_call=is_call)

    # Intermediários compartilhados — computados UMA vez para as 6 saídas.
    sqrt_tau = sqrt(tau)
    sig_sqrt_tau = sigma * sqrt_tau
    if sig_sqrt_tau == 0.0:
        # sigma == 0 exato OU underflow do produto (achado da revisão:
        # tau=1e-250 estourava ZeroDivisionError cru): sem difusão
        # representável, o limite é o determinístico.
        return _deterministic(s, k, tau, r, q, is_call=is_call)
    d1, d2 = _d1_d2(s, k, tau, r, sigma, q, sig_sqrt_tau)
    df_r = exp(-r * tau)
    df_q = exp(-q * tau)
    n_d1 = norm_pdf(d1)

    if is_call:
        nd1 = norm_cdf(d1)
        nd2 = norm_cdf(d2)
        price = s * df_q * nd1 - k * df_r * nd2
        delta = df_q * nd1
        theta = (
            -(s * sigma * df_q * n_d1) / (2.0 * sqrt_tau) + q * s * df_q * nd1 - r * k * df_r * nd2
        )
        rho = k * tau * df_r * nd2
    else:
        nmd1 = norm_cdf(-d1)
        nmd2 = norm_cdf(-d2)
        price = k * df_r * nmd2 - s * df_q * nmd1
        delta = -df_q * nmd1
        theta = (
            -(s * sigma * df_q * n_d1) / (2.0 * sqrt_tau)
            - q * s * df_q * nmd1
            + r * k * df_r * nmd2
        )
        rho = -k * tau * df_r * nmd2

    # Piso em zero (VV-PLAN §6, Deep OTM: "preço >= 0, sem underflow para
    # negativo"). Em OTM profundo, s*df_q*N(d1) e k*df_r*N(d2) (na put, o
    # espelho k*df_r*N(-d2) e s*df_q*N(-d1)) são dois números minúsculos e
    # quase iguais; cada produto carrega ~1 ulp de arredondamento e a
    # subtração cancela os dígitos significativos, podendo devolver um
    # subnormal NEGATIVO (ex.: -1e-323) onde o valor exato é um positivo
    # menor que esse ruído. O piso move o preço menos que o próprio ruído da
    # subtração (ordens abaixo da tolerância da paridade) e as gregas não
    # dependem dele. A ordem max(price, 0.0) preserva um eventual NaN em vez
    # de mascará-lo como 0.0.
    price = max(price, 0.0)

    # Gamma e vega são idênticos para call e put de mesmos parâmetros —
    # mesma expressão, mesmos intermediários (propriedade testada).
    gamma = df_q * n_d1 / (s * sig_sqrt_tau)
    vega = s * df_q * n_d1 * sqrt_tau
    return BSOutputs(price, delta, gamma, theta, vega, rho)


def bs_price(
    s: float,
    k: float,
    tau: float,
    r: float,
    sigma: float,
    q: float = 0.0,
    *,
    is_call: bool,
) -> float:
    """Açúcar de conveniência: apenas o preço."""
    return bs_outputs(s, k, tau, r, sigma, q, is_call=is_call).price

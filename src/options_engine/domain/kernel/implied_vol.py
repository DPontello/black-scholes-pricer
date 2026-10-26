"""Volatilidade implícita Black-Scholes(-Merton) europeia — functional core.

Funções puras sobre floats, stdlib only, sem I/O e sem estado. Inverte o
preço do kernel (``bs_outputs``) em sigma — a fórmula de preço NÃO é
reimplementada aqui: preço, vega e o limite inferior vêm todos do kernel.

Unidades: as mesmas de ``black_scholes`` (docs/CONVENTIONS.md §1) — ``price``
na moeda do subjacente, ``tau`` em anos, ``r``/``q`` contínuos; ``sigma``
devolvida anualizada e decimal, na mesma base de anualização de ``tau``.

Contrato (preço fora dos limites ou não convergência viram STATUS — nunca
exceção, nunca NaN). As regras valem NESTA ordem — a primeira que casa
decide, e a precedência é parte do contrato:
    1. Entradas ilegais -> ``InvalidKernelInputError``: ``price`` não finito
        ou < 0; ``sigma_tol`` não finito ou <= 0; ``max_iterations`` < 1; e
        tudo o que ``bs_outputs`` já rejeita (s<=0, k<=0, tau<0, não
        finitos, fator de desconto fora da faixa de ``exp``). A validação
        precede o atalho do vencimento: preço ilegal com tau == 0 também
        levanta.
    2. tau == 0 -> ``EXPIRED`` para QUALQUER preço legal, mesmo fora dos
        limites: no vencimento o preço é o intrínseco para qualquer sigma —
        a volatilidade não é identificável.
    3. price < limite inferior -> ``BELOW_INTRINSIC`` (comparação estrita).
        O limite inferior de não-arbitragem é o intrínseco DESCONTADO,
        ``max(±(S·e^(-q·tau) - K·e^(-r·tau)), 0)`` — que é exatamente o
        preço BS com sigma = 0, e por isso é calculado pelo próprio kernel.
    4. price >= limite superior -> ``ABOVE_UPPER_BOUND`` (o próprio limite
        incluso): ``S·e^(-q·tau)`` para call, ``K·e^(-r·tau)`` para put — o
        limite de sigma -> inf, nunca atingido por sigma finito.
    5. price == limite inferior -> ``CONVERGED`` com sigma = 0.0 exato
        (``METHOD_CLOSED_FORM``, 0 iterações): o limite inferior é atingido
        em sigma = 0 (ramo determinístico do kernel), então é solução, não
        ausência dela.
    6. tau abaixo da guarda de representabilidade (Limitações, abaixo) ->
        ``NO_CONVERGENCE`` sem iterar (``METHOD_NONE``, 0 iterações).
    7. Senão o solver itera: ``CONVERGED`` com sigma finito em
        ``[0, sigma_max]`` e o rótulo dos passos usados; ``max_iterations``
        esgotado -> ``NO_CONVERGENCE`` com sigma = ``None`` (nunca um
        número inventado; ``iterations == max_iterations`` e o ``method``
        ainda informa os passos tentados).

Algoritmo — Newton-Raphson salvaguardado por bracketing (rtsafe de Press et
al., *Numerical Recipes*, §9.4):
    * f(sigma) = preço_BS(sigma) - price é estritamente crescente em sigma
      (vega > 0 para tau > 0). A checagem de limites garante f(0) < 0 < f(inf),
      logo há raiz única.
    * Bracket inicial ``[0, sigma_max]`` com sigma_max = ``_TOTAL_VOL_CAP /
      sqrt(tau)``: para qualquer entrada válida do kernel o preço em
      sigma_max já é o limite superior em float64 (|ln(F/K)| < ~2.9e3 por
      construção, então N(d2) e N(-d1) ficam abaixo de ~1e-90), logo a raiz
      está no bracket sempre que ``price < limite superior``.
    * A cada iterada o bracket encolhe pelo sinal do resíduo. O passo de
      Newton (resíduo / vega) só é aceito se (a) cair dentro do bracket e (b)
      for no máximo metade do penúltimo passo; senão, bisseção. (b) é o
      critério de "vega pequeno" sem número mágico: vega pequeno relativo ao
      resíduo produz passo grande e cai na bisseção; vega == 0 (underflow em
      OTM profundo, ou o ramo sigma = 0 do kernel) é passo infinito. (b)
      também garante que os passos caem pelo menos à metade a cada duas
      iterações — término mesmo no regime de ruído de arredondamento.
    * Convergência: ``|passo| <= sigma_tol + _REL_STEP_FLOOR·sigma``. Num
      passo de bisseção o passo é a meia-largura do bracket, que contém a
      raiz — é cota de erro, não estimativa. O piso relativo de máquina
      garante término em qualquer escala de sigma (mesma convenção de
      ``scipy.optimize.brentq``).

Chute inicial — ``max(sigma_MK, sigma_BS)``, ambos em forma fechada:
    * sigma_MK = sqrt(2·|ln(F/K)| / tau) (Manaster & Koehler, 1982) é o
      ponto de inflexão do preço em sigma: convexo abaixo, côncavo acima.
    * sigma_BS = (price - limite inferior)·sqrt(2π) / (min(S̃, K̃)·sqrt(tau))
      — Brenner & Subrahmanyam (1988) aplicado ao valor-tempo, com
      S̃ = S·e^(-q·tau) e K̃ = K·e^(-r·tau). Por paridade, o valor-tempo é o
      preço da opção OTM equivalente, limitado por
      min(S̃, K̃)·sigma·sqrt(tau)/sqrt(2π): logo sigma_BS <= raiz SEMPRE.
    Com o máximo dos dois, ou o chute fica à esquerda da raiz na região
    côncava, ou no ponto de inflexão à direita da raiz na região convexa —
    nos dois casos Newton puro converge monotonicamente, sem ultrapassar a
    raiz (argumento de Manaster-Koehler). As salvaguardas entram quando a
    convergência é lenta (curva muito plana em OTM/ITM profundo, onde a
    regra da metade troca passos por bisseção) ou dominada por ruído
    (vega ~0); no domínio identificável a inversão é Newton puro em 2 a 12
    iterações (medido: 19.997 de 20.000 inversões do oráculo scipy).

Limitações conhecidas:
    * ``tau`` abaixo de ~5.6e-305 anos levaria sigma_max a um valor cujo
      quadrado transborda float64 dentro de ``d1`` do kernel; o solver não
      itera nesse regime e devolve ``NO_CONVERGENCE`` em vez de um número
      sem significado.
    * Os limites são comparados em float64, sem folga: quando o valor-tempo
      está abaixo do ulp do preço (OTM/ITM extremos, vol total muito alta),
      até um preço gerado pelo próprio kernel pode cair 1 ulp fora de um
      limite e virar ``BELOW_INTRINSIC``/``ABOVE_UPPER_BOUND`` — corretamente:
      esse preço não carrega informação sobre sigma.

Nota de modelagem (mesma do kernel BS): ``is_call: bool`` keyword-only é a
representação do functional core; no domínio o tipo é o enum ``OptionType``.

Referências: Manaster & Koehler, "The Calculation of Implied Variances from
the Black-Scholes Model: A Note", *Journal of Finance* 37(1), 1982; Brenner &
Subrahmanyam, "A Simple Formula to Compute the Implied Standard Deviation",
*Financial Analysts Journal* 44(5), 1988; Press et al., *Numerical Recipes*,
3ª ed., §9.4 (rtsafe); Jäckel, *Let's Be Rational*, 2015 (evolução prevista
no ROADMAP, fora do escopo desta entrega).
"""

import sys
from enum import Enum, unique
from math import exp, inf, isfinite, log, pi, sqrt
from typing import Final, NamedTuple

from options_engine.domain.kernel.black_scholes import bs_outputs, bs_price
from options_engine.domain.model.errors import InvalidKernelInputError

__all__ = [
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_SIGMA_TOL",
    "METHOD_BISECTION",
    "METHOD_CLOSED_FORM",
    "METHOD_NEWTON",
    "METHOD_NEWTON_BISECTION",
    "METHOD_NONE",
    "ImpliedVolResult",
    "ImpliedVolStatus",
    "implied_vol",
]

# --- parâmetros do solver (defaults nomeados, sobrescrevíveis por chamada) ---
# Tolerância ABSOLUTA em sigma (vol decimal): 1e-12 está ~8 ordens abaixo da
# precisão de cotação de vol (1e-4 = 0.01 ponto) e ainda é alcançável — o
# erro de reprecificação é vega·|Δsigma| <= ~2.2·S·1e-12 no domínio tau <= 30.
DEFAULT_SIGMA_TOL: Final = 1e-12
# Newton monotônico converge em poucas iterações (<= 12 medido). A bisseção
# pura do bracket inteiro até DEFAULT_SIGMA_TOL leva log2(sigma_max/sigma_tol)
# passos: ~51 em tau de 1 dia útil, e cabe em 100 para todo tau >= ~6e-33 ano.
# Orçamento esgotado vira NO_CONVERGENCE, nunca um sigma inventado.
DEFAULT_MAX_ITERATIONS: Final = 100

# --- rótulos de ``ImpliedVolResult.method`` ----------------------------------
METHOD_NEWTON: Final = "newton"  # só passos de Newton
METHOD_BISECTION: Final = "bisection"  # só passos de bisseção
METHOD_NEWTON_BISECTION: Final = "newton+bisection"  # misto
METHOD_CLOSED_FORM: Final = "closed_form"  # sigma = 0 exato no limite inferior
METHOD_NONE: Final = "none"  # status decidido antes de qualquer iteração

# --- constantes numéricas internas -------------------------------------------
# Teto da vol total sigma·sqrt(tau) do bracket inicial (racional no docstring
# do módulo): cobre o chute de Manaster-Koehler (sqrt(2·|ln(F/K)|) < ~76) e
# leva o preço ao limite superior em float64 para toda entrada válida.
_TOTAL_VOL_CAP: Final = 100.0
# Maior sigma cujo quadrado (``0.5·sigma·sigma`` em d1 do kernel) é finito.
_SIGMA_REPRESENTABLE_MAX: Final = sqrt(sys.float_info.max)
# Piso relativo do critério de parada: 4 ulps de sigma — abaixo disso o
# passo é ruído de representação, não informação.
_REL_STEP_FLOOR: Final = 4.0 * sys.float_info.epsilon
_SQRT_2PI: Final = sqrt(2.0 * pi)


@unique
class ImpliedVolStatus(Enum):
    """Desfecho da inversão — todo caso fora do "achou sigma" é um status.

    Precedência entre eles: contrato numerado no docstring do módulo.
    """

    CONVERGED = "converged"  # sigma achado; 0.0 exato no limite inferior
    BELOW_INTRINSIC = "below_intrinsic"  # price < intrínseco descontado (estrito)
    ABOVE_UPPER_BOUND = "above_upper_bound"  # price >= S·e^(-q·tau) (call) ou K·e^(-r·tau) (put)
    NO_CONVERGENCE = "no_convergence"  # orçamento esgotado ou tau irrepresentável
    EXPIRED = "expired"  # tau == 0: sigma não identificável


class ImpliedVolResult(NamedTuple):
    """Retorno rico da inversão (ROADMAP, Sprint 5).

    ``sigma`` é ``float`` se e somente se ``status`` é ``CONVERGED``; nos
    demais casos é ``None`` — nunca NaN, nunca um número inventado.
    ``iterations`` conta avaliações do kernel no laço do solver: 0 quando a
    checagem prévia decide (``METHOD_NONE`` nos status sem solução e na
    guarda de tau; ``METHOD_CLOSED_FORM`` em sigma = 0.0 no limite
    inferior), ``max_iterations`` no ``NO_CONVERGENCE`` por esgotamento.
    ``method`` é um dos rótulos ``METHOD_*``.
    """

    sigma: float | None
    status: ImpliedVolStatus
    iterations: int
    method: str


def _check_solver_inputs(price: float, sigma_tol: float, max_iterations: int) -> None:
    # `not (x >= 0)` / `not (x > 0)`: NaN compara False com tudo — rejeitado
    # mesmo sem a guarda de finitude (defesa em profundidade, como no kernel).
    if not (isfinite(price) and price >= 0.0):
        raise InvalidKernelInputError(f"preço deve ser finito e >= 0; recebido {price!r}")
    if not (isfinite(sigma_tol) and sigma_tol > 0.0):
        raise InvalidKernelInputError(f"sigma_tol deve ser finito e > 0; recebido {sigma_tol!r}")
    if max_iterations < 1:
        raise InvalidKernelInputError(f"max_iterations deve ser >= 1; recebido {max_iterations!r}")


def _unsolved(status: ImpliedVolStatus) -> ImpliedVolResult:
    """Status decidido pela checagem prévia: nenhuma iteração, nenhum sigma."""
    return ImpliedVolResult(None, status, 0, METHOD_NONE)


def _initial_guess(
    price: float,
    lower: float,
    s: float,
    k: float,
    tau: float,
    r: float,
    q: float,
    s_disc: float,
    k_disc: float,
) -> float:
    """``max(sigma_MK, sigma_BS)`` — racional e referências no docstring do módulo.

    ln(F/K) sai de ``log(s) - log(k)`` (nunca ``log(s_disc / k_disc)``): a
    razão dos descontados pode transbordar ou zerar em entradas extremas.
    """
    sqrt_tau = sqrt(tau)
    log_moneyness = log(s) - log(k) + (r - q) * tau
    inflection = sqrt(2.0 * abs(log_moneyness)) / sqrt_tau
    time_value = (price - lower) * _SQRT_2PI / (min(s_disc, k_disc) * sqrt_tau)
    return max(inflection, time_value)


def _newton_step(residual: float, vega: float) -> float:
    """Passo de Newton ``resíduo / vega``; vega nulo -> passo infinito (força bisseção)."""
    return residual / vega if vega > 0.0 else inf


def _method_label(newton_steps: int, bisection_steps: int) -> str:
    if bisection_steps == 0:
        return METHOD_NEWTON
    if newton_steps == 0:
        return METHOD_BISECTION
    return METHOD_NEWTON_BISECTION


def _safeguarded_newton(
    price: float,
    s: float,
    k: float,
    tau: float,
    r: float,
    q: float,
    *,
    is_call: bool,
    sigma: float,
    sigma_max: float,
    sigma_tol: float,
    max_iterations: int,
) -> ImpliedVolResult:
    """Newton-Raphson com bracket e fallback de bisseção (rtsafe, NR §9.4)."""
    lo, hi = 0.0, sigma_max
    # NR: os dois passos "anteriores" nascem com a largura do bracket, o que
    # libera Newton nas duas primeiras iterações.
    last_step = step_before_last = sigma_max
    newton_steps = bisection_steps = 0
    for iteration in range(1, max_iterations + 1):
        out = bs_outputs(s, k, tau, r, sigma, q, is_call=is_call)
        residual = out.price - price
        if residual < 0.0:
            lo = sigma
        else:
            hi = sigma
        newton = _newton_step(residual, out.vega_per_vol_unit)
        if lo <= sigma - newton <= hi and abs(newton) <= 0.5 * abs(step_before_last):
            step = newton
            sigma -= step
            newton_steps += 1
        else:
            step = 0.5 * (hi - lo)
            sigma = lo + step
            bisection_steps += 1
        if abs(step) <= sigma_tol + _REL_STEP_FLOOR * sigma:
            return ImpliedVolResult(
                sigma,
                ImpliedVolStatus.CONVERGED,
                iteration,
                _method_label(newton_steps, bisection_steps),
            )
        step_before_last, last_step = last_step, step
    return ImpliedVolResult(
        None,
        ImpliedVolStatus.NO_CONVERGENCE,
        max_iterations,
        _method_label(newton_steps, bisection_steps),
    )


def implied_vol(
    price: float,
    s: float,
    k: float,
    tau: float,
    r: float,
    q: float = 0.0,
    *,
    is_call: bool,
    sigma_tol: float = DEFAULT_SIGMA_TOL,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> ImpliedVolResult:
    """Volatilidade implícita de uma opção europeia (Black-Scholes-Merton).

    Devolve o sigma tal que ``bs_price(s, k, tau, r, sigma, q, is_call=...)``
    reproduz ``price`` — anualizado, decimal, na mesma base de anualização
    de ``tau``. Preço fora dos limites de não-arbitragem, opção vencida e
    não convergência viram ``status`` (contrato numerado, com a precedência,
    no docstring do módulo). Levanta ``InvalidKernelInputError`` só para
    entradas ilegais.

    Parâmetros do solver (keyword-only, defaults nomeados no módulo):
        sigma_tol       tolerância ABSOLUTA em sigma (vol decimal), finita e
                        > 0: ``|sigma - raiz| <= sigma_tol`` a menos do piso
                        relativo de máquina (4 ulps de sigma).
        max_iterations  teto de avaliações do kernel no laço, >= 1;
                        esgotado -> ``NO_CONVERGENCE`` com sigma ``None``.
    """
    _check_solver_inputs(price, sigma_tol, max_iterations)
    # O limite inferior É o preço BS com sigma = 0 — a mesma chamada valida
    # s, k, tau, r e q com o contrato do kernel (fonte única de validação).
    lower = bs_price(s, k, tau, r, 0.0, q, is_call=is_call)
    if tau == 0.0:
        return _unsolved(ImpliedVolStatus.EXPIRED)
    s_disc = s * exp(-q * tau)
    k_disc = k * exp(-r * tau)
    upper = s_disc if is_call else k_disc
    if price < lower:
        return _unsolved(ImpliedVolStatus.BELOW_INTRINSIC)
    if price >= upper:
        return _unsolved(ImpliedVolStatus.ABOVE_UPPER_BOUND)
    if price == lower:
        return ImpliedVolResult(0.0, ImpliedVolStatus.CONVERGED, 0, METHOD_CLOSED_FORM)
    sigma_max = _TOTAL_VOL_CAP / sqrt(tau)
    if sigma_max > _SIGMA_REPRESENTABLE_MAX:
        return _unsolved(ImpliedVolStatus.NO_CONVERGENCE)
    guess = _initial_guess(price, lower, s, k, tau, r, q, s_disc, k_disc)
    return _safeguarded_newton(
        price,
        s,
        k,
        tau,
        r,
        q,
        is_call=is_call,
        sigma=min(guess, sigma_max),
        sigma_max=sigma_max,
        sigma_tol=sigma_tol,
        max_iterations=max_iterations,
    )

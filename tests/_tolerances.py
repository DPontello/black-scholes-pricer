"""Fonte única de verdade das tolerâncias numéricas (VV-PLAN, tabela normativa).

Tolerância é decisão de engenharia derivada da fonte do oráculo e da física
do erro em ponto flutuante — nunca número mágico. Nenhum teste declara
tolerância inline: importe daqui. Mudar uma constante = mudar a tabela do
VV-PLAN = review explícito.
"""

import math

# --- vs valores publicados em livro-texto (arredondados pela fonte) ---------
# Metade da última casa decimal publicada — exigir mais que isso reprova o
# próprio livro (evidência: |4.759422 - 4.76| = 5.8e-4 > 1e-4).
ABS_BOOK_2DP = 5e-3  # Hull, preços a 2 casas
ABS_BOOK_4DP = 5e-5  # Haug, preços a 4 casas
ABS_BOOK_GREEKS = 5e-4  # Hull, gregas a 3 casas

# --- vs camada "verified" do golden (script stdlib independente do kernel) --
# Duas implementações independentes (erf vs erfc, ordens de operação
# distintas) concordam a ~1 ulp; 1e-12 dá margem de ~1e3x sobre o ruído.
REL_REGRESSION = 1e-12
ABS_REGRESSION_FLOOR = 1e-12  # escalar por max(s, k) no ponto de uso

# --- auto-consistência (mesmo binário, mesma aritmética) ---------------------
REL_SELF = 1e-12
ABS_SELF_FLOOR = 1e-12  # escalar pela escala do problema

# --- differential testing vs oráculo independente (scipy, job de CI) ---------
# Duas implementações da mesma fórmula com libms distintas (nossa erfc vs
# Cephes/ndtr do scipy) acumulam ~poucos ulps por avaliação; 1e-9 dá margem
# ~1e4x sobre o ruído real e ainda mata qualquer erro de fórmula (>= 0.01%).
REL_ORACLE = 1e-9
ABS_ORACLE_FLOOR = 1e-12  # escalar por max(S, K) no ponto de uso

# --- identidades matemáticas por caminhos aritméticos DIFERENTES --------------
# Ex.: homogeneidade BS(lam*s, lam*k) = lam*BS(s, k). O log da razão amplifica
# 1 ulp de diferença em (lam*s)/(lam*k) por um fator 1/(sigma*sqrt(tau)) — até
# ~1.6e4 no domínio testado —, então 1e-12 seria falso positivo garantido;
# 1e-9 mantém margem ~100x sobre o pior caso analisado.
REL_MATH_IDENTITY = 1e-9
ABS_MATH_IDENTITY_FLOOR = 1e-9  # escalar pela escala do problema

# --- fronteiras específicas (racionais na tabela do VV-PLAN §6) --------------
# Convergência ao intrínseco em tau = 1e-10: o valor-tempo residual ATM é
# ~0.4·s·sigma·sqrt(tau) ~ 8e-5 para s=100 — 1e-3 dá margem ~10x.
ABS_NEAR_EXPIRY_INTRINSIC = 1e-3
# Continuidade do ramo sigma=0 vs sigma=1e-8: em sigma tão pequeno, d1/d2
# saturam e a fórmula colapsa na forma fechada a ~ulps; 1e-9 por unidade de
# spot é margem enorme e ainda mataria qualquer erro de ramo.
ABS_SIGMA_CONTINUITY_PER_SPOT = 1e-9
# CDF vs valores de literatura transcritos a 16 dígitos: margem para erro de
# transcrição da última casa + ~1 ulp de variação de libm entre plataformas.
ABS_CDF_TABULATED = 1e-12

# --- payoff no vencimento (só somas/máximos, sem transcendentais) -------------
# Aritmética trivial: fsum de max() lineares. Tabela VV-PLAN §1.2, linha
# "Payoff no vencimento".
REL_PAYOFF = 1e-12
ABS_PAYOFF = 1e-12

# --- breakevens vs forma fechada ----------------------------------------------
# Fórmula exata, sem transcendentais; a interpolação linear entre kinks
# amplifica ~ulps quando o segmento é raso. Tabela VV-PLAN §1.2, linha
# "Breakevens do Iron Condor".
REL_BREAKEVEN = 1e-12
ABS_BREAKEVEN = 1e-9

# --- métricas de renda (domain/income/) — forma fechada -----------------------
# Custos e rendimentos são produtos, razões e fsum de poucos termos, mais UMA
# potência na anualização (via log1p/expm1: erro relativo ~x·ulp no expoente
# x <= ~700 antes do overflow, i.e. <= ~2e-13). Os golden cases são literais
# calculados à mão (decimais exatos ou 16 algarismos significativos): 1e-12
# dá margem >= 5x sobre o pior caso e ainda mata qualquer erro de fórmula. O
# piso absoluto cobre valores ~0 (IR nulo, rendimento de prêmio zero), onde o
# relativo não tem significado.
REL_INCOME = 1e-12
ABS_INCOME = 1e-12

# --- oráculo numérico do perfil líquido de renda (tests/income/) --------------
# O P&L líquido no vencimento avaliado perna a perna, cenário a cenário, com
# somas ingênuas, contra a forma fechada com fsum. Sem transcendentais: cada
# lado erra poucos ulps do MAIOR termo somado (strike x ações, ~1e4 em
# moeda), e perto do breakeven ou de resultado ~0 o cancelamento passa esse
# erro absoluto inteiro ao resultado. 1e-12 x escala dá margem ~1e3x sobre
# ~4 ulps (4 x 2.2e-16) e ainda mata qualquer erro de fórmula (centavos).
REL_INCOME_ORACLE = 1e-12
ABS_INCOME_ORACLE_PER_SCALE = 1e-12  # multiplicar pela escala strike x ações

# --- teste estatístico do GBM (seed fixa — determinístico, não flaky) --------
# Margem em erros-padrão sobre média e desvio dos log-retornos amostrados.
# Com seed fixa o teste é determinístico; o z só precisa acomodar o sorteio
# DESTA seed. z = 4.0 é folga estatística honesta (~6e-5 de massa além de 4sigma)
# e ainda mata erro de fórmula: um sqrt(dt) esquecido escala o desvio por
# ~16x (√252), dezenas de erros-padrão no N usado.
GBM_STAT_Z = 4.0

# --- folga para desigualdades (bounds, monotonia) ----------------------------
# Desigualdade estrita vira `>= -folga` para não flakar exatamente no limite.
INEQ_SLACK = 1e-9  # escalar pela escala do problema

# --- diferenças finitas centrais ---------------------------------------------
# Erro total = truncamento O(h^2) + roundoff O(eps/h); mínimo em
# h* ~ eps^(1/3) * escala, com erro ~ eps^(2/3) ~ 4e-11 (curva em U medida
# nesta máquina: ótimo em h/S = 1e-6 com |erro| = 6.1e-12). A tolerância
# 1e-6 dá margem ~1e4x porque f''' não é unitária perto de fronteiras.
EPS_MACHINE = 2.0**-52
FD_STEP = EPS_MACHINE ** (1.0 / 3.0)  # ~6.1e-6, multiplicar pela escala do parâmetro
REL_FD = 1e-6
ABS_FD = 1e-8
FD_ROUNDOFF_ULPS = 16.0  # ulps de ruído tolerados no numerador da FD (margem ~6x sobre o medido)


def fd_abs_tol(f_scale: float, h: float) -> float:
    """Tolerância absoluta de uma FD central: piso fixo + piso de roundoff.

    O numerador da FD central subtrai dois valores de magnitude ~``f_scale``,
    cada um carregando erro de alguns ulps; a divisão por 2h amplifica esse
    ruído para ~ulps·eps·f_scale/(2h) — o ramo ascendente da curva em U do
    VV-PLAN. Onde a grega vale ordens de magnitude menos que esse piso
    (ex.: theta deep ITM ~1e-10 com preço ~25), a FD é *fisicamente* incapaz
    de resolvê-la — apertar a tolerância ali mede ruído, não corretude. Onde
    a grega é relevante, o ramo relativo (``REL_FD``) governa e o piso é
    irrelevante.
    """
    return ABS_FD + FD_ROUNDOFF_ULPS * EPS_MACHINE * f_scale / (2.0 * h)


# --- volatilidade implícita (Sprint 5) ---------------------------------------
# Inverter preço em sigma PROPAGA erro de preço por 1/vega (condicionamento):
# Δsigma ≈ Δpreço / vega. Por isso a tolerância em sigma é uma função
# (``iv_sigma_abs_tol``), não um número: vega -> 0 (OTM/ITM profundo, tau -> 0)
# torna sigma fisicamente mal determinado, e a tolerância cresce junto em vez
# de flakar — mesma lógica do piso de roundoff da FD (VV-PLAN §5).
#
# Cota do solver: o critério de parada garante |sigma - raiz| <= sigma_tol
# (``DEFAULT_SIGMA_TOL`` = 1e-12 no kernel); 1e-11 dá margem 10x e ainda mata
# erro de status ou de convergência, que erram sigma em >= 1e-6.
ABS_IV_SIGMA = 1e-11
# Ruído de avaliação do preço pelo kernel, em ulps da escala max(S, K):
# medido <= ~4 ulps (|Δpreço|/escala = 9.1e-16 em 40k inversões no domínio
# identificável); 16 dá margem ~4x.
IV_ROUNDOFF_ULPS = 16.0
# Ida e volta preço -> sigma -> preço pelo MESMO kernel: erro = vega·|Δsigma| +
# ruído. Com vega <= S·sqrt(tau)/sqrt(2π) <= 2.2·S (tau <= 30) e |Δsigma| <=
# 1e-12, a cota teórica é ~2.2e-12·escala (medido: 9.1e-16·escala); 1e-11 cobre
# a cota teórica com folga ~4x.
ABS_IV_ROUNDTRIP_PRICE_FLOOR = 1e-11  # escalar por max(s, k) no ponto de uso


def iv_roundtrip_price_abs_tol(cancellation_scale: float, vega: float) -> float:
    """Tolerância absoluta do preço reavaliado na ida e volta da IV, por cota física.

    Substitui o piso ``ABS_IV_ROUNDTRIP_PRICE_FLOOR·max(S, K)`` onde há uma
    escala melhor (achado da revisão da Sprint 5: com K >> S esse piso chegava
    a 4x o próprio preço e não detectava nem erro de 100%). Dois termos:

    - ruído de avaliação, em ulps do MAIOR termo que a fórmula subtrai
      (``cancellation_scale``: ``S·e^(-qT)·N(±d1)`` ou ``K·e^(-rT)·N(±d2)``) —
      é ele, não ``max(S, K)``, que limita o erro de arredondamento;
    - cota do solver propagada pelo vega: ``vega·ABS_IV_SIGMA``.
    """
    return IV_ROUNDOFF_ULPS * EPS_MACHINE * cancellation_scale + vega * ABS_IV_SIGMA


def iv_sigma_abs_tol(price_error_bound: float, vega: float) -> float:
    """Tolerância absoluta em sigma: cota do solver + erro de preço / vega.

    ``price_error_bound`` é a cota de erro do PREÇO que originou a inversão,
    na moeda do subjacente: ruído do kernel (``IV_ROUNDOFF_ULPS·eps·escala``),
    divergência entre implementações (oráculo) ou arredondamento do livro
    (camada *published*). Vega nulo em float64 -> sigma não identificável:
    tolerância infinita (o teste deve então se apoiar no preço, não em sigma).
    """
    if vega <= 0.0:
        return math.inf
    return ABS_IV_SIGMA + price_error_bound / vega


def assert_close(
    actual: float, expected: float, *, rel: float, abs_: float, label: str = ""
) -> None:
    """Assert canônico: semântica ``math.isclose`` (OR entre rel e abs).

    ``==`` entre floats é proibido na suíte (exceção única: ramos de forma
    fechada onde o caminho aritmético é idêntico ao esperado).
    """
    if not math.isclose(actual, expected, rel_tol=rel, abs_tol=abs_):
        diff = actual - expected
        raise AssertionError(
            f"{label}: {actual!r} != {expected!r} (diff={diff:.6e}, rel_tol={rel}, abs_tol={abs_})"
        )

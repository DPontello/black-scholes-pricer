"""Família Volatilidade com a cadeia falsa (PETR4 a 30, vol 30%) e contas feitas à mão."""

from dataclasses import replace
from datetime import date
from math import log, sqrt

from options_engine.domain.analytics.volatility import VolContext, vol_context
from options_engine.domain.book.model import BookItem, BookLabel, FamilyResult
from options_engine.domain.book.presets import BookSettings
from options_engine.domain.book.volatilidade import volatility_items
from options_engine.domain.model.chain import OptionChain, PriceQuality
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side
from options_engine.domain.model.templates import Family
from tests._tolerances import ABS_MATH_IDENTITY_FLOOR, REL_MATH_IDENTITY, assert_close
from tests.application._mercado_falso import NOVEMBRO, cadeia, serie
from tests.book._cadeias import DEZEMBRO, MODERADO, cadeia_larga, du, series_do_vencimento

DIAS = {NOVEMBRO: du(NOVEMBRO), DEZEMBRO: du(DEZEMBRO)}
ALTA = vol_context("PETR4", 0.40, 0.25, [])
BAIXA = vol_context("PETR4", 0.20, 0.35, [])
NEUTRA = vol_context("PETR4", 0.30, 0.30, [])
# O spread das séries baratas da cadeia falsa passa de 20%: o filtro fica largo nos testes de conta.
LARGO = replace(MODERADO, max_spread_pct=1.5)


def _perto(atual: float, esperado: float) -> None:
    assert_close(atual, esperado, rel=REL_MATH_IDENTITY, abs_=ABS_MATH_IDENTITY_FLOOR)


def _rodar(
    contexto: VolContext,
    settings: BookSettings = LARGO,
    chain: OptionChain | None = None,
) -> FamilyResult:
    return volatility_items(chain or cadeia_larga(), contexto, settings, DIAS)


def _chaves(itens: tuple[BookItem, ...]) -> set[str]:
    return {i.template_key for i in itens}


def _simbolos(item: BookItem) -> tuple[str, ...]:
    return tuple(leg.symbol for leg in item.legs)


def test_vol_alta_lista_so_as_vendas_e_baixa_so_as_compras() -> None:
    assert _chaves(_rodar(ALTA).items) == {"iron_condor_vendido", "borboleta_comprada"}
    assert _chaves(_rodar(BAIXA).items) == {"straddle_comprado", "strangle_comprado"}


def test_vol_neutra_lista_as_duas_rotuladas_sem_sinal_claro() -> None:
    itens = _rodar(NEUTRA).items
    assert _chaves(itens) == {
        "iron_condor_vendido",
        "borboleta_comprada",
        "straddle_comprado",
        "strangle_comprado",
    }
    assert all(BookLabel.SEM_SINAL_CLARO in i.labels for i in itens)
    assert all(i.family is Family.VOLATILIDADE for i in itens)


def test_iron_condor_contra_a_conta_a_mao() -> None:
    """Bruto, sem custos nem IR: crédito c = bid W280 + bid K320 - ask W260 - ask K340 por
    ação; asas de 2, risco = (2 - c) x 100; breakevens 28 - c e 32 + c, em desvios: |ln(BE/30)| /
    (0,40 x sqrt(du / 252))."""
    chain = cadeia_larga()
    q = {quote.contract.symbol: quote for quote in chain.quotes}
    c = q["PETRW280"].bid + q["PETRK320"].bid - q["PETRW260"].ask - q["PETRK340"].ask  # type: ignore[operator]

    resultado = _rodar(ALTA, chain=chain)
    condor = next(
        i
        for i in resultado.items
        if _simbolos(i) == ("PETRW260", "PETRW280", "PETRK320", "PETRK340")
    )

    numeros = {m.key: m.value for m in condor.metrics}
    _perto(numeros["credito"], 100 * c)
    _perto(numeros["ganho"], 100 * c)
    _perto(numeros["risco"], 100 * (2 - c))
    assert condor.criterion.key == "ganho_risco"
    _perto(condor.criterion.value, c / (2 - c))
    desvio = 0.40 * sqrt(DIAS[NOVEMBRO] / 252)
    _perto(numeros["be_baixo"], abs(log((28 - c) / 30)) / desvio)
    _perto(numeros["be_alto"], abs(log((32 + c) / 30)) / desvio)
    assert 0.0 < numeros["prob_lucro"] < 1.0
    assert (numeros["iv30"], numeros["hv21"]) == (0.40, 0.25)
    assert [(leg.side, leg.quantity) for leg in condor.legs] == [
        (Side.BUY, 100),
        (Side.SELL, 100),
        (Side.SELL, 100),
        (Side.BUY, 100),
    ]
    texto = condor.render_reason(lambda m: f"<{m.key}>")
    assert texto.startswith("IV 30 de <iv30> e HV 21 de <hv21>, sem IV rank: o iron condor")
    assert "(ganho/risco <ganho_risco>)" in texto


def test_iv_rank_abre_o_porque_quando_existe() -> None:
    com_rank = vol_context("PETR4", 0.40, 0.25, [0.20 + i / 1000 for i in range(100)])
    item = _rodar(com_rank).items[0]
    assert item.render_reason(lambda m: f"<{m.key}>").startswith(
        "IV rank <iv_rank>, IV 30 de <iv30> e HV 21 de <hv21>: "
    )


def test_borboleta_tem_o_miolo_no_dinheiro_com_asas_a_um_e_dois_strikes() -> None:
    borboletas = [i for i in _rodar(ALTA).items if i.template_key == "borboleta_comprada"]
    assert {(_simbolos(i), tuple(leg.quantity for leg in i.legs)) for i in borboletas} >= {
        (("PETRK280", "PETRK300", "PETRK320"), (100, 200, 100)),
        (("PETRK260", "PETRK300", "PETRK340"), (100, 200, 100)),
    }
    valores = [i.criterion.value for i in borboletas]
    assert valores == sorted(valores, reverse=True)


def test_strangle_vendido_so_com_perda_ilimitada_liberada_e_rotulado() -> None:
    assert "strangle_vendido" not in _chaves(_rodar(ALTA).items)
    liberado = _rodar(ALTA, replace(LARGO, allow_unlimited_loss=True)).items
    strangles = [i for i in liberado if i.template_key == "strangle_vendido"]
    assert strangles
    assert all(BookLabel.PERDA_ILIMITADA in i.labels for i in strangles)
    assert all(i.criterion.key == "dist_be" for i in strangles)


def test_compras_de_vol_do_menor_movimento_ao_maior() -> None:
    itens = _rodar(BAIXA).items
    straddles = [i for i in itens if i.template_key == "straddle_comprado"]
    assert {_simbolos(i) for i in straddles} == {
        ("PETRK300", "PETRW300"),
        ("PETRL300", "PETRX300"),
    }
    valores = [i.criterion.value for i in straddles]
    assert valores == sorted(valores)
    custo = {m.key: m.value for m in straddles[0].metrics}
    _perto(custo["custo_pct"], custo["debito"] / 3000.0)


def test_perna_sem_book_vai_para_as_referencias() -> None:
    sem_book = serie("PETRK340", 34.0, book=False)
    resultado = _rodar(ALTA, chain=cadeia_larga(sem_book))
    assert not any("PETRK340" in _simbolos(i) for i in resultado.items)
    assert any("PETRK340" in _simbolos(i) for i in resultado.references)
    assert all(i.quality is not PriceQuality.EXECUTAVEL for i in resultado.references)


def test_risco_acima_do_maximo_e_liquidez_ficam_fora_sem_exclusao() -> None:
    # A menor perda máxima bruta da cadeia falsa: R$ 48 na borboleta 28/30/32 de dezembro.
    assert _rodar(ALTA, replace(LARGO, max_risk=40.0)).items == ()
    assert _rodar(BAIXA, replace(LARGO, max_risk=40.0)).items == ()
    assert _rodar(BAIXA, replace(LARGO, min_trades=13)).items == ()
    apertado = _rodar(ALTA, replace(LARGO, max_spread_pct=0.01))
    assert apertado.items == ()
    assert not any("spread" in e.reason for e in apertado.exclusions)


def test_dado_ruim_vira_exclusao_com_motivo() -> None:
    sem_preco = serie("PETRW260", 26.0, OptionType.PUT, book=False, last=None)
    put_americana = serie("PETRW300", 30.0, OptionType.PUT, estilo=ExerciseStyle.AMERICAN)
    fora_do_smile = serie("PETRK420", 42.0, book=False, last=None, trades=0)
    chain = cadeia_larga(sem_preco, put_americana, fora_do_smile)

    motivos = {e.symbol: e.reason for e in _rodar(ALTA, chain=chain).exclusions}

    assert (
        motivos["PETRW260/PETRW280/PETRK320/PETRK340"]
        == "perna sem preço: PETRW260 sem ask para comprar"
    )
    assert motivos["PETRW300"] == "put americana não suportada (ADR-0002)"
    assert motivos["PETRK420"].startswith("sem delta")
    assert motivos["PETRL340/?"].startswith("sem strike")


def test_sem_calls_nao_ha_borboleta_nem_straddle() -> None:
    so_puts = cadeia(
        [q for q in series_do_vencimento() if q.contract.terms.option_type.is_call is False]
    )
    assert _rodar(NEUTRA, chain=so_puts).items == ()


def test_vencimento_sem_dias_uteis_informados_fica_fora() -> None:
    resultado = volatility_items(cadeia_larga(), ALTA, LARGO, {NOVEMBRO: DIAS[NOVEMBRO]})
    assert {i.expiry for i in resultado.items} == {NOVEMBRO}
    hoje = volatility_items(cadeia_larga(), ALTA, LARGO, {NOVEMBRO: 0, date(2026, 12, 18): 0})
    assert hoje.items == ()


def test_regime_pela_hv_e_iv_extrapolada_sao_rotulados() -> None:
    extrapolada = vol_context("PETR4", 0.40, 0.25, [], extrapolated=True)
    item = _rodar(extrapolada).items[0]
    assert {BookLabel.REGIME_PELA_HV, BookLabel.IV_EXTRAPOLADA} <= set(item.labels)


def test_vendidas_no_mesmo_strike_nao_formam_condor_nem_strangle() -> None:
    no_dinheiro = replace(LARGO, delta_min=0.40, delta_max=0.60, allow_unlimited_loss=True)
    so_novembro = cadeia(series_do_vencimento(strikes=(28.0, 30.0, 32.0)))
    for contexto in (ALTA, BAIXA):
        itens = _rodar(contexto, no_dinheiro, chain=so_novembro).items
        strangles = [i for i in itens if i.template_key.startswith("strangle")]
        assert all(i.legs[0].strike < i.legs[1].strike for i in strangles)
        assert "iron_condor_vendido" not in _chaves(itens)


def test_borboleta_sem_asa_de_dois_strikes_fica_so_com_a_de_um() -> None:
    itens = _rodar(ALTA, chain=cadeia(series_do_vencimento(strikes=(28.0, 30.0, 32.0)))).items
    borboletas = [_simbolos(i) for i in itens if i.template_key == "borboleta_comprada"]
    assert borboletas == [("PETRK280", "PETRK300", "PETRK320")]


def test_book_de_um_lado_so_nao_mede_spread_e_fica_fora() -> None:
    so_bid = replace(serie("PETRK320", 32.0), ask=None)
    itens = _rodar(ALTA, chain=cadeia_larga(so_bid)).items
    assert not any("PETRK320" in _simbolos(i) for i in itens)

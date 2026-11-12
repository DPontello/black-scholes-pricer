"""Família Direcionais, sem visão (opções baratas pela vol) e com visão (alvo informado)."""

from dataclasses import replace
from datetime import date

import pytest

from options_engine.domain.analytics.volatility import VolContext, vol_context
from options_engine.domain.book.direcionais import (
    Direction,
    DirectionalView,
    cheap_options,
    directional_items,
)
from options_engine.domain.book.model import BookItem, BookLabel, FamilyResult
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.enums import OptionType, Side
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.templates import Family
from tests._tolerances import ABS_MATH_IDENTITY_FLOOR, REL_MATH_IDENTITY, assert_close
from tests.application._mercado_falso import NOVEMBRO, serie
from tests.book._cadeias import DEZEMBRO, MODERADO, cadeia_larga, du

DIAS = {NOVEMBRO: du(NOVEMBRO), DEZEMBRO: du(DEZEMBRO)}
LARGO = replace(MODERADO, max_spread_pct=1.5)
# IV 30 de 30% abaixo de todo o histórico (31% a 40%): rank 0.
VOL_BARATA = vol_context("PETR4", 0.30, 0.40, [0.31 + i / 1000 for i in range(100)])
ALTA_33 = DirectionalView("PETR4", Direction.ALTA, 33.0, NOVEMBRO)


def _perto(atual: float, esperado: float) -> None:
    assert_close(atual, esperado, rel=REL_MATH_IDENTITY, abs_=ABS_MATH_IDENTITY_FLOOR)


def _baratas(contexto: VolContext, chain: OptionChain | None = None) -> FamilyResult:
    return cheap_options(chain or cadeia_larga(), contexto, LARGO, DIAS)


def _visao(
    view: DirectionalView = ALTA_33, chain: OptionChain | None = None, **campos: object
) -> FamilyResult:
    return directional_items(
        chain or cadeia_larga(),
        view,
        campos.get("settings", LARGO),  # type: ignore[arg-type]  # justificativa: kwargs de teste
        DIAS,
    )


def _simbolos(item: BookItem) -> tuple[str, ...]:
    return tuple(leg.symbol for leg in item.legs)


def _por_simbolos(itens: tuple[BookItem, ...]) -> dict[tuple[str, ...], BookItem]:
    return {_simbolos(i): i for i in itens}


# --- sem visão ----------------------------------------------------------------------------------


def test_sem_visao_lista_as_series_com_iv_abaixo_da_hv_rotuladas_nao_direcionais() -> None:
    itens = _baratas(VOL_BARATA).items
    assert {_simbolos(i) for i in itens} >= {("PETRK300",), ("PETRW300",)}
    for item in itens:
        numeros = {m.key: m.value for m in item.metrics}
        assert item.family is Family.DIRECIONAIS
        assert item.labels == (BookLabel.NAO_DIRECIONAL,)
        assert 0.30 <= abs(numeros["delta"]) <= 0.60
        assert numeros["iv_serie"] < numeros["hv21"] == 0.40
        _perto(item.criterion.value, (0.40 - numeros["iv_serie"]) / 0.40)
        assert [leg.side for leg in item.legs] == [Side.BUY]
    assert ("PETRK320",) not in {_simbolos(i) for i in itens}  # delta 0,26


def test_sem_visao_vazio_com_iv_acima_da_hv_ou_rank_alto_ou_sem_rank() -> None:
    iv_cara = vol_context("PETR4", 0.30, 0.25, [0.31 + i / 1000 for i in range(100)])
    rank_alto = vol_context("PETR4", 0.30, 0.40, [0.25 + i / 1000 for i in range(100)])
    sem_rank = vol_context("PETR4", 0.30, 0.40, [])
    assert _baratas(iv_cara).items == ()
    assert _baratas(rank_alto).items == ()
    assert _baratas(sem_rank).items == ()


def test_sem_visao_respeita_o_risco_maximo() -> None:
    resultado = cheap_options(cadeia_larga(), VOL_BARATA, replace(LARGO, max_risk=1.0), DIAS)
    assert resultado.items == ()


# --- com visão ----------------------------------------------------------------------------------


def test_visao_de_alta_ordena_call_e_trava_pelo_resultado_no_alvo_sobre_o_risco() -> None:
    """Bruto, sem custos nem IR, alvo 33: a call 30 custa d = ask x 100 e dá 300 - d; a trava
    30/34 custa (ask 30 - bid 34) x 100 e dá 300 - débito; o critério é o resultado sobre o
    débito."""
    chain = cadeia_larga()
    q = {quote.contract.symbol: quote for quote in chain.quotes}
    itens = _por_simbolos(_visao(chain=chain).items)

    call = itens[("PETRK300",)]
    debito_call = 100 * q["PETRK300"].ask  # type: ignore[operator]
    assert call.template_key == "compra_call"
    _perto(call.criterion.value, (300 - debito_call) / debito_call)

    trava = itens[("PETRK300", "PETRK340")]
    debito_trava = 100 * (q["PETRK300"].ask - q["PETRK340"].bid)  # type: ignore[operator]
    assert trava.template_key == "trava_alta_call"
    assert [leg.side for leg in trava.legs] == [Side.BUY, Side.SELL]
    _perto(trava.criterion.value, (300 - debito_trava) / debito_trava)
    numeros = {m.key: m.value for m in trava.metrics}
    _perto(numeros["resultado_alvo"], 300 - debito_trava)
    _perto(numeros["risco"], debito_trava)
    _perto(numeros["breakeven"], 30 + debito_trava / 100)
    assert 0.0 < numeros["prob_alvo"] < 0.5
    assert set(itens) == {
        ("PETRK300",),
        ("PETRK320",),
        ("PETRK300", "PETRK340"),
        ("PETRK320", "PETRK340"),
    }


def test_visao_de_alta_ordena_do_maior_para_o_menor_por_estrutura() -> None:
    itens = _visao().items
    for chave in ("compra_call", "trava_alta_call"):
        valores = [i.criterion.value for i in itens if i.template_key == chave]
        assert valores == sorted(valores, reverse=True)


def test_visao_de_baixa_usa_puts_e_a_trava_de_baixa() -> None:
    itens = _por_simbolos(_visao(DirectionalView("PETR4", Direction.BAIXA, 27.0, NOVEMBRO)).items)
    assert set(itens) == {
        ("PETRW300",),
        ("PETRW280",),
        ("PETRW260", "PETRW300"),
        ("PETRW260", "PETRW280"),
    }
    trava = itens[("PETRW260", "PETRW280")]
    assert trava.template_key == "trava_baixa_put"
    assert [(leg.option_type, leg.side) for leg in trava.legs] == [
        (OptionType.PUT, Side.SELL),
        (OptionType.PUT, Side.BUY),
    ]
    assert "Visão de baixa" in trava.render_reason(lambda m: f"<{m.key}>")


def test_alvo_do_lado_errado_do_spot_e_recusado_com_o_motivo() -> None:
    with pytest.raises(InvalidDomainValueError, match="acima do spot 30"):
        _visao(DirectionalView("PETR4", Direction.ALTA, 29.0, NOVEMBRO))
    with pytest.raises(InvalidDomainValueError, match="abaixo do spot 30"):
        _visao(DirectionalView("PETR4", Direction.BAIXA, 30.0, NOVEMBRO))


def test_vencimento_sem_series_e_recusado() -> None:
    with pytest.raises(InvalidDomainValueError, match="2027-01-15"):
        _visao(DirectionalView("PETR4", Direction.ALTA, 33.0, date(2027, 1, 15)))


def test_perna_sem_preco_vira_exclusao_e_risco_alto_fica_fora() -> None:
    sem_preco = serie("PETRK340", 34.0, book=False, last=None)
    resultado = _visao(chain=cadeia_larga(sem_preco))
    assert ("PETRK300", "PETRK340") not in _por_simbolos(resultado.items)
    assert any(e.symbol == "PETRK300/PETRK340" for e in resultado.exclusions)
    assert _visao(settings=replace(LARGO, max_risk=1.0)).items == ()


def test_visao_invalida() -> None:
    with pytest.raises(InvalidDomainValueError):
        DirectionalView(" ", Direction.ALTA, 33.0, NOVEMBRO)
    with pytest.raises(InvalidDomainValueError):
        DirectionalView("PETR4", Direction.ALTA, 0.0, NOVEMBRO)

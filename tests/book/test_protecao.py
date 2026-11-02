"""Família Proteção: put protetora e collar, pelo custo mensal equivalente contra contas à mão."""

from dataclasses import replace

import pytest

from options_engine.domain.book.model import BookItem, BookLabel, BookStock, FamilyResult
from options_engine.domain.book.presets import BookPreset, BookSettings
from options_engine.domain.book.protecao import ProtectedPosition, protection_items
from options_engine.domain.income.costs import CostSchedule
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.templates import Family
from tests._tolerances import ABS_MATH_IDENTITY_FLOOR, REL_MATH_IDENTITY, assert_close
from tests.application._mercado_falso import NOVEMBRO, serie
from tests.book._cadeias import DEZEMBRO, MODERADO, TABELA, cadeia_larga, du
from tests.income._builders import zero_cost_schedule

DIAS = {NOVEMBRO: du(NOVEMBRO), DEZEMBRO: du(DEZEMBRO)}
LARGO = replace(MODERADO, max_spread_pct=1.5)
HIPOTETICA = ProtectedPosition("PETR4", 100, None, hypothetical=True)


def _perto(atual: float, esperado: float) -> None:
    assert_close(atual, esperado, rel=REL_MATH_IDENTITY, abs_=ABS_MATH_IDENTITY_FLOOR)


def _rodar(
    posicao: ProtectedPosition = HIPOTETICA,
    settings: BookSettings = LARGO,
    tabela: CostSchedule = TABELA,
    chain: OptionChain | None = None,
) -> FamilyResult:
    return protection_items(chain or cadeia_larga(), posicao, settings, tabela, DIAS)


def _por_simbolos(itens: tuple[BookItem, ...]) -> dict[tuple[str, ...], BookItem]:
    return {tuple(leg.symbol for leg in i.legs): i for i in itens}


def test_put_protetora_pelo_custo_mensal_contra_a_conta_a_mao() -> None:
    """Sem custos: a put 28 custa ask x 100; mensal = custo / (30 x 100) x 21 / du."""
    chain = cadeia_larga()
    ask = next(q.ask for q in chain.quotes if q.contract.symbol == "PETRW280")
    assert ask is not None

    put = _por_simbolos(_rodar(tabela=zero_cost_schedule(), chain=chain).items)[("PETRW280",)]

    assert (put.family, put.template_key) == (Family.PROTECAO, "put_protetora")
    assert put.stock == BookStock(Side.BUY, 100, StockOrigin.COMPRA)
    assert put.labels == (BookLabel.POSICAO_HIPOTETICA,)
    _perto(put.criterion.value, 100 * ask / 3000 * 21 / DIAS[NOVEMBRO])
    numeros = {m.key: m.value for m in put.metrics}
    _perto(numeros["custo"], 100 * ask)
    _perto(numeros["custo_pct"], 100 * ask / 3000)
    assert (numeros["piso"], numeros["piso_pct"]) == (28.0, 28.0 / 30.0)
    assert put.render_reason(lambda m: f"<{m.key}>").startswith(
        "100 ações hipotéticas: a put PETRW280 garante o piso de <piso>"
    )


def test_collar_de_credito_vem_antes_e_tem_o_teto() -> None:
    """Sem custos: collar 28/32 custa (ask put 28 - bid call 32) x 100, negativo = crédito."""
    chain = cadeia_larga()
    q = {quote.contract.symbol: quote for quote in chain.quotes}
    custo = 100 * (q["PETRW280"].ask - q["PETRK320"].bid)  # type: ignore[operator]
    assert custo < 0

    resultado = _rodar(tabela=zero_cost_schedule(), chain=chain)

    collar = _por_simbolos(resultado.items)[("PETRW280", "PETRK320")]
    assert collar.template_key == "collar"
    assert [(leg.option_type, leg.side) for leg in collar.legs] == [
        (OptionType.PUT, Side.BUY),
        (OptionType.CALL, Side.SELL),
    ]
    _perto(collar.criterion.value, custo / 3000 * 21 / DIAS[NOVEMBRO])
    numeros = {m.key: m.value for m in collar.metrics}
    assert (numeros["teto"], numeros["teto_pct"]) == (32.0, 32.0 / 30.0)
    collars = [i.criterion.value for i in resultado.items if i.template_key == "collar"]
    assert collars == sorted(collars)
    assert collars[0] < 0


def test_piso_abaixo_do_preset_fica_fora() -> None:
    conservador = replace(
        BookSettings.default(BookPreset.CONSERVADOR), max_spread_pct=1.5, min_trades=0
    )
    puts = {
        i.legs[0].strike
        for i in _rodar(settings=conservador).items
        if i.template_key == "put_protetora"
    }
    assert puts == {30.0}
    assert {i.legs[0].strike for i in _rodar().items if i.template_key == "put_protetora"} == {
        28.0,
        30.0,
    }


def test_posicao_da_carteira_usa_o_lote_inteiro_e_nao_e_rotulada() -> None:
    carteira = ProtectedPosition("PETR4", 250, 25.0, hypothetical=False)
    item = _rodar(carteira).items[0]
    assert item.stock == BookStock(Side.BUY, 200, StockOrigin.CARTEIRA)
    assert [leg.quantity for leg in item.legs] == [200] * len(item.legs)
    assert BookLabel.POSICAO_HIPOTETICA not in item.labels
    assert item.render_reason(lambda m: "x").startswith("As 200 ações da carteira")


def test_posicao_menor_que_um_lote_vira_exclusao() -> None:
    resultado = _rodar(ProtectedPosition("PETR4", 50, 25.0, hypothetical=False))
    assert resultado.items == ()
    assert resultado.exclusions[0].symbol == "PETR4"
    assert "menor que um lote" in resultado.exclusions[0].reason


def test_perna_sem_preco_vira_exclusao() -> None:
    sem_preco = serie("PETRW280", 28.0, OptionType.PUT, book=False, last=None)
    resultado = _rodar(chain=cadeia_larga(sem_preco))
    assert ("PETRW280",) not in _por_simbolos(resultado.items)
    assert any(e.symbol == "PETRW280" for e in resultado.exclusions)


def test_posicao_invalida() -> None:
    with pytest.raises(InvalidDomainValueError):
        ProtectedPosition("PETR4", 0, None, hypothetical=True)
    with pytest.raises(InvalidDomainValueError):
        ProtectedPosition("PETR4", 100, 0.0, hypothetical=False)

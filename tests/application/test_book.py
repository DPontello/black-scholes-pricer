"""``BookService`` sobre a cadeia falsa de fim de dia (PETR4 e VALE3 a 30, vol 30%)."""

from dataclasses import replace
from datetime import date

import pytest

from options_engine.adapters.outbound.b3_calendar import B3_UTC_OFFSET
from options_engine.application.ports.book import BookUseCase, BookView
from options_engine.application.use_cases.book import BookService
from options_engine.application.use_cases.strategy_builder import StrategyBuilderService
from options_engine.domain.analytics.volatility import DailyVol, VolRegime
from options_engine.domain.book.direcionais import Direction, DirectionalView
from options_engine.domain.book.presets import BookPreset, BookSettings
from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError
from options_engine.domain.model.quotes import DataSource
from options_engine.domain.model.templates import Family
from options_engine.domain.portfolio.positions import AssetTotal
from tests.application._book_falso import MercadoDoBook, mercado_do_book, servico_do_book
from tests.application._mercado_falso import CALENDARIO, NOVEMBRO, PREGAO
from tests.book._cadeias import MODERADO, TABELA, cadeia_larga

LARGO = replace(MODERADO, max_spread_pct=1.5)


def _servico(**campos: object) -> BookService:
    return servico_do_book(**campos)  # type: ignore[arg-type]  # justificativa: kwargs de teste


def _book(settings: BookSettings = LARGO, *ativos: str, **campos: object) -> BookView:
    return _servico(**campos).book(settings, ativos or ("PETR4", "VALE3"))


def test_cumpre_o_protocolo() -> None:
    assert isinstance(_servico(), BookUseCase)


def test_book_de_dois_ativos_com_as_quatro_familias_do_fim_de_dia() -> None:
    book = _book()

    assert (book.source, book.session) == (DataSource.FIM_DE_DIA, PREGAO)
    assert set(book.families) == set(Family)
    for familia in Family:
        assert book.families[familia].items, familia
    ativos = {e.item.underlying for f in book.families.values() for e in f.items}
    assert ativos == {"PETR4", "VALE3"}
    assert [c.symbol for c in book.contexts] == ["PETR4", "VALE3"]
    contexto = book.contexts[0].context
    assert contexto is not None and contexto.regime is VolRegime.BAIXA
    assert book.unavailable == ()


def test_cinco_melhores_por_estrutura_entre_os_ativos() -> None:
    renda = _book().families[Family.RENDA].items
    for chave in {e.item.template_key for e in renda}:
        assert len([e for e in renda if e.item.template_key == chave]) <= 5


def test_ativo_sem_cadeia_fica_indisponivel_com_o_motivo_e_os_outros_seguem() -> None:
    book = _book(LARGO, "PETR4", "ITUB4")
    assert [(e.symbol, e.reason) for e in book.unavailable] == [
        ("ITUB4", "ITUB4: sem fechamento no COTAHIST")
    ]
    assert book.families[Family.RENDA].items


def test_sem_nenhuma_cadeia_o_book_vem_vazio_sem_pregao() -> None:
    book = _book(LARGO, "ITUB4")
    assert book.session is None
    assert all(not f.items for f in book.families.values())


def test_sem_historico_volatilidade_e_direcionais_dizem_por_que() -> None:
    book = _book(historicos={})
    assert book.contexts[0].context is None
    assert book.contexts[0].reason == "PETR4: sem histórico"
    for familia in (Family.VOLATILIDADE, Family.DIRECIONAIS):
        assert not book.families[familia].items
        assert ("PETR4", "PETR4: sem histórico") in {
            (e.symbol, e.reason) for e in book.families[familia].exclusions
        }
    assert book.families[Family.RENDA].items
    assert book.families[Family.PROTECAO].items


def test_historico_sem_iv_hoje_tambem_vira_motivo() -> None:
    sem_iv = (DailyVol(PREGAO, 30.0, None, False, 0.30),)
    book = _book(LARGO, "PETR4", historicos={"PETR4": sem_iv})
    assert book.contexts[0].reason is not None
    assert "sem IV 30" in book.contexts[0].reason


def test_o_pedido_de_cada_item_abre_no_montador() -> None:
    mercado = mercado_do_book()
    book = _servico(mercado=mercado).book(LARGO, ("PETR4", "VALE3"))
    montador = StrategyBuilderService(
        mercado, CALENDARIO, B3_UTC_OFFSET, schedules=[TABELA], lots=lambda _: None
    )
    for familia in Family:
        entrada = book.families[familia].items[0]
        analise = montador.analyze(entrada.request)
        assert entrada.request.template == entrada.item.template_key
        assert [leg.symbol for leg in analise.legs] == [leg.symbol for leg in entrada.item.legs]
        assert all(leg.price is not None for leg in analise.legs)


def test_preset_conservador_muda_o_book() -> None:
    conservador = replace(BookSettings.default(BookPreset.CONSERVADOR), min_trades=0)
    padrao, apertado = _book(), _book(conservador)
    assert {e.item.legs for e in padrao.families[Family.RENDA].items} != {
        e.item.legs for e in apertado.families[Family.RENDA].items
    }


def test_protecao_usa_as_acoes_compradas_da_carteira() -> None:
    carteira = (
        AssetTotal("PETR4", Side.BUY, 300, 28.0),
        AssetTotal("VALE3", Side.SELL, 100, 30.0),
    )
    book = _book(carteira=carteira)
    protecao = book.families[Family.PROTECAO].items
    petr = [e for e in protecao if e.item.underlying == "PETR4"]
    vale = [e for e in protecao if e.item.underlying == "VALE3"]
    assert petr and all(e.request.stock is not None for e in petr)
    assert {(e.request.stock.origin, e.request.stock.quantity) for e in petr} == {  # type: ignore[union-attr]
        (StockOrigin.CARTEIRA, 300)
    }
    assert {e.request.stock.origin for e in vale} == {StockOrigin.COMPRA}  # type: ignore[union-attr]


def test_direcionais_com_visao_pelo_servico() -> None:
    visao = DirectionalView("PETR4", Direction.ALTA, 33.0, NOVEMBRO)
    resultado = _servico().directional(LARGO, visao)
    assert {e.item.template_key for e in resultado.items} == {"compra_call", "trava_alta_call"}
    assert all(e.request.legs[0].side is Side.BUY for e in resultado.items)
    with pytest.raises(InvalidDomainValueError, match="acima do spot"):
        _servico().directional(LARGO, replace(visao, target=29.0))


def test_vencimento_vencido_ou_fora_do_calendario_fica_fora_sem_derrubar_o_book() -> None:
    base = cadeia_larga()
    modelo = base.quotes[0]

    def com_vencimento(simbolo: str, dia: date) -> OptionQuote:
        termos = replace(modelo.contract.terms, expiry=dia)
        return replace(modelo, contract=replace(modelo.contract, symbol=simbolo, terms=termos))

    extras = (
        com_vencimento("PETRA300", date(2028, 1, 21)),
        com_vencimento("PETRJ300", date(2026, 10, 16)),
    )
    mercado = MercadoDoBook(chains={"PETR4": replace(base, quotes=(*base.quotes, *extras))})
    book = _servico(mercado=mercado).book(LARGO, ("PETR4",))
    vencimentos = {e.item.expiry for f in book.families.values() for e in f.items}
    assert vencimentos and vencimentos <= {NOVEMBRO, date(2026, 12, 18)}

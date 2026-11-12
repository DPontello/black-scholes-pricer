"""Pó no vencimento pelo fechamento do ativo, consolidado por ativo e ações livres."""

import pytest

from options_engine.domain.model.enums import OptionType, Side, StockOrigin
from options_engine.domain.portfolio.expiry import ExpiryOutcome, expiry_outcome
from options_engine.domain.portfolio.model import Open
from options_engine.domain.portfolio.positions import AssetTotal, consolidate, free_shares
from tests.portfolio._builders import D1, D2, acao, call, operacao, put

_V, _C = Side.SELL, Side.BUY


@pytest.mark.parametrize(
    ("tipo", "fechamento", "esperado"),
    [
        (OptionType.CALL, 31.99, ExpiryOutcome.PO),
        (OptionType.CALL, 32.0, ExpiryOutcome.REGISTRAR_EXERCICIO),
        (OptionType.CALL, 35.0, ExpiryOutcome.REGISTRAR_EXERCICIO),
        (OptionType.PUT, 32.01, ExpiryOutcome.PO),
        (OptionType.PUT, 32.0, ExpiryOutcome.REGISTRAR_EXERCICIO),
        (OptionType.PUT, 30.0, ExpiryOutcome.REGISTRAR_EXERCICIO),
        (OptionType.CALL, None, ExpiryOutcome.AGUARDANDO_FECHAMENTO),
        (OptionType.PUT, None, ExpiryOutcome.AGUARDANDO_FECHAMENTO),
    ],
)
def test_po_so_fora_do_dinheiro_estrito_e_com_o_fechamento(
    tipo: OptionType, fechamento: float | None, esperado: ExpiryOutcome
) -> None:
    assert expiry_outcome(tipo, 32.0, fechamento) is esperado


def test_consolidado_soma_as_operacoes_do_mesmo_ticker_pelo_preco_medio() -> None:
    a = operacao(
        [call(32.0), acao()], [Open(1, D1, _C, 100, 30.0), Open(0, D1, _V, 100, 1.00)], "a"
    )
    b = operacao(
        [call(32.0), acao()], [Open(1, D2, _C, 200, 31.5), Open(0, D2, _V, 200, 1.30)], "b"
    )
    totais = {(t.symbol, t.side): t for t in consolidate([a, b])}
    assert totais[("PETRK320", _V)].quantity == 300
    assert totais[("PETRK320", _V)].average_price == pytest.approx(1.20, abs=1e-12)
    assert totais[("PETR4", _C)] == AssetTotal("PETR4", _C, 300, pytest.approx(31.0))  # type: ignore[arg-type]


def test_acoes_livres_descontam_as_que_cobrem_call_vendida() -> None:
    a_mao = operacao([acao()], [Open(0, D1, _C, 500, 28.0)], "mao")
    coberta_propria = operacao(
        [call(32.0), acao()], [Open(1, D1, _C, 100, 30.0), Open(0, D1, _V, 100, 1.0)], "propria"
    )
    coberta_da_carteira = operacao(
        [call(33.0), acao(StockOrigin.CARTEIRA)], [Open(0, D1, _V, 200, 0.8)], "carteira"
    )
    protegida = operacao(
        [put(28.0), acao()], [Open(1, D1, _C, 100, 30.0), Open(0, D1, _C, 100, 0.5)], "put"
    )
    operacoes = [a_mao, coberta_propria, coberta_da_carteira, protegida]
    assert free_shares(operacoes, "PETR4") == 500 - 200 + 100
    assert free_shares(operacoes, "VALE3") == 0

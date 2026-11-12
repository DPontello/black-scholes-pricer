"""``RollService``: a mesma estrutura no vencimento seguinte e o caixa de zerar as atuais."""

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta, timezone

import pytest

from options_engine.application.ports.alerts import RollUseCase
from options_engine.application.ports.inbound import (
    BuilderLegInput,
    BuilderRequest,
    BuilderStockInput,
)
from options_engine.application.ports.portfolio import (
    LegMark,
    OperationView,
    PortfolioSymbols,
    PortfolioView,
)
from options_engine.application.use_cases.roll import RollService
from options_engine.domain.model.enums import Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError, UnknownRecordError
from options_engine.domain.model.quotes import DataSource
from options_engine.domain.portfolio.model import Open, Operation, OptionLegRef
from options_engine.domain.portfolio.positions import leg_states
from tests.application._mercado_falso import MercadoFalso, cadeia, serie
from tests.portfolio._builders import D1, NOVEMBRO, acao, call, operacao, put

B3 = timezone(timedelta(hours=-3))
SEMANAL = date(2026, 11, 27)
DEZEMBRO = date(2026, 12, 17)


@dataclass
class _Relogio:
    agora: datetime = datetime(2026, 11, 16, 14, 0, tzinfo=B3)

    def now(self) -> datetime:
        return self.agora


@dataclass
class _Sugestoes:
    pedidos: list[tuple[str, str, date]] = field(default_factory=list)

    def __call__(self, ativo: str, modelo: str, vencimento: date) -> BuilderRequest:
        self.pedidos.append((ativo, modelo, vencimento))
        if modelo == "venda_coberta":
            return BuilderRequest(
                ativo,
                (BuilderLegInput("PETRL320", Side.SELL, 100),),
                BuilderStockInput(Side.BUY, 100, StockOrigin.COMPRA),
                modelo,
            )
        return BuilderRequest(
            ativo,
            (
                BuilderLegInput("PETRL300", Side.BUY, 100),
                BuilderLegInput("PETRL320", Side.SELL, 100),
            ),
            None,
            modelo,
        )


def _mercado() -> MercadoFalso:
    quotes = (
        serie("PETRK300", 30.0),
        serie("PETRK300W4", 30.0, vencimento=SEMANAL),
        serie("PETRL300", 30.0, vencimento=DEZEMBRO),
    )
    return MercadoFalso(chains={"PETR4": cadeia(quotes)})


def _visao(op: Operation, precos: dict[int, float | None]) -> OperationView:
    estados = leg_states(op)
    marcas = tuple(None if e.side is None else LegMark(precos.get(e.index), None) for e in estados)
    return OperationView(op, estados, 0.0, marcas, None)


def _servico(
    *visoes: OperationView, sugestoes: _Sugestoes | None = None, mercado: MercadoFalso | None = None
) -> RollService:
    carteira = PortfolioView(visoes, (), (), DataSource.AO_VIVO, PortfolioSymbols((), ()))
    return RollService(
        lambda: carteira,
        _Sugestoes() if sugestoes is None else sugestoes,
        _Relogio(),
        B3,
        market=_mercado() if mercado is None else mercado,
    )


def _trava(quantidade: int = 100, modelo: str | None = "trava_alta_call") -> Operation:
    op = operacao(
        [call(30.0), call(32.0)],
        [Open(0, D1, Side.BUY, quantidade, 1.2), Open(1, D1, Side.SELL, quantidade, 0.6)],
        id_="trava0001",
        nome="trava de novembro",
    )
    return replace(op, template=modelo)


def test_servico_cumpre_a_porta() -> None:
    assert isinstance(_servico(), RollUseCase)


def test_rolagem_mensal_vai_ao_proximo_mensal() -> None:
    sugestoes = _Sugestoes()
    sugestao = _servico(_visao(_trava(), {0: 1.5, 1: 0.45}), sugestoes=sugestoes).roll("trava0001")
    assert (sugestao.current_expiry, sugestao.next_expiry) == (NOVEMBRO, DEZEMBRO)
    assert sugestoes.pedidos == [("PETR4", "trava_alta_call", DEZEMBRO)]
    assert (sugestao.operation_name, sugestao.underlying, sugestao.source) == (
        "trava de novembro",
        "PETR4",
        DataSource.AO_VIVO,
    )


def test_rolagem_semanal_vai_ao_proximo() -> None:
    semanal = OptionLegRef("PETRW300W3", replace(put(30.0).terms, expiry=date(2026, 11, 20)))
    op = replace(
        operacao([semanal], [Open(0, D1, Side.SELL, 100, 0.5)], id_="semanal01"),
        template="put_coberta",
    )
    sugestao = _servico(_visao(op, {0: 0.2})).roll("semanal01")
    assert sugestao.next_expiry == SEMANAL


def test_quantidades_proporcionais() -> None:
    sugestao = _servico(_visao(_trava(300), {0: 1.5, 1: 0.45})).roll("trava0001")
    assert sugestao.request is not None
    assert [(p.symbol, p.side, p.quantity) for p in sugestao.request.legs] == [
        ("PETRL300", Side.BUY, 300),
        ("PETRL320", Side.SELL, 300),
    ]


def test_acao_do_modelo_vem_da_carteira() -> None:
    coberta = replace(
        operacao(
            [call(32.0), acao()],
            [Open(0, D1, Side.SELL, 200, 0.8), Open(1, D1, Side.BUY, 200, 29.0)],
            id_="coberta01",
        ),
        template="venda_coberta",
    )
    sugestao = _servico(_visao(coberta, {0: 0.3, 1: 29.5})).roll("coberta01")
    assert sugestao.request is not None
    assert sugestao.request.stock == BuilderStockInput(Side.BUY, 200, StockOrigin.CARTEIRA)
    assert sugestao.close_cash == pytest.approx(-0.3 * 200)


def test_caixa_de_zerar() -> None:
    sugestao = _servico(_visao(_trava(), {0: 1.5, 1: 0.45})).roll("trava0001")
    # Vende a comprada no bid (recebe 150) e recompra a vendida no ask (paga 45).
    assert sugestao.close_cash == pytest.approx(150.0 - 45.0)


def test_sem_preco_de_zerar_caixa_indeterminado() -> None:
    assert _servico(_visao(_trava(), {0: 1.5, 1: None})).roll("trava0001").close_cash is None


def test_rolagem_sem_modelo() -> None:
    sugestoes = _Sugestoes()
    servico = _servico(_visao(_trava(modelo=None), {0: 1.5, 1: 0.45}), sugestoes=sugestoes)
    sugestao = servico.roll("trava0001")
    assert (sugestao.next_expiry, sugestao.request, sugestoes.pedidos) == (DEZEMBRO, None, [])


def test_modelo_fora_do_catalogo_e_como_sem_modelo() -> None:
    sugestao = _servico(_visao(_trava(modelo="sumiu"), {0: 1.5, 1: 0.45})).roll("trava0001")
    assert sugestao.request is None


def test_sem_vencimento_seguinte() -> None:
    so_novembro = MercadoFalso(chains={"PETR4": cadeia((serie("PETRK300", 30.0),))})
    sugestao = _servico(_visao(_trava(), {0: 1.5, 1: 0.45}), mercado=so_novembro).roll("trava0001")
    assert (sugestao.next_expiry, sugestao.request) == (None, None)


def test_vencimento_atual_e_o_da_vendida_mais_proxima() -> None:
    longe = OptionLegRef("PETRX280", replace(put(28.0).terms, expiry=DEZEMBRO))
    op = replace(
        operacao(
            [longe, call(32.0)],
            [Open(0, D1, Side.SELL, 100, 0.9), Open(1, D1, Side.SELL, 100, 0.6)],
            id_="duas0001",
        ),
        template="strangle_vendido",
    )
    sugestao = _servico(_visao(op, {0: 0.5, 1: 0.2})).roll("duas0001")
    assert sugestao.current_expiry == NOVEMBRO


def test_operacao_sem_vendida_recusada() -> None:
    comprada = operacao([call(30.0)], [Open(0, D1, Side.BUY, 100, 1.2)], id_="comprada1")
    with pytest.raises(InvalidDomainValueError, match="vendida"):
        _servico(_visao(comprada, {0: 1.5})).roll("comprada1")


def test_operacao_que_nao_esta_aberta() -> None:
    with pytest.raises(UnknownRecordError, match="naoexiste"):
        _servico().roll("naoexiste")

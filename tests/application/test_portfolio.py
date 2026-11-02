"""``PortfolioService``: registro, encerramento, exercício, vencimento e a pasta do perfil."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from options_engine.application.ports.outbound import UnreadableFile
from options_engine.application.ports.portfolio import (
    ExpiryNotice,
    Fill,
    PortfolioUseCase,
    RegisterOperation,
    RegisterOptionLeg,
    RegisterStock,
)
from options_engine.application.use_cases.portfolio import PortfolioService
from options_engine.domain.model.chain import OptionQuote
from options_engine.domain.model.contracts import OptionContract, OptionTerms
from options_engine.domain.model.enums import ExerciseStyle, OptionType, Side, StockOrigin
from options_engine.domain.model.errors import InvalidDomainValueError, UnknownRecordError
from options_engine.domain.model.quotes import DataSource, UnderlyingQuote
from options_engine.domain.portfolio.expiry import ExpiryOutcome
from options_engine.domain.portfolio.model import (
    Close,
    Expired,
    Open,
    Operation,
    OptionLegRef,
    TransferOut,
)
from options_engine.domain.portfolio.positions import leg_states
from tests.application._mercado_falso import CALENDARIO, INSTANTE, MercadoFalso, preco_bs
from tests.income._builders import make_cost_schedule
from tests.portfolio._builders import D1, D2, NOVEMBRO, call, put

B3 = timezone(timedelta(hours=-3))
_V, _C = Side.SELL, Side.BUY


@dataclass
class _Repositorio:
    operacoes: dict[str, Operation] = field(default_factory=dict)
    ilegiveis: tuple[UnreadableFile, ...] = ()

    def list(self) -> tuple[Operation | UnreadableFile, ...]:
        return (*self.operacoes.values(), *self.ilegiveis)

    def save(self, operation: Operation) -> None:
        self.operacoes[operation.id] = operation

    def load(self, operation_id: str) -> Operation:
        if operation_id not in self.operacoes:
            raise UnknownRecordError(operation_id)
        return self.operacoes[operation_id]


@dataclass
class _Relogio:
    agora: datetime = datetime(2026, 11, 4, 14, 0, tzinfo=B3)

    def now(self) -> datetime:
        return self.agora


def _servico(
    repositorio: _Repositorio,
    relogio: _Relogio | None = None,
    mercado: MercadoFalso | None = None,
) -> PortfolioService:
    ids = iter(f"op{i}" for i in range(1, 100))
    return PortfolioService(
        lambda: repositorio,
        relogio or _Relogio(),
        [make_cost_schedule()],
        lambda: next(ids),
        B3,
        market=MercadoFalso() if mercado is None else mercado,
        calendar=CALENDARIO,
    )


def _perna(strike: float, lado: Side, *execucoes: Fill, tipo: str = "call") -> RegisterOptionLeg:
    ref = call(strike) if tipo == "call" else put(strike)
    return RegisterOptionLeg(ref.symbol, ref.terms, lado, execucoes)


def _coberta_da_carteira(quantidade: int) -> RegisterOperation:
    return RegisterOperation(
        "PETR4",
        "coberta",
        D1,
        (_perna(32.0, _V, Fill(quantidade, 1.0, costs=0.0)),),
        RegisterStock(_C, StockOrigin.CARTEIRA),
    )


def _strangle_vendido() -> RegisterOperation:
    return RegisterOperation(
        "PETR4",
        "strangle",
        D1,
        (
            _perna(32.0, _V, Fill(100, 1.0, costs=0.0)),
            _perna(28.0, _V, Fill(100, 0.5, costs=0.0), tipo="put"),
        ),
    )


def test_cumpre_o_protocol() -> None:
    assert isinstance(_servico(_Repositorio()), PortfolioUseCase)


def test_registra_e_lista_a_operacao_aberta() -> None:
    servico = _servico(_Repositorio())
    trava = servico.register(
        RegisterOperation(
            "PETR4",
            "  trava de alta ",
            D1,
            (
                _perna(32.0, _C, Fill(100, 1.00), Fill(200, 1.30, costs=1.5)),
                _perna(34.0, _V, Fill(300, 0.40)),
            ),
        )
    )
    assert (trava.id, trava.name, trava.created_on) == ("op1", "trava de alta", D1)
    assert trava.events[1] == Open(0, D1, _C, 200, 1.30, 1.5)
    visao = servico.open_operations()
    (aberta,) = visao.operations
    assert aberta.operation == trava
    assert aberta.legs[0].average_price == pytest.approx(1.20, abs=1e-12)
    assert [(t.total.symbol, t.total.side, t.total.quantity) for t in visao.totals] == [
        ("PETRK320", _C, 300),
        ("PETRK340", _V, 300),
    ]
    assert servico.history() == ()


def test_encerrar_tudo_move_para_o_historico() -> None:
    servico = _servico(_Repositorio())
    vendida = servico.register(
        RegisterOperation("PETR4", "call", D1, (_perna(32.0, _V, Fill(100, 1.0, costs=0.0)),))
    )
    parcial = servico.close(vendida.id, 0, 40, 0.5, D2, costs=0.0)
    assert servico.open_operations().operations[0].operation == parcial
    servico.close(vendida.id, 0, 60, 0.5, D2, costs=0.0)
    assert servico.open_operations().operations == ()
    (encerrada,) = servico.history()
    assert encerrada.realized == pytest.approx(50.0, abs=1e-9)


def test_acoes_livres_insuficientes_sao_recusadas() -> None:
    servico = _servico(_Repositorio())
    servico.add_stock("PETR4", 100, 28.0, D1)
    with pytest.raises(InvalidDomainValueError, match="100 ações livres"):
        servico.register(_coberta_da_carteira(200))
    servico.register(_coberta_da_carteira(100))
    with pytest.raises(InvalidDomainValueError, match="0 ações livres"):
        servico.register(_coberta_da_carteira(100))


def test_acoes_a_mao_sao_uma_operacao_de_uma_perna_sem_custo_estimado() -> None:
    servico = _servico(_Repositorio())
    a_mao = servico.add_stock("PETR4", 300, 28.5, D1)
    assert a_mao.events == (Open(0, D1, _C, 300, 28.5, costs=0.0),)
    (visao,) = servico.open_operations().operations
    assert visao.realized == 0.0


def test_atribuicao_com_acao_da_carteira_tira_as_acoes_pelo_preco_medio_do_perfil() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio)
    primeiro = servico.add_stock("PETR4", 300, 28.0, D1)
    segundo = servico.add_stock("PETR4", 100, 32.0, D2)
    coberta = servico.register(_coberta_da_carteira(200))
    atribuida = servico.assign(coberta.id, 0, 200, NOVEMBRO, costs=0.0)
    # Venda = strike + prêmio = 33; custo = o médio das 400 ações do perfil = 29.
    assert atribuida.events[-1] == Close(1, NOVEMBRO, 200, 33.0, costs=0.0, cost_basis=29.0)
    assert leg_states(atribuida)[1].realized == 800.0
    # Saem na proporção das livres de cada operação: o médio de quem fica não muda.
    assert repositorio.operacoes[primeiro.id].events[-1] == TransferOut(
        0, NOVEMBRO, 150, coberta.id
    )
    assert repositorio.operacoes[segundo.id].events[-1] == TransferOut(0, NOVEMBRO, 50, coberta.id)
    (acoes,) = [t.total for t in servico.open_operations().totals if t.total.symbol == "PETR4"]
    assert (acoes.quantity, acoes.average_price) == (200, 29.0)


def test_sobra_da_divisao_vai_para_a_operacao_mais_antiga() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio)
    lotes = [servico.add_stock("PETR4", 100, preco, D1) for preco in (28.0, 30.0, 32.0)]
    coberta = servico.register(_coberta_da_carteira(100))
    servico.assign(coberta.id, 0, 100, NOVEMBRO, costs=0.0)
    saidas = [repositorio.operacoes[lote.id].events[-1] for lote in lotes]
    assert [s.quantity for s in saidas if isinstance(s, TransferOut)] == [34, 33, 33]


def test_atribuicao_da_carteira_sem_acoes_livres_e_recusada_sem_gravar() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio)
    a_mao = servico.add_stock("PETR4", 100, 28.0, D1)
    coberta = servico.register(_coberta_da_carteira(100))
    servico.close(a_mao.id, 0, 100, 30.0, D2, costs=0.0)
    antes = dict(repositorio.operacoes)
    with pytest.raises(InvalidDomainValueError, match="faltam 100 ações livres"):
        servico.assign(coberta.id, 0, 100, NOVEMBRO)
    assert repositorio.operacoes == antes


def test_coberta_com_a_propria_acao_nao_mexe_na_carteira() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio)
    a_mao = servico.add_stock("PETR4", 100, 28.0, D1)
    coberta = servico.register(
        RegisterOperation(
            "PETR4",
            "coberta comprando",
            D1,
            (_perna(32.0, _V, Fill(100, 1.0, costs=0.0)),),
            RegisterStock(_C, StockOrigin.COMPRA, (Fill(100, 30.0, costs=0.0),)),
        )
    )
    servico.assign(coberta.id, 0, 100, NOVEMBRO, costs=0.0)
    assert repositorio.operacoes[a_mao.id] == a_mao
    (encerrada,) = servico.history()
    assert encerrada.realized == pytest.approx(300.0, abs=1e-9)


def test_exercicio_e_atribuicao_conferem_o_lado_da_perna() -> None:
    servico = _servico(_Repositorio())
    vendida = servico.register(
        RegisterOperation("PETR4", "call", D1, (_perna(32.0, _V, Fill(100, 1.0)),))
    )
    comprada = servico.register(
        RegisterOperation("PETR4", "put", D1, (_perna(28.0, _C, Fill(100, 0.5), tipo="put"),))
    )
    with pytest.raises(InvalidDomainValueError, match="exercício só em perna comprada"):
        servico.exercise(vendida.id, 0, 100, NOVEMBRO)
    with pytest.raises(InvalidDomainValueError, match="atribuição só em perna vendida"):
        servico.assign(comprada.id, 0, 100, NOVEMBRO)
    with pytest.raises(InvalidDomainValueError, match="perna 3"):
        servico.assign(vendida.id, 3, 100, NOVEMBRO)
    exercida = servico.exercise(comprada.id, 0, 100, NOVEMBRO, costs=0.0)
    assert exercida.events[-1] == Open(1, NOVEMBRO, _V, 100, 27.5, costs=0.0)


@pytest.mark.parametrize(
    ("command", "motivo"),
    [
        (RegisterOperation("PETR4", "x", D1, (_perna(32.0, _V),)), "sem execução"),
        (
            RegisterOperation(
                "PETR4",
                "x",
                D1,
                (_perna(32.0, _V, Fill(100, 1.0)),),
                RegisterStock(_C, StockOrigin.CARTEIRA, (Fill(100, 30.0),)),
            ),
            "carteira",
        ),
        (
            RegisterOperation(
                "PETR4",
                "x",
                D1,
                (_perna(32.0, _V, Fill(100, 1.0)),),
                RegisterStock(_V, StockOrigin.CARTEIRA),
            ),
            "carteira",
        ),
        (
            RegisterOperation(
                "PETR4",
                "x",
                D1,
                (_perna(32.0, _V, Fill(100, 1.0)),),
                RegisterStock(_C, StockOrigin.COMPRA),
            ),
            "sem execução",
        ),
        (RegisterOperation("PETR4", " ", D1, (_perna(32.0, _V, Fill(100, 1.0)),)), "nome"),
    ],
)
def test_registro_invalido_e_recusado_sem_gravar(command: RegisterOperation, motivo: str) -> None:
    repositorio = _Repositorio()
    with pytest.raises(InvalidDomainValueError, match=motivo):
        _servico(repositorio).register(command)
    assert repositorio.operacoes == {}


def _fechamento(valor: float | None) -> dict[tuple[str, date], float | None]:
    return {("PETR4", NOVEMBRO): valor}


def test_po_e_gravado_uma_vez_so() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio, _Relogio(datetime(2026, 11, 19, 18, 0, tzinfo=B3)))
    strangle = servico.register(_strangle_vendido())
    fechamentos = _fechamento(30.0)
    assert servico.process_expiries(lambda ativo, dia: fechamentos.get((ativo, dia))) == ()
    vencida = repositorio.operacoes[strangle.id]
    assert vencida.events[-2:] == (Expired(0, NOVEMBRO), Expired(1, NOVEMBRO))
    assert servico.process_expiries(lambda ativo, dia: fechamentos.get((ativo, dia))) == ()
    assert repositorio.operacoes[strangle.id] == vencida
    (encerrada,) = servico.history()
    assert encerrada.realized == pytest.approx(150.0, abs=1e-9)


def test_dentro_do_dinheiro_avisa_para_registrar_e_sem_fechamento_aguarda() -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio, _Relogio(datetime(2026, 11, 20, 10, 0, tzinfo=B3)))
    strangle = servico.register(_strangle_vendido())
    assert servico.process_expiries(lambda _ativo, _dia: None) == (
        ExpiryNotice(strangle.id, 0, "PETRK320", NOVEMBRO, ExpiryOutcome.AGUARDANDO_FECHAMENTO),
        ExpiryNotice(strangle.id, 1, "PETRW280", NOVEMBRO, ExpiryOutcome.AGUARDANDO_FECHAMENTO),
    )
    assert repositorio.operacoes[strangle.id] == strangle
    fechamentos = _fechamento(33.0)
    assert servico.process_expiries(lambda ativo, dia: fechamentos.get((ativo, dia))) == (
        ExpiryNotice(strangle.id, 0, "PETRK320", NOVEMBRO, ExpiryOutcome.REGISTRAR_EXERCICIO),
    )
    assert repositorio.operacoes[strangle.id].events[-1] == Expired(1, NOVEMBRO)


@pytest.mark.parametrize(
    ("agora", "processa"),
    [
        (datetime(2026, 11, 19, 20, 59, tzinfo=UTC), False),  # 17h59 na B3
        (datetime(2026, 11, 19, 21, 0, tzinfo=UTC), True),
        (datetime(2026, 11, 18, 23, 0, tzinfo=B3), False),
    ],
)
def test_so_o_pregao_do_vencimento_ja_encerrado_conta(agora: datetime, processa: bool) -> None:
    repositorio = _Repositorio()
    servico = _servico(repositorio, _Relogio(agora))
    strangle = servico.register(_strangle_vendido())
    fechamentos = _fechamento(30.0)
    servico.process_expiries(lambda ativo, dia: fechamentos.get((ativo, dia)))
    assert (repositorio.operacoes[strangle.id] != strangle) is processa


def test_arquivos_ilegiveis_aparecem_na_carteira() -> None:
    ilegivel = UnreadableFile("operacoes/x.json", "JSON ilegível")
    servico = _servico(_Repositorio(ilegiveis=(ilegivel,)))
    assert servico.open_operations().unreadable == (ilegivel,)


def test_perfil_trocado_troca_a_pasta() -> None:
    hugo, mae = _Repositorio(), _Repositorio()
    aberto = [hugo]
    ids = iter(["a" * 32, "b" * 32])
    servico = PortfolioService(
        lambda: aberto[0],
        _Relogio(),
        [make_cost_schedule()],
        lambda: next(ids),
        B3,
        market=MercadoFalso(),
        calendar=CALENDARIO,
    )
    servico.add_stock("PETR4", 100, 28.0, D1)
    aberto[0] = mae
    assert servico.open_operations().operations == ()
    servico.add_stock("VALE3", 100, 60.0, D1)
    assert list(hugo.operacoes) == ["a" * 32] and list(mae.operacoes) == ["b" * 32]


def _cotacao(ref: OptionLegRef, bid: float | None, ask: float | None) -> OptionQuote:
    return OptionQuote(OptionContract(ref.symbol, ref.terms), bid, ask, None, 0, 0.0, INSTANTE)


def _acao(bid: float | None, ask: float | None) -> UnderlyingQuote:
    return UnderlyingQuote("PETR4", 30.0, bid, ask, 29.0, 100, 1.0e6, INSTANTE, DataSource.AO_VIVO)


def _trava(servico: PortfolioService) -> Operation:
    return servico.register(
        RegisterOperation(
            "PETR4",
            "trava de alta",
            D1,
            (_perna(30.0, _C, Fill(100, 1.20)), _perna(32.0, _V, Fill(100, 0.60))),
        )
    )


def test_marca_pelo_preco_de_zerar_bid_na_comprada_e_ask_na_vendida() -> None:
    mercado = MercadoFalso(
        option_quotes={
            "PETRK300": _cotacao(call(30.0), 1.50, 1.60),
            "PETRK320": _cotacao(call(32.0), 0.40, 0.45),
        }
    )
    servico = _servico(_Repositorio(), mercado=mercado)
    _trava(servico)
    visao = servico.open_operations()
    assert visao.source is DataSource.AO_VIVO
    (trava,) = visao.operations
    comprada, vendida = trava.marks
    assert comprada is not None and vendida is not None
    assert (comprada.price, comprada.theoretical, comprada.reason) == (1.50, None, None)
    assert comprada.unrealized == pytest.approx(30.0, abs=1e-9)
    assert vendida.price == 0.45 and vendida.unrealized == pytest.approx(15.0, abs=1e-9)
    assert trava.unrealized == pytest.approx(45.0, abs=1e-9)
    assert [t.mark.price for t in visao.totals] == [1.50, 0.45]


def test_sem_bid_a_comprada_fica_sem_preco_de_zerar_e_com_o_teorico_ao_lado() -> None:
    mercado = MercadoFalso(
        option_quotes={
            "PETRK300": _cotacao(call(30.0), None, 1.60),
            "PETRK320": _cotacao(call(32.0), 0.40, 0.45),
        }
    )
    servico = _servico(_Repositorio(), mercado=mercado)
    _trava(servico)
    (trava,) = servico.open_operations().operations
    comprada = trava.marks[0]
    assert comprada is not None
    assert (comprada.price, comprada.unrealized) == (None, None)
    assert comprada.reason == "sem oferta de compra para zerar"
    # O smile da cadeia falsa sai da vol de 30% com que as séries foram precificadas.
    assert comprada.theoretical == pytest.approx(preco_bs(30.0, OptionType.CALL), abs=0.01)
    assert trava.unrealized is None


def test_sem_cotacao_sai_o_motivo_e_sem_cadeia_nao_ha_teorico() -> None:
    mercado = MercadoFalso(chains={}, option_quotes={"PETRK320": "sem cotação ao vivo"})
    servico = _servico(_Repositorio(), mercado=mercado)
    _trava(servico)
    (trava,) = servico.open_operations().operations
    comprada, vendida = trava.marks
    assert comprada is not None and vendida is not None
    assert (comprada.reason, comprada.theoretical) == ("aguardando dados", None)
    assert (vendida.reason, vendida.theoretical) == ("sem cotação ao vivo", None)


def test_put_americana_nao_tem_teorico() -> None:
    americana = OptionLegRef(
        "PETRX280",
        OptionTerms("PETR4", 28.0, NOVEMBRO, OptionType.PUT, ExerciseStyle.AMERICAN),
    )
    mercado = MercadoFalso(option_quotes={"PETRX280": _cotacao(americana, None, None)})
    servico = _servico(_Repositorio(), mercado=mercado)
    servico.register(
        RegisterOperation(
            "PETR4",
            "put",
            D1,
            (RegisterOptionLeg(americana.symbol, americana.terms, _C, (Fill(100, 0.50),)),),
        )
    )
    (operacao,) = servico.open_operations().operations
    marca = operacao.marks[0]
    assert marca is not None and (marca.price, marca.theoretical) == (None, None)


def test_acoes_marcadas_pelo_book_do_ativo_e_fim_de_dia_rotulado() -> None:
    mercado = MercadoFalso(healths=[DataSource.FIM_DE_DIA], quotes={"PETR4": _acao(29.9, 30.0)})
    servico = _servico(_Repositorio(), mercado=mercado)
    servico.add_stock("PETR4", 100, 28.0, D1)
    visao = servico.open_operations()
    assert visao.source is DataSource.FIM_DE_DIA
    (acoes,) = visao.operations
    marca = acoes.marks[0]
    assert marca is not None and marca.price == 29.9
    assert marca.unrealized == pytest.approx(190.0, abs=1e-9)
    mercado.quotes["PETR4"] = _acao(None, 30.0)
    (sem_bid,) = servico.open_operations().operations
    assert sem_bid.marks[0] is not None and sem_bid.marks[0].theoretical is None


def test_simbolos_da_carteira_aberta_e_preco_medio_das_acoes() -> None:
    servico = _servico(_Repositorio())
    trava = _trava(servico)
    servico.add_stock("VALE3", 100, 60.0, D1)
    servico.add_stock("PETR4", 300, 28.0, D1)
    servico.add_stock("PETR4", 100, 32.0, D2)
    simbolos = servico.symbols()
    assert simbolos.underlyings == ("PETR4", "VALE3")
    assert simbolos.series == ("PETRK300", "PETRK320")
    servico.close(trava.id, 0, 100, 1.5, D2)
    assert servico.symbols().series == ("PETRK320",)
    assert servico.average_price("PETR4") == 29.0
    assert servico.average_price("ITUB4") is None

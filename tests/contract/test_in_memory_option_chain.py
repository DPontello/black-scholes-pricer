"""Fake em memória plugado na suíte de contrato do ``OptionChainPort``.

Prova que a suíte roda — e que as duas fábricas bastam — antes de existir
adapter real. Vive só em tests/: NÃO é adapter de produção. O primeiro
adapter real (COTAHIST, ADR-0006) herda a mesma suíte do mesmo jeito.

As séries de PETR4 cobrem as cinco situações de book da ADR-0004, para que
a bateria exercite lados ausentes (``None``) e presentes na mesma cadeia.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from options_engine.domain.model.chain import OptionChain, OptionQuote
from options_engine.domain.model.enums import OptionType
from options_engine.domain.model.errors import UnknownSymbolError
from tests.contract.option_chain_contract import OptionChainPortContract
from tests.domain._builders import make_contract, make_snapshot, make_terms

PREGAO = datetime(2026, 10, 23, 21, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class InMemoryOptionChainSource:
    """Cadeias pré-montadas; subjacente fora delas → ``UnknownSymbolError``.

    A busca é pelo símbolo DENTRO de cada cadeia (não por chave de dict
    paralela): chave e conteúdo não têm como divergir.
    """

    chains: tuple[OptionChain, ...]

    def get_chain(self, underlying_symbol: str) -> OptionChain:
        for chain in self.chains:
            if chain.underlying.underlying_symbol == underlying_symbol:
                return chain
        raise UnknownSymbolError(f"subjacente desconhecido no fake: {underlying_symbol!r}")


def _quote(
    symbol: str,
    underlying: str,
    strike: float,
    option_type: OptionType,
    bid: float | None,
    ask: float | None,
    last: float | None,
    trades: int,
) -> OptionQuote:
    terms = make_terms(underlying=underlying, strike=strike, option_type=option_type)
    return OptionQuote(
        contract=make_contract(symbol=symbol, terms=terms),
        bid=bid,
        ask=ask,
        last=last,
        trades=trades,
        volume=100.0 * trades,
        timestamp=PREGAO,
    )


def _cadeia_petr4() -> OptionChain:
    call, put = OptionType.CALL, OptionType.PUT
    return OptionChain(
        underlying=make_snapshot(underlying_symbol="PETR4", timestamp=PREGAO),
        quotes=(
            _quote("PETRK300", "PETR4", 30.0, call, 1.20, 1.25, 1.22, 37),  # book completo
            _quote("PETRK320", "PETR4", 32.0, call, 0.45, None, 0.47, 5),  # só bid
            _quote("PETRK340", "PETR4", 34.0, call, None, 0.18, None, 0),  # só ask
            _quote("PETRW280", "PETR4", 28.0, put, None, None, 0.62, 3),  # vazio, com negócio
            _quote("PETRW260", "PETR4", 26.0, put, None, None, None, 0),  # vazio, sem negócio
        ),
    )


def _cadeia_vale3() -> OptionChain:
    return OptionChain(
        underlying=make_snapshot(
            underlying_symbol="VALE3", spot=60.0, bid=59.95, ask=60.05, mid=60.0, timestamp=PREGAO
        ),
        quotes=(_quote("VALEK600", "VALE3", 60.0, OptionType.CALL, 2.10, 2.16, 2.12, 54),),
    )


class TestInMemoryOptionChainContract(OptionChainPortContract):
    def make_port(self) -> InMemoryOptionChainSource:
        return InMemoryOptionChainSource(chains=(_cadeia_petr4(), _cadeia_vale3()))

    def known_symbol(self) -> str:
        return "PETR4"

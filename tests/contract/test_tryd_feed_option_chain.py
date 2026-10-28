"""``TrydMarketFeed`` plugado na suíte de contrato do ``OptionChainPort``.

O quadro recebe valores sintéticos para tudo o que o feed assina; a cadeia sai do que o Tryd
"entregou", sem relação com o fim de dia.
"""

from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from options_engine.adapters.outbound.tryd.feed import TrydMarketFeed
from tests.adapters._mercado import alimentar_assinados, biblioteca, cadastro_com_objetos, montar
from tests.contract.option_chain_contract import OptionChainPortContract

_ATIVOS = {"PETR4": 30.0, "VALE3": 60.0}


def _valores(ticker: str) -> dict[str, float | int | str | None]:
    if ticker in _ATIVOS:
        spot = _ATIVOS[ticker]
        return {"ULT": spot, "OCP": spot - 0.25, "OVD": spot + 0.25, "NEG": 500, "VOL": 1e6}
    # Cada terceira série fica sem o lado da venda: o zero do Tryd tem que virar None.
    sem_venda = sum(ord(c) for c in ticker) % 3 == 0
    return {"ULT": 1.0, "OCP": 0.75, "OVD": 0.0 if sem_venda else 1.25, "NEG": 10, "VOL": 750.0}


class TestTrydMarketFeedOptionChainContract(OptionChainPortContract):
    _raiz: Path
    _biblioteca: B3FileLibrary

    @pytest.fixture(autouse=True)
    def _preparar(self, tmp_path: Path) -> None:
        self._raiz = tmp_path
        self._biblioteca = biblioteca(tmp_path / "mercado", cadastro=cadastro_com_objetos())

    def make_port(self) -> TrydMarketFeed:
        m = montar(self._raiz, lib=self._biblioteca)
        m.feed.watch(list(_ATIVOS), list(_ATIVOS))
        alimentar_assinados(m.board, m.cliente.topicos, _valores)
        return m.feed

    def known_symbols(self) -> tuple[str, ...]:
        return ("PETR4", "VALE3")

    def unavailable_symbol(self) -> str | None:
        return "ITUB4"

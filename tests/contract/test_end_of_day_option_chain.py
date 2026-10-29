"""``EndOfDayMarket`` plugado na suíte de contrato do ``OptionChainPort``."""

from pathlib import Path

import pytest

from options_engine.adapters.outbound.b3files.end_of_day import EndOfDayMarket
from options_engine.adapters.outbound.b3files.library import B3FileLibrary
from tests.adapters._mercado import CDI, biblioteca
from tests.contract.option_chain_contract import OptionChainPortContract


class TestEndOfDayOptionChainContract(OptionChainPortContract):
    _biblioteca: B3FileLibrary

    @pytest.fixture(autouse=True)
    def _preparar(self, tmp_path: Path) -> None:
        self._biblioteca = biblioteca(tmp_path / "mercado")

    def make_port(self) -> EndOfDayMarket:
        return EndOfDayMarket(self._biblioteca, lambda: CDI)

    def known_symbols(self) -> tuple[str, ...]:
        return ("PETR4", "VALE3")

    def unavailable_symbol(self) -> str | None:
        return "ITUB4"

    def test_cadeia_de_arquivo_de_fim_de_dia_e_identica_entre_consultas(self) -> None:
        """Promessa desta implementação: a biblioteca não muda entre consultas."""
        port = self.make_port()
        assert port.get_chain("PETR4") == port.get_chain("PETR4")

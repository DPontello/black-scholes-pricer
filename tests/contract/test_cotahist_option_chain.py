"""``CotahistOptionChainAdapter`` plugado na suíte de contrato do ``OptionChainPort``.

Critério de aceite da Sprint 5: ``pytest -q tests/contract`` verde com o
adapter COTAHIST sobre a fixture sintética (``tests/data/cotahist/``). Os
comportamentos específicos do adapter vivem em ``tests/adapters/cotahist/``.
"""

from pathlib import Path

from options_engine.adapters.outbound.cotahist import CotahistOptionChainAdapter
from options_engine.domain.model.conventions import Compounding, RiskFreeRate
from tests.contract.option_chain_contract import OptionChainPortContract
from tests.data.cotahist.build_fixture import COTAHIST_NAME, INSTRUMENTS_NAME, REFERENCE_SESSION

FIXTURE = Path(__file__).resolve().parents[1] / "data" / "cotahist"


class TestCotahistOptionChainContract(OptionChainPortContract):
    def make_port(self) -> CotahistOptionChainAdapter:
        return CotahistOptionChainAdapter(
            session_date=REFERENCE_SESSION,
            cotahist_paths=[FIXTURE / COTAHIST_NAME],
            instruments_path=FIXTURE / INSTRUMENTS_NAME,
            risk_free_rate=RiskFreeRate(0.15, Compounding.BUSINESS_DAILY_252),
        )

    def known_symbols(self) -> tuple[str, ...]:
        return ("PETR4", "VALE3")

    def unavailable_symbol(self) -> str | None:
        return "ITUB4"

    def test_cadeia_de_arquivo_de_fim_de_dia_e_identica_entre_consultas(self) -> None:
        """Promessa desta implementação: a fonte não muda entre consultas."""
        port = self.make_port()
        assert port.get_chain("PETR4") == port.get_chain("PETR4")

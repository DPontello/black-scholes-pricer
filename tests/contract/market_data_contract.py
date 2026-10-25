"""Suíte de contrato do ``MarketDataPort`` — escrita UMA vez, herdada por todos.

Type hints garantem forma; ESTA suíte garante comportamento (ARCH §8). Cada
adapter (mock hoje, feed B3 amanhã) herda a classe e fornece apenas as
fixtures de construção — quando o adapter real chegar, ele nasce com a
bateria de conformidade pronta.

Nada aqui é específico de GBM (risco nº 1 do ROADMAP S3: port desenhado a
partir do mock). Determinismo por seed é promessa do MOCK, não do contrato —
vive na subclasse.
"""

from abc import ABC, abstractmethod
from dataclasses import FrozenInstanceError

import pytest

from options_engine.application.ports.outbound import MarketDataPort
from options_engine.domain.model.conventions import RiskFreeRate, Volatility
from options_engine.domain.model.errors import UnknownSymbolError
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["MarketDataPortContract"]


class MarketDataPortContract(ABC):
    """Herde, implemente as duas fábricas, ganhe a bateria inteira."""

    @abstractmethod
    def make_port(self) -> MarketDataPort:
        """Uma instância NOVA do adapter, pronta para consulta."""

    @abstractmethod
    def known_symbol(self) -> str:
        """Símbolo que o adapter reconhece."""

    UNKNOWN_SYMBOL = "XXXX99"

    # --- forma -----------------------------------------------------------

    def test_satisfaz_o_protocol_em_runtime(self) -> None:
        assert isinstance(self.make_port(), MarketDataPort)

    def test_devolve_snapshot_do_simbolo_pedido(self) -> None:
        snapshot = self.make_port().get_snapshot(self.known_symbol())
        assert isinstance(snapshot, MarketSnapshot)
        assert snapshot.underlying_symbol == self.known_symbol()

    # --- coerência de valores (contrato 1 e 3 do port) --------------------

    def test_spot_e_vol_positivos(self) -> None:
        snapshot = self.make_port().get_snapshot(self.known_symbol())
        assert snapshot.spot > 0.0
        assert isinstance(snapshot.volatility, Volatility)
        assert snapshot.volatility.value > 0.0

    def test_book_ordenado(self) -> None:
        snapshot = self.make_port().get_snapshot(self.known_symbol())
        assert 0.0 <= snapshot.bid <= snapshot.mid <= snapshot.ask

    def test_taxa_sempre_como_vo_com_compounding_explicito(self) -> None:
        """Taxa como float nu é proibida em qualquer port (CONVENTIONS §3)."""
        snapshot = self.make_port().get_snapshot(self.known_symbol())
        assert isinstance(snapshot.risk_free_rate, RiskFreeRate)

    # --- tempo (contrato 2) ------------------------------------------------

    def test_timestamp_tz_aware(self) -> None:
        ts = self.make_port().get_snapshot(self.known_symbol()).timestamp
        assert ts.tzinfo is not None
        assert ts.tzinfo.utcoffset(ts) is not None

    def test_timestamps_monotonicos_nao_decrescentes(self) -> None:
        port = self.make_port()
        anteriores = port.get_snapshot(self.known_symbol()).timestamp
        for _ in range(5):
            atual = port.get_snapshot(self.known_symbol()).timestamp
            assert atual >= anteriores
            anteriores = atual

    # --- erros (contrato 4) -------------------------------------------------

    def test_simbolo_desconhecido_e_excecao_de_dominio(self) -> None:
        """``UnknownSymbolError``, nunca ``KeyError``/``None`` vazando."""
        with pytest.raises(UnknownSymbolError):
            self.make_port().get_snapshot(self.UNKNOWN_SYMBOL)

    # --- consulta, não comando (contrato 5) ----------------------------------

    def test_snapshot_devolvido_e_imutavel(self) -> None:
        snapshot = self.make_port().get_snapshot(self.known_symbol())
        with pytest.raises(FrozenInstanceError):
            snapshot.spot = 0.0  # type: ignore[misc]

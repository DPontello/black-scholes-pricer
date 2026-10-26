"""Suíte de contrato do ``OptionChainPort`` — escrita UMA vez, herdada por todos.

Mesmo molde da suíte do ``MarketDataPort`` (ARCH §8): type hints garantem
forma; ESTA suíte garante o contrato semântico da ADR-0003. Cada adapter
(COTAHIST na fase 1, intraday depois) herda a classe e fornece só as duas
fábricas — nasce com a bateria de conformidade pronta.

As verificações de book repetem de propósito invariantes que os VOs já
impõem na construção: o port é julgado pelo que ENTREGA, não pelo que o
tipo promete (um adapter que devolvesse um duck type escaparia dos VOs).

Nada aqui depende de fonte, data ou liquidez específica. Promessas de uma
implementação (ex.: cadeia idêntica em consultas repetidas de um arquivo de
fim de dia) vivem na subclasse — no intraday a cadeia muda entre consultas
e isso não viola o contrato.
"""

from abc import ABC, abstractmethod
from dataclasses import FrozenInstanceError
from math import isfinite

import pytest

from options_engine.application.ports.outbound import OptionChainPort
from options_engine.domain.model.chain import OptionChain
from options_engine.domain.model.errors import UnknownSymbolError

__all__ = ["OptionChainPortContract"]


class OptionChainPortContract(ABC):
    """Herde, implemente as duas fábricas, ganhe a bateria inteira.

    ``known_symbol`` precisa ter ao menos uma série na fonte configurada:
    contra uma cadeia vazia as verificações por cotação passariam no vazio
    (há um teste que trava isso).
    """

    @abstractmethod
    def make_port(self) -> OptionChainPort:
        """Uma instância NOVA do adapter, pronta para consulta."""

    @abstractmethod
    def known_symbol(self) -> str:
        """Subjacente que o adapter reconhece, com ao menos uma série."""

    UNKNOWN_SYMBOL = "XXXX99"

    def _chain(self) -> OptionChain:
        return self.make_port().get_chain(self.known_symbol())

    # --- forma -----------------------------------------------------------

    def test_satisfaz_o_protocol_em_runtime(self) -> None:
        assert isinstance(self.make_port(), OptionChainPort)

    def test_devolve_cadeia_do_subjacente_pedido(self) -> None:
        chain = self._chain()
        assert isinstance(chain, OptionChain)
        assert chain.underlying.underlying_symbol == self.known_symbol()

    def test_fixture_tem_series_para_a_bateria_nao_passar_no_vazio(self) -> None:
        assert len(self._chain().quotes) > 0, (
            f"known_symbol {self.known_symbol()!r} sem séries: as verificações por "
            f"cotação desta suíte passariam no vazio"
        )

    # --- book: lado ausente é None, nunca 0 (contratos 1 e 2) ---------------

    def test_lados_ausentes_sao_none_e_presentes_sao_finitos_e_positivos(self) -> None:
        for quote in self._chain().quotes:
            for valor in (quote.bid, quote.ask, quote.last):
                assert valor is None or (isfinite(valor) and valor > 0.0), (
                    f"{quote.contract.symbol}: lado {valor!r} — zero da fonte vira None "
                    f"no adapter (ADR-0003)"
                )

    def test_bid_nao_supera_ask_com_os_dois_lados_presentes(self) -> None:
        for quote in self._chain().quotes:
            if quote.bid is not None and quote.ask is not None:
                assert quote.bid <= quote.ask, quote.contract.symbol

    # --- subjacente (contrato 3) --------------------------------------------

    def test_todas_as_cotacoes_sao_do_subjacente_pedido(self) -> None:
        for quote in self._chain().quotes:
            assert quote.contract.terms.underlying == self.known_symbol(), quote.contract.symbol

    # --- tempo (contrato 4) ---------------------------------------------------

    def test_timestamps_tz_aware(self) -> None:
        chain = self._chain()
        timestamps = [chain.underlying.timestamp, *(q.timestamp for q in chain.quotes)]
        for ts in timestamps:
            assert ts.tzinfo is not None
            assert ts.tzinfo.utcoffset(ts) is not None

    # --- erros (contrato 5) -----------------------------------------------------

    def test_simbolo_desconhecido_e_excecao_de_dominio(self) -> None:
        """``UnknownSymbolError``, nunca ``KeyError``/``None``/erro de I/O vazando."""
        with pytest.raises(UnknownSymbolError):
            self.make_port().get_chain(self.UNKNOWN_SYMBOL)

    # --- consulta, não comando (contrato 6) ---------------------------------------

    def test_cadeia_devolvida_e_imutavel(self) -> None:
        chain = self._chain()
        assert isinstance(chain.quotes, tuple)
        with pytest.raises(FrozenInstanceError):
            chain.quotes = ()  # type: ignore[misc]  # justificativa: atribuição ilegal é o próprio teste
        for quote in chain.quotes:
            with pytest.raises(FrozenInstanceError):
                quote.bid = None  # type: ignore[misc]  # justificativa: idem

    def test_consulta_que_falha_nao_inutiliza_o_port(self) -> None:
        port = self.make_port()
        with pytest.raises(UnknownSymbolError):
            port.get_chain(self.UNKNOWN_SYMBOL)
        chain = port.get_chain(self.known_symbol())
        assert chain.underlying.underlying_symbol == self.known_symbol()

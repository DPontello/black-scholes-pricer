"""Suíte de contrato do ``OptionChainPort`` — escrita UMA vez, herdada por todos.

Mesmo molde da suíte do ``MarketDataPort`` (ARCH §8): type hints garantem
forma; ESTA suíte garante o contrato semântico da ADR-0003. Cada adapter
(COTAHIST na fase 1, intraday depois) herda a classe e fornece só as duas
fábricas — nasce com a bateria de conformidade pronta.

As verificações de book repetem de propósito invariantes que os VOs já
impõem na construção: o port é julgado pelo que ENTREGA, não pelo que o
tipo promete (um adapter que devolvesse um duck type escaparia dos VOs).
Pelo mesmo motivo o snapshot do subjacente passa pelas mesmas checagens
da suíte do ``MarketDataPort``: o ``MarketSnapshot`` não confere em runtime
o tipo da taxa nem o da vol.

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
from options_engine.domain.model.chain import OptionChain, OptionQuote
from options_engine.domain.model.conventions import RiskFreeRate, Volatility
from options_engine.domain.model.errors import UnknownSymbolError
from options_engine.domain.model.market import MarketSnapshot

__all__ = ["OptionChainPortContract"]


class OptionChainPortContract(ABC):
    """Herde, implemente as duas fábricas, ganhe a bateria inteira.

    ``known_symbols`` precisa trazer ao menos DOIS subjacentes distintos,
    cada um com ao menos uma série na fonte configurada. Com um símbolo só,
    um adapter que ignorasse o argumento (devolvendo sempre a cadeia do
    primeiro subjacente da fonte) passaria a bateria inteira; contra uma
    cadeia vazia, as verificações por cotação passariam no vazio. Há testes
    que travam as duas coisas.
    """

    @abstractmethod
    def make_port(self) -> OptionChainPort:
        """Uma instância NOVA do adapter, pronta para consulta."""

    @abstractmethod
    def known_symbols(self) -> tuple[str, ...]:
        """Ao menos dois subjacentes distintos que o adapter reconhece, cada
        um com ao menos uma série."""

    UNKNOWN_SYMBOL = "XXXX99"

    def _chains(self) -> list[tuple[str, OptionChain]]:
        """Cada símbolo conhecido consultado em sequência na MESMA instância.

        É como o painel percorre os subjacentes: um adapter que só responde
        certo à primeira consulta já tropeça aqui, em toda a bateria.
        """
        port = self.make_port()
        return [(simbolo, port.get_chain(simbolo)) for simbolo in self.known_symbols()]

    def _quotes(self) -> list[OptionQuote]:
        return [quote for _, chain in self._chains() for quote in chain.quotes]

    # --- forma -----------------------------------------------------------

    def test_satisfaz_o_protocol_em_runtime(self) -> None:
        assert isinstance(self.make_port(), OptionChainPort)

    def test_fixture_tem_dois_subjacentes_para_pegar_adapter_que_ignora_o_simbolo(
        self,
    ) -> None:
        assert len(set(self.known_symbols())) >= 2, (
            f"known_symbols {self.known_symbols()!r}: com menos de dois subjacentes "
            f"distintos, um adapter que ignora o símbolo pedido passaria no contrato"
        )

    def test_devolve_cadeia_do_subjacente_pedido(self) -> None:
        for simbolo, chain in self._chains():
            assert isinstance(chain, OptionChain), simbolo
            assert chain.underlying.underlying_symbol == simbolo

    def test_fixture_tem_series_para_a_bateria_nao_passar_no_vazio(self) -> None:
        for simbolo, chain in self._chains():
            assert len(chain.quotes) > 0, (
                f"{simbolo!r} sem séries: as verificações por cotação desta suíte "
                f"passariam no vazio"
            )

    def test_cotacoes_sao_option_quote(self) -> None:
        """Um duck type escaparia das invariantes que o VO impõe na construção."""
        for quote in self._quotes():
            assert isinstance(quote, OptionQuote), type(quote).__name__

    # --- snapshot do subjacente (molde do MarketDataPort, ARCH §8) -----------

    def test_subjacente_e_snapshot_com_spot_e_vol_positivos(self) -> None:
        for simbolo, chain in self._chains():
            underlying = chain.underlying
            assert isinstance(underlying, MarketSnapshot), simbolo
            assert underlying.spot > 0.0, simbolo
            assert isinstance(underlying.volatility, Volatility), simbolo
            assert underlying.volatility.value > 0.0, simbolo

    def test_taxa_do_subjacente_sempre_como_vo_com_compounding_explicito(self) -> None:
        """Taxa como float nu é proibida em qualquer port (CONVENTIONS §3)."""
        for simbolo, chain in self._chains():
            assert isinstance(chain.underlying.risk_free_rate, RiskFreeRate), simbolo

    # --- book: lado ausente é None, nunca 0 (contratos 1 e 2) ---------------

    def test_lados_ausentes_sao_none_e_presentes_sao_finitos_e_positivos(self) -> None:
        for quote in self._quotes():
            for valor in (quote.bid, quote.ask, quote.last):
                assert valor is None or (isfinite(valor) and valor > 0.0), (
                    f"{quote.contract.symbol}: lado {valor!r} — zero da fonte vira None "
                    f"no adapter (ADR-0003)"
                )

    def test_bid_nao_supera_ask_com_os_dois_lados_presentes(self) -> None:
        for quote in self._quotes():
            if quote.bid is not None and quote.ask is not None:
                assert quote.bid <= quote.ask, quote.contract.symbol

    # --- subjacente (contrato 3) --------------------------------------------

    def test_todas_as_cotacoes_sao_do_subjacente_pedido(self) -> None:
        for simbolo, chain in self._chains():
            for quote in chain.quotes:
                assert quote.contract.terms.underlying == simbolo, quote.contract.symbol

    # --- tempo (contrato 4) ---------------------------------------------------

    def test_timestamps_tz_aware(self) -> None:
        for _, chain in self._chains():
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
        for _, chain in self._chains():
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
        for simbolo in self.known_symbols():
            assert port.get_chain(simbolo).underlying.underlying_symbol == simbolo

    def test_consultas_repetidas_na_mesma_instancia_seguem_respondendo(self) -> None:
        """Consultar não consome a fonte: a segunda rodada, na mesma instância,
        ainda entrega a cadeia pedida e não vazia.

        Igualdade entre as rodadas NÃO é exigida — no intraday a cadeia muda
        entre consultas; cadeia idêntica é promessa da subclasse.
        """
        port = self.make_port()
        for rodada in ("primeira", "segunda"):
            for simbolo in self.known_symbols():
                chain = port.get_chain(simbolo)
                assert chain.underlying.underlying_symbol == simbolo, (rodada, simbolo)
                assert len(chain.quotes) > 0, f"{rodada} consulta de {simbolo!r} sem séries"

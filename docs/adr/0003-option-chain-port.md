# ADR-0003 — `OptionChainPort` e lado de book ausente como `None`

- **Status:** Aceita
- **Data:** 2026-10-26
- **Decisores:** mesa de operações

## Contexto

O `MarketDataPort` devolve só o `MarketSnapshot` do ativo-objeto. O painel
de renda precisa da **cadeia de opções** (todas as séries de um subjacente)
com bid, ask, último negócio e liquidez por série.

Nas fontes testadas (COTAHIST e brapi), melhor compra e melhor venda vêm
zeradas com frequência. Hoje o `MarketSnapshot` aceita `bid = 0` como valor
válido (`0 <= bid <= mid <= ask`): um zero de "sem oferta" que atravessasse a
fronteira viraria um preço real, sem erro de runtime.

Além disso, o `MarketSnapshot` carrega uma única volatilidade, mas no
mercado real cada série tem a sua volatilidade implícita.

## Decisão

1. Port novo, com assinatura nascida do use case (mesma disciplina do ARCH §4.1):

   ```python
   class OptionChainPort(Protocol):
       def get_chain(self, underlying_symbol: str) -> OptionChain: ...
   ```

   O pregão de referência vive dentro da cadeia (timestamp tz-aware); o
   adapter é configurado com a fonte/data. O mesmo contrato serve fim de
   dia e intraday.

2. VOs novos no domínio:
   - `OptionQuote`: `contract: OptionContract`, `bid: float | None`,
     `ask: float | None`, `last: float | None`, `trades: int`,
     `volume: float`, `timestamp: datetime`.
   - `OptionChain`: `underlying: MarketSnapshot` (VO existente reutilizado)
     e `quotes: tuple[OptionQuote, ...]`.

3. **Lado ausente é `None`, nunca `0`.** A tradução "zero da fonte → `None`"
   acontece exclusivamente no adapter (ARCH §1).

4. Contrato semântico, numa suíte herdável `OptionChainPortContract` em
   `tests/contract/` (molde da suíte do `MarketDataPort`):
   - `bid`, `ask` e `last` são `None` ou finitos e `> 0`;
   - com os dois lados presentes, `bid <= ask`;
   - todas as cotações são do subjacente pedido;
   - timestamps tz-aware;
   - símbolo desconhecido → `UnknownSymbolError`;
   - consulta, não comando.

5. A vol do `MarketSnapshot` do subjacente passa a ser a **vol realizada**
   (vol de referência), calculada pelo adapter a partir do histórico. A vol
   por série é a implícita, aplicada por perna com
   `dataclasses.replace(snapshot, volatility=...)` — o mesmo padrão de
   `apply_scenario`, sem alterar o VO.

## Consequências

- `MarketDataPort` não muda; nenhum adapter existente é afetado.
- Livro vazio no **ativo-objeto** também precisa de tradução no adapter
  (o `MarketSnapshot` exige `mid`); a regra fica na ADR-0004.
- Adapters futuros (Necton/MT5/Profit) nascem com a bateria de conformidade
  pronta e entram com uma linha no composition root.

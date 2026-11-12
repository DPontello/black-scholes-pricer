import { Fragment } from "react";

import type { ItemBook } from "../api/book";
import { formatarPreco } from "../formatacao";

const VERBO = { compra: "comprar", venda: "vender" };

/** O que fazer, numa linha: "vender 100 BOVAK168W1 a 1,12 · comprar 100 BOVA11". */
export function LinhaPernas({ item }: { item: ItemBook }) {
  const partes = item.pernas.map((p) => ({
    chave: p.ticker,
    lado: p.lado,
    texto: `${p.quantidade} ${p.ticker} a ${formatarPreco(p.premio)}`,
  }));
  if (item.acao !== null) {
    const { lado, quantidade, origem } = item.acao;
    partes.push({
      chave: "acao",
      lado,
      texto: `${quantidade} ${item.ativo}${origem === "carteira" ? " da carteira" : ""}`,
    });
  }
  return (
    <p className="linha-pernas">
      {partes.map((parte, i) => (
        <Fragment key={parte.chave}>
          {i > 0 && " · "}
          <span className={parte.lado}>{VERBO[parte.lado]}</span> {parte.texto}
        </Fragment>
      ))}
    </p>
  );
}

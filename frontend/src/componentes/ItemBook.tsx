import { useNavigate } from "react-router-dom";

import type { ItemBook as Item } from "../api/book";
import { formatarData, formatarPreco } from "../formatacao";

const QUALIDADE = { executavel: "executável", indicativo: "indicativo", teorico: "teórico" };

type Props = { item: Item };

export function ItemBook({ item }: Props) {
  const navegar = useNavigate();

  function abrir() {
    navegar(`/montador?ativo=${encodeURIComponent(item.ativo)}`, { state: { pedido: item.pedido } });
  }

  return (
    <article className="item-book" aria-label={`${item.nome} ${item.ativo}`}>
      <header>
        <strong>{item.nome}</strong> {item.ativo}{" "}
        <span className="secundario">
          vence {formatarData(item.vencimento)} ({item.dias_uteis} du)
        </span>
        {item.qualidade !== "executavel" && (
          <span className="selo-qualidade">preço {QUALIDADE[item.qualidade]}</span>
        )}
      </header>
      <p className="criterio">
        {item.criterio.rotulo}: <strong>{item.criterio.texto}</strong>
      </p>
      <ul className="pernas-book">
        {item.pernas.map((perna) => (
          <li key={perna.ticker}>
            <span className={perna.lado}>{perna.lado}</span> {perna.quantidade} {perna.ticker} (
            {perna.tipo} {formatarPreco(perna.strike)}) a {formatarPreco(perna.premio)}
          </li>
        ))}
        {item.acao !== null && (
          <li>
            <span className={item.acao.lado}>{item.acao.lado}</span> {item.acao.quantidade} ações{" "}
            {item.acao.origem === "carteira" ? "da carteira" : "junto"}
          </li>
        )}
      </ul>
      <div className="numeros">
        {item.numeros.map((m) => (
          <span className="numero" key={m.chave}>
            <span className="secundario">{m.rotulo}</span>
            {m.texto}
          </span>
        ))}
      </div>
      <p className="porque">{item.porque}</p>
      {item.rotulos.length > 0 && (
        <ul className="rotulos">
          {item.rotulos.map((r) => (
            <li key={r.chave}>{r.texto}</li>
          ))}
        </ul>
      )}
      <button type="button" onClick={abrir}>
        Abrir no montador
      </button>
    </article>
  );
}

import type {
  AcaoPedido,
  Analise,
  Lado,
  OrigemPreco,
  PedidoAnalise,
  PernaPedido,
} from "../api/montador";
import { formatarPreco } from "../formatacao";
import { CampoPreco } from "./CampoPreco";

const ORIGEM: Record<OrigemPreco, string> = {
  executavel: "book",
  indicativo: "último negócio",
  teorico: "teórico",
  digitado: "digitado",
  preco_medio: "preço médio da carteira",
};

type Props = {
  pedido: PedidoAnalise;
  analise: Analise | null;
  onMudar: (pedido: PedidoAnalise) => void;
};

function SeletorLado({ valor, onMudar, rotulo }: { valor: Lado; onMudar: (l: Lado) => void; rotulo: string }) {
  return (
    <select aria-label={`Lado de ${rotulo}`} value={valor} onChange={(e) => onMudar(e.target.value as Lado)}>
      <option value="compra">compra</option>
      <option value="venda">venda</option>
    </select>
  );
}

export function TabelaPernas({ pedido, analise, onMudar }: Props) {
  function mudarPerna(i: number, parcial: Partial<PernaPedido>) {
    const pernas = pedido.pernas.map((p, j) => (j === i ? { ...p, ...parcial } : p));
    onMudar({ ...pedido, pernas });
  }
  function mudarAcao(parcial: Partial<AcaoPedido>) {
    if (pedido.acao !== null) onMudar({ ...pedido, acao: { ...pedido.acao, ...parcial } });
  }

  if (pedido.pernas.length === 0 && pedido.acao === null)
    return (
      <p className="secundario">
        Escolha um modelo pronto ou clique em + numa série da cadeia para pôr a primeira perna.
      </p>
    );

  return (
    <table className="tabela-pernas">
      <thead>
        <tr>
          <th>Série</th>
          <th>Lado</th>
          <th className="num">Quantidade</th>
          <th className="num">Preço</th>
          <th>Origem do preço</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {pedido.pernas.map((perna, i) => {
          const vista = analise?.pernas[i];
          const foraDoLote = vista?.lote != null && perna.quantidade % vista.lote !== 0;
          return (
            <tr key={`${perna.ticker}-${i}`}>
              <td>
                {perna.ticker}{" "}
                {vista !== undefined && (
                  <span className="secundario">
                    {vista.tipo} {formatarPreco(vista.strike)}
                    {vista.estilo === "american" ? " · americana" : ""}
                  </span>
                )}
              </td>
              <td>
                <SeletorLado
                  rotulo={perna.ticker}
                  valor={perna.lado}
                  onMudar={(lado) => mudarPerna(i, { lado })}
                />
              </td>
              <td className="num">
                <input
                  aria-label={`Quantidade de ${perna.ticker}`}
                  className={foraDoLote ? "fora-do-lote" : undefined}
                  type="number"
                  min={1}
                  step={vista?.lote ?? 100}
                  value={perna.quantidade}
                  onChange={(e) => mudarPerna(i, { quantidade: Math.max(1, Number(e.target.value)) })}
                />
              </td>
              <td className="num">
                <CampoPreco
                  rotulo={`Preço de ${perna.ticker}`}
                  valor={perna.preco}
                  placeholder={formatarPreco(vista?.preco ?? null)}
                  onMudar={(preco) => mudarPerna(i, { preco })}
                />
              </td>
              <td className="secundario">{vista?.origem ? ORIGEM[vista.origem] : "sem preço"}</td>
              <td>
                <button
                  type="button"
                  aria-label={`Tirar ${perna.ticker}`}
                  onClick={() => onMudar({ ...pedido, pernas: pedido.pernas.filter((_, j) => j !== i) })}
                >
                  ×
                </button>
              </td>
            </tr>
          );
        })}
        {pedido.acao !== null && (
          <tr>
            <td>
              Ação {pedido.ativo}{" "}
              <select
                aria-label="De onde vem a ação"
                value={pedido.acao.origem}
                onChange={(e) => mudarAcao({ origem: e.target.value as AcaoPedido["origem"] })}
              >
                <option value="compra">comprada junto</option>
                <option value="carteira">já na carteira</option>
              </select>
            </td>
            <td>
              <SeletorLado
                rotulo={`ação ${pedido.ativo}`}
                valor={pedido.acao.lado}
                onMudar={(lado) => mudarAcao({ lado })}
              />
            </td>
            <td className="num">
              <input
                aria-label="Quantidade de ações"
                type="number"
                min={1}
                step={100}
                value={pedido.acao.quantidade}
                onChange={(e) => mudarAcao({ quantidade: Math.max(1, Number(e.target.value)) })}
              />
            </td>
            <td className="num">
              <CampoPreco
                rotulo="Preço da ação"
                valor={pedido.acao.preco}
                placeholder={
                  pedido.acao.origem === "carteira"
                    ? "preço médio"
                    : formatarPreco(analise?.acao?.preco ?? null)
                }
                onMudar={(preco) => mudarAcao({ preco })}
              />
            </td>
            <td className="secundario">
              {analise?.acao?.origem_preco ? ORIGEM[analise.acao.origem_preco] : "—"}
            </td>
            <td>
              <button
                type="button"
                aria-label="Tirar a ação"
                onClick={() => onMudar({ ...pedido, acao: null })}
              >
                ×
              </button>
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

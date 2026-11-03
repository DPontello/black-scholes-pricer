import { Fragment, useState } from "react";
import { useNavigate } from "react-router-dom";

import type { FamiliaBook, ItemBook } from "../api/book";
import { formatarData, formatarDiasUteis, formatarPreco } from "../formatacao";
import { LinhaPernas } from "./LinhaPernas";

const QUALIDADE = { executavel: "executável", indicativo: "indicativo", teorico: "teórico" };

function chave(item: ItemBook): string {
  return item.pedido.pernas.map((p) => p.ticker).join("/");
}

function Itens({ itens }: { itens: ItemBook[] }) {
  const navegar = useNavigate();
  const [abertas, setAbertas] = useState<Set<string>>(new Set());

  function alternar(id: string) {
    const novas = new Set(abertas);
    if (!novas.delete(id)) novas.add(id);
    setAbertas(novas);
  }

  function abrir(item: ItemBook) {
    navegar(`/montador?ativo=${encodeURIComponent(item.ativo)}`, { state: { pedido: item.pedido } });
  }

  return (
    <table className="tabela-familia">
      <thead>
        <tr>
          <th>Operação</th>
          <th>Vence</th>
          <th>Critério</th>
          <th className="num">Ganha até</th>
          <th className="num">Perde até</th>
          <th className="num">Chance de lucro</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {itens.map((item) => {
          const id = chave(item);
          const aberta = abertas.has(id);
          const strikes = item.pernas.map((p) => `${p.tipo} ${formatarPreco(p.strike)}`).join(" / ");
          return (
            <Fragment key={id}>
              <tr className="linha-item" onClick={() => alternar(id)}>
                <td>
                  <button type="button" className="link" aria-expanded={aberta}>
                    <span aria-hidden="true">{aberta ? "▾" : "▸"}</span> {item.nome}
                  </button>{" "}
                  <span className="secundario">
                    {item.ativo} {strikes}
                  </span>
                  {item.qualidade !== "executavel" && (
                    <span className="selo-qualidade">preço {QUALIDADE[item.qualidade]}</span>
                  )}
                </td>
                <td>
                  {formatarData(item.vencimento)} ({formatarDiasUteis(item.dias_uteis)})
                </td>
                <td>
                  {item.criterio.texto} <span className="secundario">{item.criterio.rotulo}</span>
                </td>
                <td className="num">{item.resultado?.ganha_ate_texto ?? "—"}</td>
                <td className={item.resultado === null ? "num" : "num baixa"}>
                  {item.resultado?.perde_ate_texto ?? "—"}
                </td>
                <td className="num">{item.resultado?.chance_texto ?? "—"}</td>
                <td>
                  <button
                    type="button"
                    className="link"
                    aria-label={`Abrir ${item.nome} ${item.ativo} no montador`}
                    onClick={(e) => {
                      e.stopPropagation();
                      abrir(item);
                    }}
                  >
                    abrir
                  </button>
                </td>
              </tr>
              {aberta && (
                <tr className="detalhe-operacao">
                  <td colSpan={7}>
                    <LinhaPernas item={item} />
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
                  </td>
                </tr>
              )}
            </Fragment>
          );
        })}
      </tbody>
    </table>
  );
}

export function motivoVazio(familia: FamiliaBook): string {
  if (familia.referencias.length > 0) return "sem preço de compra e venda agora";
  if (familia.exclusoes.length > 0) return "nenhuma série passou nos filtros";
  return "nada passou nos filtros do preset";
}

export function TabelaFamilia({ familia }: { familia: FamiliaBook }) {
  return (
    <>
      {familia.itens.length === 0 ? (
        <p className="secundario">Nada hoje nesta família: {motivoVazio(familia)}.</p>
      ) : (
        <Itens itens={familia.itens} />
      )}
      {familia.referencias.length > 0 && (
        <details className="referencias">
          <summary>Referências sem preço de compra e venda agora ({familia.referencias.length})</summary>
          <Itens itens={familia.referencias} />
        </details>
      )}
      {familia.exclusoes.length > 0 && (
        <details className="exclusoes">
          <summary>Fora do book por dado ruim ({familia.exclusoes.length})</summary>
          <ul>
            {familia.exclusoes.map((e) => (
              <li key={`${e.simbolo}:${e.motivo}`}>
                {e.simbolo}: {e.motivo}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

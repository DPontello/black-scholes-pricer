import { type FormEvent, useState } from "react";

import type { Cotacao } from "../api/aoVivo";
import {
  formatarHora,
  formatarInteiro,
  formatarPercentual,
  formatarPreco,
  formatarVolume,
} from "../formatacao";

type Props = {
  cotacoes: Cotacao[];
  selecionado: string | null;
  onEscolher: (ativo: string) => void;
  onDefinirAtivos: (ativos: string[]) => void;
};

const FONTE_CURTA = { ao_vivo: "", atrasado: "atrasado", fim_de_dia: "fim de dia" } as const;

function classeVariacao(v: number | null): string {
  if (v === null || v === 0) return "";
  return v > 0 ? "alta" : "baixa";
}

export function ListaAtivos({ cotacoes, selecionado, onEscolher, onDefinirAtivos }: Props) {
  const [novo, setNovo] = useState("");
  const ativos = cotacoes.map((c) => c.ativo);

  function adicionar(evento: FormEvent) {
    evento.preventDefault();
    const ticker = novo.trim().toUpperCase();
    if (ticker === "") return;
    onDefinirAtivos([...ativos, ticker]);
    setNovo("");
  }

  return (
    <div className="lista-ativos">
      <table>
        <thead>
          <tr>
            <th>Ativo</th>
            <th className="num">Último</th>
            <th className="num">Var%</th>
            <th className="num">Compra</th>
            <th className="num">Venda</th>
            <th className="num">Negócios</th>
            <th className="num">Volume</th>
            <th className="num">Hora</th>
            <th aria-label="Remover" />
          </tr>
        </thead>
        <tbody>
          {cotacoes.map((c) => (
            <tr key={c.ativo} className={c.ativo === selecionado ? "selecionado" : undefined}>
              <td>
                <button type="button" className="link" onClick={() => onEscolher(c.ativo)}>
                  {c.ativo}
                </button>
              </td>
              {c.motivo !== null ? (
                <td colSpan={7} className="secundario">
                  {c.motivo}
                </td>
              ) : (
                <>
                  <td className="num">{formatarPreco(c.ultimo)}</td>
                  <td className={`num ${classeVariacao(c.variacao_pct)}`}>
                    {formatarPercentual(c.variacao_pct)}
                  </td>
                  <td className="num compra">{formatarPreco(c.compra)}</td>
                  <td className="num venda">{formatarPreco(c.venda)}</td>
                  <td className="num">{formatarInteiro(c.negocios)}</td>
                  <td className="num">{formatarVolume(c.volume)}</td>
                  <td className="num">
                    {formatarHora(c.hora)}
                    {c.fonte !== null && FONTE_CURTA[c.fonte] !== "" && (
                      <span className="secundario"> ({FONTE_CURTA[c.fonte]})</span>
                    )}
                  </td>
                </>
              )}
              <td>
                <button
                  type="button"
                  aria-label={`Remover ${c.ativo}`}
                  title="Tirar da lista"
                  onClick={() => onDefinirAtivos(ativos.filter((a) => a !== c.ativo))}
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="adicionar-ativo" onSubmit={adicionar}>
        <input
          aria-label="Adicionar ativo"
          placeholder="Ticker, ex.: BOVA11"
          value={novo}
          onChange={(e) => setNovo(e.target.value)}
          maxLength={12}
        />{" "}
        <button type="submit">Adicionar</button>
      </form>
    </div>
  );
}

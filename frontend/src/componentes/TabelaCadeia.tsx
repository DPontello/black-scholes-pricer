import { useState } from "react";

import type { Cadeia, CadeiaIndisponivel, Serie, Vencimento } from "../api/aoVivo";
import {
  formatarData,
  formatarDelta,
  formatarHora,
  formatarInteiro,
  formatarPreco,
  formatarVol,
} from "../formatacao";

type Props = {
  ativo: string | null;
  cadeia: Cadeia | null;
  indisponivel: CadeiaIndisponivel | null;
  onVencimentos: (datas: string[]) => void;
};

const FONTES = { ao_vivo: "Ao vivo (Tryd)", atrasado: "Atrasado", fim_de_dia: "Fim de dia (B3)" };

type Linha = { strike: number; call: Serie | undefined; put: Serie | undefined };

function linhas(vencimento: Vencimento): Linha[] {
  const porStrike = new Map<number, { calls: Serie[]; puts: Serie[] }>();
  for (const serie of vencimento.series) {
    const grupo = porStrike.get(serie.strike) ?? { calls: [], puts: [] };
    (serie.tipo === "call" ? grupo.calls : grupo.puts).push(serie);
    porStrike.set(serie.strike, grupo);
  }
  const saida: Linha[] = [];
  for (const strike of [...porStrike.keys()].sort((a, b) => a - b)) {
    const { calls, puts } = porStrike.get(strike)!;
    for (let i = 0; i < Math.max(calls.length, puts.length); i += 1)
      saida.push({ strike, call: calls[i], put: puts[i] });
  }
  return saida;
}

function maisPerto(strikes: number[], spot: number): number | null {
  let melhor: number | null = null;
  for (const strike of strikes)
    if (melhor === null || Math.abs(strike - spot) < Math.abs(melhor - spot)) melhor = strike;
  return melhor;
}

function Lado({ serie, espelho }: { serie: Serie | undefined; espelho: boolean }) {
  const celulas = [
    <td key="compra" className="num compra" title={serie?.ticker}>
      {formatarPreco(serie?.compra ?? null)}
    </td>,
    <td key="venda" className="num venda">
      {formatarPreco(serie?.venda ?? null)}
    </td>,
    <td key="ultimo" className="num">
      {formatarPreco(serie?.ultimo ?? null)}
    </td>,
    <td key="iv" className="num">
      {formatarVol(serie?.iv ?? null)}
    </td>,
    <td key="delta" className="num">
      {formatarDelta(serie?.delta ?? null)}
    </td>,
    <td key="negocios" className="num secundario">
      {serie === undefined ? "—" : formatarInteiro(serie.negocios)}
    </td>,
  ];
  return <>{espelho ? celulas.reverse() : celulas}</>;
}

function EscolhaVencimentos({
  cadeia,
  onVencimentos,
  onAdicionado,
}: {
  cadeia: Cadeia;
  onVencimentos: (datas: string[]) => void;
  onAdicionado: (data: string) => void;
}) {
  const escolhidos = new Set(cadeia.vencimentos.map((v) => v.data));

  function alternar(data: string) {
    if (escolhidos.has(data)) {
      if (escolhidos.size === 1) return; // a cadeia sempre mostra ao menos um vencimento
      escolhidos.delete(data);
    } else {
      escolhidos.add(data);
      onAdicionado(data);
    }
    onVencimentos([...escolhidos].sort());
  }

  return (
    <div className="vencimentos" role="group" aria-label="Vencimentos">
      <span className="secundario">Vencimentos (S = semanal):</span>
      {cadeia.disponiveis.map((d) => (
        <button
          key={d.data}
          type="button"
          aria-pressed={escolhidos.has(d.data)}
          className={d.semanal ? "semanal" : undefined}
          title={`${d.semanal ? "Semanal" : "Mensal"}, ${d.dias_uteis} dias úteis`}
          onClick={() => alternar(d.data)}
        >
          {formatarData(d.data).slice(0, 5)}
          {d.semanal ? " S" : ""}
        </button>
      ))}
    </div>
  );
}

export function TabelaCadeia({ ativo, cadeia, indisponivel, onVencimentos }: Props) {
  const [aba, setAba] = useState<string | null>(null);

  if (ativo === null) {
    return <p className="secundario">Escolha um ativo na lista para ver a cadeia de opções.</p>;
  }
  if (indisponivel !== null && indisponivel.ativo === ativo) {
    return (
      <p className="aviso" role="status">
        Cadeia de {ativo} indisponível: {indisponivel.mensagem}
      </p>
    );
  }
  if (cadeia === null || cadeia.ativo !== ativo) {
    return <p className="secundario">Carregando a cadeia de {ativo}…</p>;
  }

  const vencimento = cadeia.vencimentos.find((v) => v.data === aba) ?? cadeia.vencimentos[0];
  const atm =
    vencimento === undefined
      ? null
      : maisPerto(
          vencimento.series.map((s) => s.strike),
          cadeia.spot,
        );

  return (
    <section className="tabela-cadeia">
      <header className="cabecalho-cadeia">
        <strong>{cadeia.ativo}</strong> spot {formatarPreco(cadeia.spot)}{" "}
        <span className="secundario">
          ({FONTES[cadeia.fonte]}, {formatarHora(cadeia.hora)})
        </span>
      </header>
      <EscolhaVencimentos cadeia={cadeia} onVencimentos={onVencimentos} onAdicionado={setAba} />
      <div className="abas" role="tablist">
        {cadeia.vencimentos.map((v) => (
          <button
            key={v.data}
            type="button"
            role="tab"
            aria-selected={v === vencimento}
            onClick={() => setAba(v.data)}
          >
            {formatarData(v.data).slice(0, 5)} ({v.dias_uteis} du)
          </button>
        ))}
      </div>
      {vencimento === undefined ? (
        <p className="secundario">Nenhum vencimento com séries no cadastro.</p>
      ) : vencimento.series.length === 0 ? (
        <p className="secundario">Nenhuma série deste vencimento chegou ainda.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th colSpan={6} className="lado-call">
                CALLS
              </th>
              <th />
              <th colSpan={6} className="lado-put">
                PUTS
              </th>
            </tr>
            <tr>
              {["Compra", "Venda", "Último", "IV", "Delta", "Neg."].map((c) => (
                <th key={`call-${c}`} className="num">
                  {c}
                </th>
              ))}
              <th className="num">Strike</th>
              {["Neg.", "Delta", "IV", "Último", "Venda", "Compra"].map((c) => (
                <th key={`put-${c}`} className="num">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas(vencimento).map((linha) => (
              <tr
                key={`${linha.strike}-${linha.call?.ticker ?? ""}-${linha.put?.ticker ?? ""}`}
                className={linha.strike === atm ? "no-dinheiro" : undefined}
              >
                <Lado serie={linha.call} espelho={false} />
                <td className="num strike">{formatarPreco(linha.strike)}</td>
                <Lado serie={linha.put} espelho />
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {cadeia.rejeitadas.length > 0 && (
        <details className="rejeitadas">
          <summary>{cadeia.rejeitadas.length} série(s) fora da cadeia</summary>
          <ul>
            {cadeia.rejeitadas.map((r) => (
              <li key={r.ticker}>
                {r.ticker}: {r.motivo}
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

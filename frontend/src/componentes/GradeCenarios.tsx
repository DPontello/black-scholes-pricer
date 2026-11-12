import type { Hoje } from "../api/montador";
import { formatarPercentual, formatarPreco } from "../formatacao";

function pontos(choque: number): string {
  const valor = Math.round(choque * 100);
  return `${valor > 0 ? "+" : ""}${valor} pts`;
}

export function GradeCenarios({ grade }: { grade: Hoje["grade"] }) {
  return (
    <table className="grade-cenarios">
      <caption>Resultado hoje se o preço e a volatilidade mudarem agora</caption>
      <thead>
        <tr>
          <th>Preço \ Vol</th>
          {grade.choques_vol.map((c) => (
            <th key={c} className="num">
              {pontos(c)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {grade.spots.map((spot, i) => (
          <tr key={spot}>
            <th>
              {formatarPercentual(grade.choques_spot[i] ?? null)}{" "}
              <span className="secundario">({formatarPreco(spot)})</span>
            </th>
            {(grade.valores[i] ?? []).map((v, j) => (
              <td key={j} className={`num ${v === null ? "" : v >= 0 ? "alta" : "baixa"}`}>
                {formatarPreco(v)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

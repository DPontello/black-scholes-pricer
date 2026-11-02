import type { Analise } from "../api/montador";
import { formatarDelta, formatarPreco, formatarVol } from "../formatacao";

function reais(v: number): string {
  return `R$ ${formatarPreco(Math.abs(v))}`;
}

export function frase(analise: Analise): string {
  const v = analise.no_vencimento;
  if (v === null) return "Falta o preço de alguma perna: o resultado sai só bruto, sem prêmio.";
  const caixa =
    v.caixa >= 0 ? `Você recebe ${reais(v.caixa)} agora` : `Você paga ${reais(v.caixa)} agora`;
  const pior =
    v.perda_max === null
      ? "no pior caso a perda é ilimitada"
      : v.perda_max >= 0
        ? "não há perda no vencimento"
        : `no pior caso perde ${reais(v.perda_max)}`;
  const melhor =
    v.ganho_max === null
      ? "o ganho é ilimitado"
      : v.ganho_max > 0
        ? `ganha no máximo ${reais(v.ganho_max)}`
        : v.ganho_max === 0
          ? "no melhor caso empata"
          : `no melhor caso ainda perde ${reais(v.ganho_max)}`;
  const empates = v.breakevens.map((b) => formatarPreco(b));
  const empate =
    empates.length === 0
      ? ""
      : `; empata se ${analise.ativo} terminar em ${empates.join(" ou ")} no vencimento`;
  return `${caixa}; ${pior}; ${melhor}${empate}.`;
}

function Numero({ rotulo, valor, dica }: { rotulo: string; valor: string; dica?: string }) {
  return (
    <div className="numero" title={dica}>
      <span className="secundario">{rotulo}</span>
      <strong>{valor}</strong>
    </div>
  );
}

function maximo(v: number | null): string {
  return v === null ? "ilimitado" : `R$ ${formatarPreco(v)}`;
}

export function ResumoEstrutura({ analise }: { analise: Analise }) {
  const v = analise.no_vencimento;
  const gregas = analise.hoje?.gregas;
  return (
    <section className="resumo-estrutura">
      <p className="frase">{frase(analise)}</p>
      {v !== null && (
        <div className="numeros">
          <Numero rotulo="Ganho máximo líquido" valor={maximo(v.ganho_max_liquido)} />
          <Numero rotulo="Perda máxima líquida" valor={maximo(v.perda_max_liquida)} />
          <Numero
            rotulo="Custos de montagem"
            valor={`R$ ${formatarPreco(v.custos_montagem)}`}
            dica="Emolumentos da B3 e corretagem, pela tabela da ADR-0005"
          />
          <Numero
            rotulo="IR estimado no ganho máximo"
            valor={v.ir_no_ganho_max === null ? "—" : `R$ ${formatarPreco(v.ir_no_ganho_max)}`}
            dica="Estimativa por operação, não é cálculo fiscal"
          />
          <Numero
            rotulo="Chance de lucro"
            valor={formatarVol(v.probabilidade)}
            dica="Probabilidade risco-neutra no vencimento, pela vol do smile no dinheiro"
          />
          <Numero rotulo="Dias úteis" valor={String(analise.dias_uteis)} />
        </div>
      )}
      {gregas !== undefined && (
        <div className="numeros">
          <Numero rotulo="Delta" valor={formatarDelta(gregas.delta)} dica="Em ações equivalentes" />
          <Numero rotulo="Gamma" valor={formatarDelta(gregas.gamma)} />
          <Numero
            rotulo="Theta por dia útil"
            valor={`R$ ${formatarPreco(gregas.theta_dia_util)}`}
            dica="Quanto a estrutura ganha ou perde de um dia útil para o outro, com o resto parado"
          />
          <Numero
            rotulo="Vega por ponto"
            valor={`R$ ${formatarPreco(gregas.vega_ponto)}`}
            dica="Quanto ganha ou perde se a volatilidade subir 1 ponto"
          />
        </div>
      )}
      {analise.hoje_indisponivel !== null && (
        <p className="secundario">Sem avaliação de hoje: {analise.hoje_indisponivel}.</p>
      )}
      {analise.avisos.length > 0 && (
        <ul className="avisos">
          {analise.avisos.map((a) => (
            <li key={a} className="aviso">
              {a}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

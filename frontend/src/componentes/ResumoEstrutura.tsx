import type { Analise } from "../api/montador";
import { formatarDelta, formatarPreco, formatarVol } from "../formatacao";
import { Ajuda } from "./Ajuda";
import { GradeCenarios } from "./GradeCenarios";

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

type NumeroProps = { rotulo: string; valor: string; dica?: string; termo?: string };

function Numero({ rotulo, valor, dica, termo }: NumeroProps) {
  return (
    <div className="numero" title={dica}>
      <span className="secundario">
        {rotulo}
        {termo !== undefined && (
          <>
            {" "}
            <Ajuda id={termo} />
          </>
        )}
      </span>
      <strong>{valor}</strong>
    </div>
  );
}

function maximo(v: number | null): string {
  return v === null ? "ilimitado" : `R$ ${formatarPreco(v)}`;
}

export function ResumoEstrutura({ analise }: { analise: Analise }) {
  const v = analise.no_vencimento;
  return (
    <section className="resumo-estrutura">
      <p className="frase">{frase(analise)}</p>
      {v !== null && (
        <div className="numeros numeros-grandes">
          <Numero rotulo="Ganho máximo" valor={maximo(v.ganho_max)} termo="ganho-perda-maximos" />
          <Numero rotulo="Perda máxima" valor={maximo(v.perda_max)} />
          <Numero
            rotulo="Chance de lucro"
            valor={formatarVol(v.probabilidade)}
            dica="Probabilidade risco-neutra no vencimento, pela vol do smile no dinheiro"
            termo="chance-de-lucro"
          />
        </div>
      )}
    </section>
  );
}

export function DetalhesEstrutura({ analise }: { analise: Analise }) {
  const v = analise.no_vencimento;
  const gregas = analise.hoje?.gregas;
  return (
    <>
      {v !== null && (
        <div className="numeros">
          <Numero
            rotulo="Custos de montagem"
            valor={`R$ ${formatarPreco(v.custos_montagem)}`}
            dica="Emolumentos da B3 e corretagem, pela tabela da ADR-0005; não saem do ganho nem da perda"
            termo="custos-ir"
          />
          <Numero rotulo="Dias úteis" valor={String(analise.dias_uteis)} />
        </div>
      )}
      {gregas !== undefined && (
        <div className="numeros">
          <Numero
            rotulo="Delta"
            valor={formatarDelta(gregas.delta)}
            dica="Em ações equivalentes"
            termo="delta"
          />
          <Numero rotulo="Gamma" valor={formatarDelta(gregas.gamma)} termo="gamma" />
          <Numero
            rotulo="Theta por dia útil"
            valor={`R$ ${formatarPreco(gregas.theta_dia_util)}`}
            dica="Quanto a estrutura ganha ou perde de um dia útil para o outro, com o resto parado"
            termo="theta"
          />
          <Numero
            rotulo="Vega por ponto"
            valor={`R$ ${formatarPreco(gregas.vega_ponto)}`}
            dica="Quanto ganha ou perde se a volatilidade subir 1 ponto"
            termo="vega"
          />
        </div>
      )}
      {analise.hoje !== null && <GradeCenarios grade={analise.hoje.grade} />}
    </>
  );
}

export function AvisosEstrutura({ analise }: { analise: Analise }) {
  if (analise.hoje_indisponivel === null && analise.avisos.length === 0) return null;
  return (
    <>
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
    </>
  );
}

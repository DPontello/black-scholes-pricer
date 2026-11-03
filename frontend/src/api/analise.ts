import { pedir, type Fonte } from "./cliente";

/** Vols e CDI em fração anual; `null` é pregão sem o número (sem smile no spot, histórico curto). */
export type Pregao = {
  pregao: string;
  fechamento: number;
  iv30: number | null;
  extrapolada: boolean;
  hv21: number | null;
};

export type Hoje = {
  iv30: number;
  hv21: number;
  iv_rank: number | null;
  iv_percentil: number | null;
  regime: "alta" | "baixa" | "neutra";
  regime_pela_hv: boolean;
  extrapolada: boolean;
};

export type Smile = {
  vencimento: string;
  dias_uteis: number;
  pontos: { strike: number; iv: number; ticker: string }[];
};

export type PontoTermo = { vencimento: string; dias_uteis: number; iv: number };

export type AnaliseMercado = {
  ativo: string;
  spot: number;
  cdi_anual: number;
  fonte: Fonte;
  hora: string;
  historico: Pregao[];
  historico_motivo: string | null;
  hoje: Hoje | null;
  hoje_motivo: string | null;
  smiles: Smile[];
  estrutura: PontoTermo[];
};

export function analisarAtivo(ativo: string): Promise<AnaliseMercado> {
  return pedir(`/api/mercado/analise/${encodeURIComponent(ativo)}`);
}

import { json, pedir, type Fonte, type PresetBook } from "./cliente";
import type { Lado, PedidoAnalise } from "./montador";

export type Familia = "renda" | "volatilidade" | "direcionais" | "protecao";
export type Qualidade = "executavel" | "indicativo" | "teorico";

/** `valor` cru na `unidade` da API; `texto` já formatado, o mesmo que o porquê cita. */
export type Metrica = { chave: string; rotulo: string; valor: number; unidade: string; texto: string };

export type PernaBook = {
  ticker: string;
  tipo: "call" | "put";
  strike: number;
  lado: Lado;
  quantidade: number;
  premio: number;
  qualidade: Qualidade;
};

/**
 * Ganho e perda brutos no vencimento, sem custos nem IR (como a corretora mostra); a chance de lucro também.
 * `null` em `ganha_ate`/`perde_ate` = sem limite. Os textos já vêm formatados.
 */
export type ResultadoBook = {
  ganha_ate: number | null;
  perde_ate: number | null;
  chance_de_lucro: number;
  ganha_ate_texto: string;
  perde_ate_texto: string;
  chance_texto: string;
};

export type ItemBook = {
  familia: Familia;
  estrutura: string;
  nome: string;
  ativo: string;
  vencimento: string;
  dias_uteis: number;
  pernas: PernaBook[];
  acao: { lado: Lado; quantidade: number; origem: "compra" | "carteira" } | null;
  qualidade: Qualidade;
  criterio: Metrica;
  numeros: Metrica[];
  porque: string;
  porque_curto: string;
  rotulos: { chave: string; texto: string }[];
  pedido: PedidoAnalise;
  resultado: ResultadoBook | null;
};

export type Exclusao = { simbolo: string; motivo: string };

export type FamiliaBook = { itens: ItemBook[]; referencias: ItemBook[]; exclusoes: Exclusao[] };

export type ContextoVol = {
  ativo: string;
  iv30: number | null;
  hv21: number | null;
  iv_rank: number | null;
  iv_percentil: number | null;
  regime: "alta" | "baixa" | "neutra" | null;
  regime_pela_hv: boolean;
  extrapolada: boolean;
  motivo: string | null;
};

export type Book = {
  pregao: string | null;
  fonte: Fonte;
  preset: PresetBook;
  contextos: ContextoVol[];
  familias: Record<Familia, FamiliaBook>;
  indisponiveis: Exclusao[];
};

export type Visao = { ativo: string; direcao: "alta" | "baixa"; alvo: number; vencimento: string };

export function carregarBook(): Promise<Book> {
  return pedir("/api/book");
}

export function direcional(visao: Visao): Promise<FamiliaBook> {
  return pedir("/api/book/direcional", json("POST", visao));
}

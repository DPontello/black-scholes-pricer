import type { Familia } from "./book";
import { pedir } from "./cliente";
import type { Lado } from "./montador";

export type PernaExemplo = {
  tipo: "call" | "put";
  lado: Lado;
  strike: number;
  premio: number;
  quantidade: number;
};

export type CenarioExemplo = { preco: number; resultado: number };

/**
 * Exemplo fixo de uma operação (ação a R$ 50,00), em reais, sem custos nem IR.
 * `premio_liquido` > 0 recebe e < 0 paga (só as opções); `null` em `ganho_maximo`/`perda_maxima` = sem limite.
 */
export type Exemplo = {
  chave: string;
  nome: string;
  familia: Familia;
  spot: number;
  pernas: PernaExemplo[];
  acoes: number;
  premio_liquido: number;
  cenarios: CenarioExemplo[];
  empates: number[];
  ganho_maximo: number | null;
  perda_maxima: number | null;
  curva: [number, number][];
};

export function carregarExemplos(): Promise<Exemplo[]> {
  return pedir("/api/aprender/exemplos");
}

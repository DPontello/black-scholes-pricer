import { json, pedir, type Fonte } from "./cliente";

export type Lado = "compra" | "venda";
export type OrigemAcao = "compra" | "carteira";
export type OrigemPreco = "executavel" | "indicativo" | "teorico" | "digitado";

export type PernaPedido = { ticker: string; lado: Lado; quantidade: number; preco: number | null };
export type AcaoPedido = { lado: Lado; quantidade: number; origem: OrigemAcao; preco: number | null };
export type PedidoAnalise = {
  ativo: string;
  pernas: PernaPedido[];
  acao: AcaoPedido | null;
  modelo: string | null;
};

export type Modelo = {
  chave: string;
  familia: "renda" | "direcionais" | "volatilidade" | "protecao";
  nome: string;
  pernas: { tipo: "call" | "put"; lado: Lado; proporcao: number; passo: number }[];
  acao: Lado | null;
};

export type PernaAnalise = {
  ticker: string;
  tipo: "call" | "put";
  strike: number;
  estilo: "american" | "european";
  lado: Lado;
  quantidade: number;
  lote: number | null;
  preco: number | null;
  origem: OrigemPreco | null;
};

/** Valores em reais; `null` nos máximos é ilimitado. */
export type NoVencimento = {
  caixa: number;
  breakevens: number[];
  ganho_max: number | null;
  perda_max: number | null;
  ganho_max_liquido: number | null;
  perda_max_liquida: number | null;
  custos_montagem: number;
  ir_no_ganho_max: number | null;
  probabilidade: number;
};

export type Hoje = {
  curva: { spot: number; resultado: number }[];
  gregas: { delta: number; gamma: number; theta_dia_util: number; vega_ponto: number; rho: number };
  grade: {
    choques_spot: number[];
    choques_vol: number[];
    spots: number[];
    valores: (number | null)[][];
  };
  call_americana_aproximada: boolean;
};

export type Analise = {
  nome: string;
  ativo: string;
  vencimento: string;
  dias_uteis: number;
  spot: number;
  fonte: Fonte;
  hora: string;
  pernas: PernaAnalise[];
  acao: {
    ticker: string;
    lado: Lado;
    quantidade: number;
    origem: OrigemAcao;
    preco: number | null;
    origem_preco: OrigemPreco | null;
  } | null;
  curva: { spot: number; payoff: number; resultado: number | null; liquido: number | null }[];
  no_vencimento: NoVencimento | null;
  hoje: Hoje | null;
  hoje_indisponivel: string | null;
  avisos: string[];
};

export type Simulacao = { id: string; nome: string; criada_em: string; pedido: PedidoAnalise };

export function listarModelos(): Promise<Modelo[]> {
  return pedir("/api/montador/modelos");
}

export function sugerir(ativo: string, modelo: string, vencimento: string): Promise<PedidoAnalise> {
  const busca = new URLSearchParams({ ativo, modelo, vencimento });
  return pedir(`/api/montador/sugestao?${busca.toString()}`);
}

export function analisar(pedido: PedidoAnalise): Promise<Analise> {
  return pedir("/api/montador/analise", json("POST", pedido));
}

export function listarSimulacoes(): Promise<{
  simulacoes: Simulacao[];
  ilegiveis: { arquivo: string; motivo: string }[];
}> {
  return pedir("/api/simulacoes");
}

export function salvarSimulacao(nome: string, pedido: PedidoAnalise): Promise<Simulacao> {
  return pedir("/api/simulacoes", json("POST", { nome, ...pedido }));
}

export function apagarSimulacao(id: string): Promise<void> {
  return pedir(`/api/simulacoes/${encodeURIComponent(id)}`, { method: "DELETE" });
}

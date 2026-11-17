// /api/alertas: a lista (também no WebSocket), dispensar, restaurar e a sugestão de rolagem.

import { type Fonte, pedir } from "./cliente";
import type { PedidoAnalise } from "./montador";

export type TipoAlerta =
  | "exercicio_a_registrar"
  | "stop"
  | "stop_sem_preco"
  | "strike_mudou"
  | "risco_de_exercicio"
  | "vencimento_proximo"
  | "aguardando_fechamento"
  | "alvo";

/** `perna` é null no stop e no alvo (alertas da operação inteira). `estimado`: o total do stop
 * saiu do teórico de uma perna sem oferta para zerar. `strike` e `strike_cadastro`: só no strike
 * que mudou no Cadastro (o em vigor e o do Cadastro). */
export type Alerta = {
  chave: string;
  tipo: TipoAlerta;
  operacao: string;
  nome: string;
  ativo: string;
  perna: number | null;
  ticker: string | null;
  vencimento: string | null;
  dias_uteis: number | null;
  dentro_do_dinheiro: boolean | null;
  total: number | null;
  limite: number | null;
  pode_rolar: boolean;
  estimado: boolean;
  strike: number | null;
  strike_cadastro: number | null;
};

/** Um alerta que não pôde ser avaliado agora; `perna` e `ticker` são null no stop e no alvo. */
export type NaoAvaliado = {
  chave: string;
  tipo: TipoAlerta;
  operacao: string;
  nome: string;
  ativo: string;
  perna: number | null;
  ticker: string | null;
  motivo: "sem_spot" | "sem_preco" | "fora_do_calendario";
};

/** Já na ordem de gravidade; `dispensados`: quantos estão escondidos agora; `nao_avaliados`: os
 * que não deu para avaliar, dispensados inclusive. */
export type Alertas = { fonte: Fonte; alertas: Alerta[]; dispensados: number; nao_avaliados: NaoAvaliado[] };

/** `pedido` null: operação sem modelo ou sem vencimento seguinte. Caixa: + recebe, − paga. */
export type Rolagem = {
  operacao: string;
  nome: string;
  ativo: string;
  vencimento_atual: string;
  vencimento_novo: string | null;
  pedido: PedidoAnalise | null;
  caixa_de_zerar: number | null;
  fonte: Fonte;
};

export function lerAlertas(): Promise<Alertas> {
  return pedir<Alertas>("/api/alertas");
}

export function dispensarAlerta(chave: string): Promise<void> {
  return pedir<void>(`/api/alertas/${encodeURIComponent(chave)}/dispensar`, { method: "POST" });
}

export function restaurarAlertas(): Promise<void> {
  return pedir<void>("/api/alertas/restaurar", { method: "POST" });
}

export function lerRolagem(operacao: string): Promise<Rolagem> {
  return pedir<Rolagem>(`/api/alertas/rolagem/${encodeURIComponent(operacao)}`);
}

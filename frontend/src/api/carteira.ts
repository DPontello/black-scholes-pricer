import { json, pedir, type Fonte } from "./cliente";
import type { Analise, Lado, OrigemAcao, PedidoAnalise } from "./montador";

/** `preco` é o de zerar (bid na comprada, ask na vendida); sem ele, `teorico` fica ao lado, fora do total. */
export type Marca = {
  preco: number | null;
  nao_realizado: number | null;
  teorico: number | null;
  motivo: string | null;
};

export type PernaCarteira = {
  indice: number;
  ticker: string;
  tipo: "call" | "put" | "acao";
  strike: number | null;
  vencimento: string | null;
  estilo: "american" | "european" | null;
  origem: OrigemAcao | null;
  lado: Lado | null;
  quantidade: number;
  preco_medio: number;
  realizado: number;
  marca: Marca | null;
};

export type Evento = {
  tipo: "abertura" | "encerramento" | "exercicio" | "atribuicao" | "po" | "transferencia";
  perna: number;
  data: string;
  lado: Lado | null;
  quantidade: number | null;
  preco: number | null;
  custos: number | null;
  custo_medio: number | null;
  para: string | null;
};

export type OperacaoCarteira = {
  id: string;
  ativo: string;
  nome: string;
  criada_em: string;
  pernas: PernaCarteira[];
  eventos: Evento[];
  realizado: number;
  /** `null` quando alguma perna aberta está sem preço de zerar. */
  nao_realizado: number | null;
};

export type TotalAtivo = {
  ticker: string;
  lado: Lado;
  quantidade: number;
  preco_medio: number;
  marca: Marca;
};

export type AvisoVencimento = {
  operacao: string;
  perna: number;
  ticker: string;
  vencimento: string;
  situacao: "registrar_exercicio" | "aguardando_fechamento";
};

export type Carteira = {
  fonte: Fonte;
  operacoes: OperacaoCarteira[];
  totais: TotalAtivo[];
  avisos: AvisoVencimento[];
  ilegiveis: { arquivo: string; motivo: string }[];
};

/** Rascunho do formulário: preço `null` é o que o usuário ainda tem de preencher. */
export type ExecucaoRascunho = { quantidade: number; preco: number | null; custos: number | null };
export type RascunhoOperacao = {
  ativo: string;
  nome: string;
  data: string;
  pernas: { ticker: string; lado: Lado; execucoes: ExecucaoRascunho[] }[];
  acao: { lado: Lado; origem: OrigemAcao; execucoes: ExecucaoRascunho[] } | null;
};

type Salva = { id: string };

export function lerCarteira(): Promise<Carteira> {
  return pedir("/api/carteira");
}

export function lerHistorico(): Promise<OperacaoCarteira[]> {
  return pedir("/api/carteira/historico");
}

export function registrarOperacao(corpo: RascunhoOperacao): Promise<Salva> {
  return pedir("/api/carteira/operacoes", json("POST", corpo));
}

export function adicionarAcoes(corpo: {
  ativo: string;
  quantidade: number;
  preco_medio: number;
  data: string;
}): Promise<Salva> {
  return pedir("/api/carteira/acoes", json("POST", corpo));
}

type EventoPedido = { perna: number; quantidade: number; data: string; custos: number | null };

export function encerrar(id: string, corpo: EventoPedido & { preco: number }): Promise<Salva> {
  return pedir(`/api/carteira/operacoes/${encodeURIComponent(id)}/encerrar`, json("POST", corpo));
}

export function exercer(id: string, corpo: EventoPedido): Promise<Salva> {
  return pedir(`/api/carteira/operacoes/${encodeURIComponent(id)}/exercer`, json("POST", corpo));
}

export function atribuir(id: string, corpo: EventoPedido): Promise<Salva> {
  return pedir(`/api/carteira/operacoes/${encodeURIComponent(id)}/atribuir`, json("POST", corpo));
}

export function rascunhoVazio(data: string): RascunhoOperacao {
  return { ativo: "", nome: "", data, pernas: [], acao: null };
}

// O que o montador mostrou vira o ponto de partida: o usuário confere com a nota da corretora.
export function rascunhoDaAnalise(
  pedido: PedidoAnalise,
  analise: Analise | null,
  data: string,
): RascunhoOperacao {
  const acao = pedido.acao;
  return {
    ativo: pedido.ativo,
    nome: analise?.nome ?? "",
    data,
    pernas: pedido.pernas.map((perna, i) => ({
      ticker: perna.ticker,
      lado: perna.lado,
      execucoes: [
        { quantidade: perna.quantidade, preco: analise?.pernas[i]?.preco ?? perna.preco, custos: null },
      ],
    })),
    acao:
      acao === null
        ? null
        : {
            lado: acao.lado,
            origem: acao.origem,
            execucoes:
              acao.origem === "carteira"
                ? []
                : [
                    {
                      quantidade: acao.quantidade,
                      preco: analise?.acao?.preco ?? acao.preco,
                      custos: null,
                    },
                  ],
          },
  };
}

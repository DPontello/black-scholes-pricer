import type { Book, ItemBook } from "../api/book";
import type { Perfil, PresetBook } from "../api/cliente";

export const MODERADO: PresetBook = {
  preset: "moderado",
  delta_min: 0.15,
  delta_max: 0.35,
  negocios_min: 10,
  spread_max: 0.2,
  risco_max: 3000,
  vencimentos: 2,
  piso_protecao: 0.9,
  perda_ilimitada: false,
};

export const PERFIL: Perfil = { nome: "Hugo", ativos: ["PETR4", "VALE3"], cdi_anual: 0.15, book: MODERADO };

export function itemCoberta(extra: Partial<ItemBook> = {}): ItemBook {
  return {
    familia: "renda",
    estrutura: "venda_coberta",
    nome: "venda coberta",
    ativo: "PETR4",
    vencimento: "2026-11-19",
    dias_uteis: 18,
    pernas: [
      {
        ticker: "PETRK320",
        tipo: "call",
        strike: 32,
        lado: "venda",
        quantidade: 100,
        premio: 0.41,
        qualidade: "executavel",
      },
    ],
    acao: { lado: "compra", quantidade: 100, origem: "compra" },
    qualidade: "executavel",
    criterio: {
      chave: "anual_liquido",
      rotulo: "anualizado líquido",
      valor: 0.124,
      unidade: "percentual",
      texto: "12,4%",
    },
    numeros: [
      { chave: "premio", rotulo: "prêmio por ação", valor: 0.41, unidade: "reais", texto: "R$ 0,41" },
    ],
    porque: "Venda coberta de PETRK320: o prêmio de R$ 0,41 por ação rende 12,4% ao ano.",
    porque_curto: "Renda com as suas ações: recebe o prêmio e aceita vender no strike.",
    rotulos: [],
    pedido: {
      ativo: "PETR4",
      pernas: [{ ticker: "PETRK320", lado: "venda", quantidade: 100, preco: null }],
      acao: { lado: "compra", quantidade: 100, origem: "compra", preco: null },
      modelo: "venda_coberta",
    },
    resultado: {
      ganha_ate: 350.11,
      perde_ate: 16433.11,
      chance_de_lucro: 0.62,
      ganha_ate_texto: "R$ 350,11",
      perde_ate_texto: "R$ 16.433,11",
      chance_texto: "62,0%",
    },
    ...extra,
  };
}

export function bookFalso(extra: Partial<Book> = {}): Book {
  const vazia = { itens: [], referencias: [], exclusoes: [] };
  return {
    pregao: "2026-10-23",
    fonte: "fim_de_dia",
    preset: MODERADO,
    contextos: [
      {
        ativo: "PETR4",
        iv30: 0.3,
        hv21: 0.4,
        iv_rank: 0.12,
        iv_percentil: 0.08,
        regime: "baixa",
        regime_pela_hv: false,
        extrapolada: false,
        motivo: null,
      },
      {
        ativo: "VALE3",
        iv30: null,
        hv21: null,
        iv_rank: null,
        iv_percentil: null,
        regime: null,
        regime_pela_hv: false,
        extrapolada: false,
        motivo: "VALE3: sem histórico de IV",
      },
    ],
    familias: {
      renda: {
        itens: [itemCoberta()],
        referencias: [
          itemCoberta({
            nome: "put coberta",
            estrutura: "put_coberta",
            qualidade: "indicativo",
            pernas: [
              {
                ticker: "PETRW280",
                tipo: "put",
                strike: 28,
                lado: "venda",
                quantidade: 100,
                premio: 0.3,
                qualidade: "indicativo",
              },
            ],
            acao: null,
            pedido: {
              ativo: "PETR4",
              pernas: [{ ticker: "PETRW280", lado: "venda", quantidade: 100, preco: null }],
              acao: null,
              modelo: "put_coberta",
            },
          }),
        ],
        exclusoes: [{ simbolo: "PETRL340/?", motivo: "sem strike 1 passo mais fora" }],
      },
      volatilidade: vazia,
      direcionais: vazia,
      protecao: vazia,
    },
    indisponiveis: [],
    ...extra,
  };
}

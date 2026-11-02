import type { Analise } from "../api/montador";

// Venda coberta de PETR4 com a PETRK541 (os números do teste com os arquivos reais de 28/10).
export function analiseCoberta(parcial: Partial<Analise> = {}): Analise {
  return {
    nome: "venda coberta",
    ativo: "PETR4",
    vencimento: "2026-11-19",
    dias_uteis: 15,
    spot: 52.51,
    fonte: "fim_de_dia",
    hora: "2026-10-28T18:00:00-03:00",
    pernas: [
      {
        ticker: "PETRK541",
        tipo: "call",
        strike: 52.91,
        estilo: "american",
        lado: "venda",
        quantidade: 100,
        lote: 100,
        preco: 1.72,
        origem: "executavel",
      },
    ],
    acao: {
      ticker: "PETR4",
      lado: "compra",
      quantidade: 100,
      origem: "compra",
      preco: 52.52,
      origem_preco: "executavel",
    },
    curva: [
      { spot: 26.25, payoff: 2625, resultado: -2455, liquido: -2456.81 },
      { spot: 52.51, payoff: 5251, resultado: 171, liquido: 143.6 },
      { spot: 78.76, payoff: 5291, resultado: 211, liquido: 177.6 },
    ],
    no_vencimento: {
      caixa: -5080,
      breakevens: [50.8],
      ganho_max: 211,
      perda_max: -5080,
      ganho_max_liquido: 183.43,
      perda_max_liquida: -5081.81,
      custos_montagem: 1.81,
      ir_no_ganho_max: 25.77,
      probabilidade: 0.68,
    },
    hoje: {
      curva: [
        { spot: 26.25, resultado: -2470 },
        { spot: 52.51, resultado: -12 },
        { spot: 78.76, resultado: 205 },
      ],
      gregas: { delta: 47.94, gamma: -8.77, theta_dia_util: 7.45, vega_ponto: -5.1, rho: -151.8 },
      grade: {
        choques_spot: [-0.2, 0, 0.2],
        choques_vol: [-0.1, 0, 0.1],
        spots: [42.01, 52.51, 63.01],
        valores: [
          [-1040, -1050, null],
          [10, -12, -40],
          [200, 190, 170],
        ],
      },
      call_americana_aproximada: true,
    },
    hoje_indisponivel: null,
    avisos: [
      "opção americana: o resultado no vencimento supõe que não há exercício antecipado",
      "call americana avaliada hoje como europeia (ADR-0002)",
    ],
    ...parcial,
  };
}

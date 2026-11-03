import type { Exemplo, PernaExemplo } from "../api/aprender";
import type { Familia } from "../api/book";

type Perna = [PernaExemplo["tipo"], PernaExemplo["lado"], number, number, number];

type Linha = {
  chave: string;
  nome: string;
  familia: Familia;
  pernas: Perna[];
  acoes: number;
  premioLiquido: number;
  // O resultado a R$ 45, R$ 50 e R$ 55.
  resultados: [number, number, number];
  empates: number[];
  ganhoMaximo: number | null;
  perdaMaxima: number | null;
};

// A curva é curta de propósito: dá ao gráfico pontos dentro e fora da janela; os números do resto
// são os do exemplo real (PETR4 a R$ 50,00), na ordem do catálogo.
function exemplo(l: Linha): Exemplo {
  const [abaixo, parado, acima] = l.resultados;
  return {
    chave: l.chave,
    nome: l.nome,
    familia: l.familia,
    spot: 50,
    pernas: l.pernas.map(([tipo, lado, strike, premio, quantidade]) => ({
      tipo,
      lado,
      strike,
      premio,
      quantidade,
    })),
    acoes: l.acoes,
    premio_liquido: l.premioLiquido,
    cenarios: [
      { preco: 45, resultado: abaixo },
      { preco: 50, resultado: parado },
      { preco: 55, resultado: acima },
    ],
    empates: l.empates,
    ganho_maximo: l.ganhoMaximo,
    perda_maxima: l.perdaMaxima,
    curva: [
      [30, abaixo],
      [45, abaixo],
      [50, parado],
      [55, acima],
      [70, acima],
    ],
  };
}

export const EXEMPLOS: Exemplo[] = [
  exemplo({
    chave: "venda_coberta",
    nome: "venda coberta",
    familia: "renda",
    pernas: [["call", "venda", 52, 1.14, 100]],
    acoes: 100,
    premioLiquido: 114,
    resultados: [-386, 114, 314],
    empates: [48.86],
    ganhoMaximo: 314,
    perdaMaxima: 4886,
  }),
  exemplo({
    chave: "put_coberta",
    nome: "put coberta",
    familia: "renda",
    pernas: [["put", "venda", 48, 0.7, 100]],
    acoes: 0,
    premioLiquido: 70,
    resultados: [-230, 70, 70],
    empates: [47.3],
    ganhoMaximo: 70,
    perdaMaxima: 4730,
  }),
  exemplo({
    chave: "trava_alta_put",
    nome: "trava de alta com put",
    familia: "renda",
    pernas: [
      ["put", "compra", 46, 0.28, 100],
      ["put", "venda", 48, 0.7, 100],
    ],
    acoes: 0,
    premioLiquido: 42,
    resultados: [-158, 42, 42],
    empates: [47.58],
    ganhoMaximo: 42,
    perdaMaxima: 158,
  }),
  exemplo({
    chave: "trava_baixa_call",
    nome: "trava de baixa com call",
    familia: "renda",
    pernas: [
      ["call", "venda", 52, 1.14, 100],
      ["call", "compra", 54, 0.58, 100],
    ],
    acoes: 0,
    premioLiquido: 56,
    resultados: [56, 56, -144],
    empates: [52.56],
    ganhoMaximo: 56,
    perdaMaxima: 144,
  }),
  exemplo({
    chave: "compra_call",
    nome: "compra de call",
    familia: "direcionais",
    pernas: [["call", "compra", 50, 2.02, 100]],
    acoes: 0,
    premioLiquido: -202,
    resultados: [-202, -202, 298],
    empates: [52.02],
    ganhoMaximo: null,
    perdaMaxima: 202,
  }),
  exemplo({
    chave: "compra_put",
    nome: "compra de put",
    familia: "direcionais",
    pernas: [["put", "compra", 50, 1.44, 100]],
    acoes: 0,
    premioLiquido: -144,
    resultados: [356, -144, -144],
    empates: [48.56],
    ganhoMaximo: 4856,
    perdaMaxima: 144,
  }),
  exemplo({
    chave: "trava_alta_call",
    nome: "trava de alta com call",
    familia: "direcionais",
    pernas: [
      ["call", "compra", 50, 2.02, 100],
      ["call", "venda", 52, 1.14, 100],
    ],
    acoes: 0,
    premioLiquido: -88,
    resultados: [-88, -88, 112],
    empates: [50.88],
    ganhoMaximo: 112,
    perdaMaxima: 88,
  }),
  exemplo({
    chave: "trava_baixa_put",
    nome: "trava de baixa com put",
    familia: "direcionais",
    pernas: [
      ["put", "venda", 48, 0.7, 100],
      ["put", "compra", 50, 1.44, 100],
    ],
    acoes: 0,
    premioLiquido: -74,
    resultados: [126, -74, -74],
    empates: [49.26],
    ganhoMaximo: 126,
    perdaMaxima: 74,
  }),
  exemplo({
    chave: "straddle_comprado",
    nome: "straddle comprado",
    familia: "volatilidade",
    pernas: [
      ["call", "compra", 50, 2.02, 100],
      ["put", "compra", 50, 1.44, 100],
    ],
    acoes: 0,
    premioLiquido: -346,
    resultados: [154, -346, 154],
    empates: [46.54, 53.46],
    ganhoMaximo: null,
    perdaMaxima: 346,
  }),
  exemplo({
    chave: "straddle_vendido",
    nome: "straddle vendido",
    familia: "volatilidade",
    pernas: [
      ["call", "venda", 50, 2.02, 100],
      ["put", "venda", 50, 1.44, 100],
    ],
    acoes: 0,
    premioLiquido: 346,
    resultados: [-154, 346, -154],
    empates: [46.54, 53.46],
    ganhoMaximo: 346,
    perdaMaxima: null,
  }),
  exemplo({
    chave: "strangle_comprado",
    nome: "strangle comprado",
    familia: "volatilidade",
    pernas: [
      ["put", "compra", 48, 0.7, 100],
      ["call", "compra", 52, 1.14, 100],
    ],
    acoes: 0,
    premioLiquido: -184,
    resultados: [116, -184, 116],
    empates: [46.16, 53.84],
    ganhoMaximo: null,
    perdaMaxima: 184,
  }),
  exemplo({
    chave: "strangle_vendido",
    nome: "strangle vendido",
    familia: "volatilidade",
    pernas: [
      ["put", "venda", 48, 0.7, 100],
      ["call", "venda", 52, 1.14, 100],
    ],
    acoes: 0,
    premioLiquido: 184,
    resultados: [-116, 184, -116],
    empates: [46.16, 53.84],
    ganhoMaximo: 184,
    perdaMaxima: null,
  }),
  exemplo({
    chave: "iron_condor_vendido",
    nome: "iron condor vendido",
    familia: "volatilidade",
    pernas: [
      ["put", "compra", 46, 0.28, 100],
      ["put", "venda", 48, 0.7, 100],
      ["call", "venda", 52, 1.14, 100],
      ["call", "compra", 54, 0.58, 100],
    ],
    acoes: 0,
    premioLiquido: 98,
    resultados: [-102, 98, -102],
    empates: [47.02, 52.98],
    ganhoMaximo: 98,
    perdaMaxima: 102,
  }),
  exemplo({
    chave: "iron_condor_comprado",
    nome: "iron condor comprado",
    familia: "volatilidade",
    pernas: [
      ["put", "venda", 46, 0.28, 100],
      ["put", "compra", 48, 0.7, 100],
      ["call", "compra", 52, 1.14, 100],
      ["call", "venda", 54, 0.58, 100],
    ],
    acoes: 0,
    premioLiquido: -98,
    resultados: [102, -98, 102],
    empates: [47.02, 52.98],
    ganhoMaximo: 102,
    perdaMaxima: 98,
  }),
  exemplo({
    chave: "borboleta_comprada",
    nome: "borboleta comprada",
    familia: "volatilidade",
    pernas: [
      ["call", "compra", 48, 3.26, 100],
      ["call", "venda", 50, 2.02, 200],
      ["call", "compra", 52, 1.14, 100],
    ],
    acoes: 0,
    premioLiquido: -36,
    resultados: [-36, 164, -36],
    empates: [48.36, 51.64],
    ganhoMaximo: 164,
    perdaMaxima: 36,
  }),
  exemplo({
    chave: "borboleta_vendida",
    nome: "borboleta vendida",
    familia: "volatilidade",
    pernas: [
      ["call", "venda", 48, 3.26, 100],
      ["call", "compra", 50, 2.02, 200],
      ["call", "venda", 52, 1.14, 100],
    ],
    acoes: 0,
    premioLiquido: 36,
    resultados: [36, -164, 36],
    empates: [48.36, 51.64],
    ganhoMaximo: 36,
    perdaMaxima: 164,
  }),
  exemplo({
    chave: "put_protetora",
    nome: "put protetora",
    familia: "protecao",
    pernas: [["put", "compra", 48, 0.7, 100]],
    acoes: 100,
    premioLiquido: -70,
    resultados: [-270, -70, 430],
    empates: [50.7],
    ganhoMaximo: null,
    perdaMaxima: 270,
  }),
  exemplo({
    chave: "collar",
    nome: "collar",
    familia: "protecao",
    pernas: [
      ["put", "compra", 48, 0.7, 100],
      ["call", "venda", 52, 1.14, 100],
    ],
    acoes: 100,
    premioLiquido: 44,
    resultados: [-156, 44, 244],
    empates: [49.56],
    ganhoMaximo: 244,
    perdaMaxima: 156,
  }),
];

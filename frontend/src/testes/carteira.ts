import type { Carteira, OperacaoCarteira, PernaCarteira } from "../api/carteira";

// Trava de alta de PETR4 marcada: a comprada sem bid (só o teórico) e a vendida pelo ask.
export function perna(parcial: Partial<PernaCarteira> = {}): PernaCarteira {
  return {
    indice: 0,
    ticker: "PETRK300",
    tipo: "call",
    strike: 30,
    vencimento: "2026-11-19",
    estilo: "european",
    origem: null,
    lado: "compra",
    quantidade: 100,
    preco_medio: 1.2,
    realizado: 0,
    marca: { preco: null, nao_realizado: null, teorico: 1.23, motivo: "sem oferta de compra para zerar" },
    ...parcial,
  };
}

export function trava(parcial: Partial<OperacaoCarteira> = {}): OperacaoCarteira {
  return {
    id: "op1",
    ativo: "PETR4",
    nome: "trava de alta",
    criada_em: "2026-11-04",
    pernas: [
      perna(),
      perna({
        indice: 1,
        ticker: "PETRK320",
        strike: 32,
        lado: "venda",
        preco_medio: 0.6,
        marca: { preco: 0.45, nao_realizado: 15, teorico: null, motivo: null },
      }),
    ],
    eventos: [
      {
        tipo: "abertura",
        perna: 0,
        data: "2026-11-04",
        lado: "compra",
        quantidade: 100,
        preco: 1.2,
        custos: null,
        custo_medio: null,
        para: null,
      },
    ],
    realizado: -10.12,
    nao_realizado: null,
    ...parcial,
  };
}

export function carteira(parcial: Partial<Carteira> = {}): Carteira {
  return {
    fonte: "ao_vivo",
    operacoes: [trava()],
    totais: [
      {
        ticker: "PETR4",
        lado: "compra",
        quantidade: 200,
        preco_medio: 29,
        marca: { preco: 30, nao_realizado: 200, teorico: null, motivo: null },
      },
      {
        ticker: "PETRK320",
        lado: "venda",
        quantidade: 300,
        preco_medio: 0.6,
        marca: { preco: 0.45, nao_realizado: 45, teorico: null, motivo: null },
      },
      {
        ticker: "PETRK300",
        lado: "compra",
        quantidade: 100,
        preco_medio: 1.2,
        marca: { preco: null, nao_realizado: null, teorico: 1.23, motivo: "sem oferta de compra para zerar" },
      },
    ],
    avisos: [],
    ilegiveis: [],
    ...parcial,
  };
}

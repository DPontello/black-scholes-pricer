import type { Carteira, MesIr, OperacaoCarteira, PernaCarteira } from "../api/carteira";

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

// Novembro do exemplo conferido à mão: base comum 85 (137 menos os 52 de outubro), 12,75 de IR
// mais os 5,60 que vieram de outubro dão os 18,35 do DARF.
export function mesIr(parcial: Partial<MesIr> = {}): MesIr {
  return {
    mes: "2026-11",
    comum: 137,
    day_trade: 0,
    base_comum: 85,
    base_day_trade: 0,
    prejuizo_comum: 0,
    prejuizo_day_trade: 0,
    ir_do_mes: 12.75,
    ir_de_antes: 5.6,
    ir_a_pagar: 18.35,
    ir_para_depois: 0,
    pagar_ate: "2026-12-30",
    pecas: [
      {
        data: "2026-11-12",
        ticker: "PETRW280",
        categoria: "comum",
        tipo: "encerramento",
        resultado: 58,
        operacoes: ["venda de put"],
      },
      {
        data: "2026-11-19",
        ticker: "PETRW280",
        categoria: "comum",
        tipo: "po",
        resultado: 79,
        operacoes: ["venda de put"],
      },
    ],
    exercicios: [{ data: "2026-11-19", ticker: "PETRK320", operacao: "call exercida" }],
    ...parcial,
  };
}

// Outubro: o prejuízo comum de 52 abate o ganho de novembro; o day trade de 28 dá 5,60, abaixo de R$ 10.
export function mesIrOutubro(parcial: Partial<MesIr> = {}): MesIr {
  return {
    mes: "2026-10",
    comum: -52,
    day_trade: 28,
    base_comum: 0,
    base_day_trade: 28,
    prejuizo_comum: 52,
    prejuizo_day_trade: 0,
    ir_do_mes: 5.6,
    ir_de_antes: 0,
    ir_a_pagar: 0,
    ir_para_depois: 5.6,
    pagar_ate: null,
    pecas: [
      {
        data: "2026-10-01",
        ticker: "PETRK300",
        categoria: "day_trade",
        tipo: "encerramento",
        resultado: 28,
        operacoes: ["call de outubro"],
      },
      {
        data: "2026-10-15",
        ticker: "PETRK300",
        categoria: "comum",
        tipo: "encerramento",
        resultado: -52,
        operacoes: ["call de outubro"],
      },
    ],
    exercicios: [],
    ...parcial,
  };
}

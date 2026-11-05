import type { Alerta, Alertas, Rolagem } from "../api/alertas";

// Put vendida de PETR4 perto do strike a 2 du do vencimento, e uma operação de ações no stop.
export function alerta(parcial: Partial<Alerta> = {}): Alerta {
  return {
    chave: "vencimento_proximo:op1:0",
    tipo: "vencimento_proximo",
    operacao: "op1",
    nome: "put coberta",
    ativo: "PETR4",
    perna: 0,
    ticker: "PETRW280",
    vencimento: "2026-11-19",
    dias_uteis: 2,
    dentro_do_dinheiro: null,
    total: null,
    limite: null,
    pode_rolar: true,
    ...parcial,
  };
}

export function alertas(parcial: Partial<Alertas> = {}): Alertas {
  return {
    fonte: "ao_vivo",
    alertas: [
      alerta({
        chave: "stop:op2:-",
        tipo: "stop",
        operacao: "op2",
        nome: "ações à mão",
        perna: null,
        ticker: null,
        vencimento: null,
        dias_uteis: null,
        total: -210,
        limite: 200,
        pode_rolar: false,
      }),
      alerta({
        chave: "risco_de_exercicio:op1:0",
        tipo: "risco_de_exercicio",
        dentro_do_dinheiro: false,
      }),
      alerta(),
    ],
    dispensados: 0,
    ...parcial,
  };
}

export function rolagem(parcial: Partial<Rolagem> = {}): Rolagem {
  return {
    operacao: "op1",
    nome: "put coberta",
    ativo: "PETR4",
    vencimento_atual: "2026-11-19",
    vencimento_novo: "2026-12-17",
    pedido: {
      ativo: "PETR4",
      pernas: [{ ticker: "PETRX280", lado: "venda", quantidade: 100, preco: null }],
      acao: null,
      modelo: "put_coberta",
    },
    caixa_de_zerar: -35,
    fonte: "ao_vivo",
    ...parcial,
  };
}

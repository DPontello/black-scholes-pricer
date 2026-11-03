import type { AnaliseMercado } from "../api/analise";

export function analiseMercado(extra: Partial<AnaliseMercado> = {}): AnaliseMercado {
  return {
    ativo: "PETR4",
    spot: 30,
    cdi_anual: 0.15,
    fonte: "fim_de_dia",
    hora: "2026-10-23T18:00:00-03:00",
    historico: [
      { pregao: "2026-10-21", fechamento: 29.5, iv30: 0.32, extrapolada: false, hv21: 0.28 },
      { pregao: "2026-10-22", fechamento: 29.8, iv30: null, extrapolada: false, hv21: 0.29 },
      { pregao: "2026-10-23", fechamento: 30, iv30: 0.31, extrapolada: true, hv21: null },
    ],
    historico_motivo: null,
    hoje: {
      iv30: 0.3,
      hv21: 0.4,
      iv_rank: 0.12,
      iv_percentil: 0.08,
      regime: "baixa",
      regime_pela_hv: false,
      extrapolada: false,
    },
    hoje_motivo: null,
    smiles: [
      {
        vencimento: "2026-11-19",
        dias_uteis: 18,
        pontos: [
          { strike: 28, iv: 0.31, ticker: "PETRW280" },
          { strike: 32, iv: 0.29, ticker: "PETRK320" },
        ],
      },
      {
        vencimento: "2026-12-18",
        dias_uteis: 38,
        pontos: [{ strike: 30, iv: 0.3, ticker: "PETRL300" }],
      },
    ],
    estrutura: [
      { vencimento: "2026-11-19", dias_uteis: 18, iv: 0.3 },
      { vencimento: "2026-12-18", dias_uteis: 38, iv: 0.3 },
    ],
    ...extra,
  };
}

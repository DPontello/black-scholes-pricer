import { render, screen } from "@testing-library/react";
import * as echarts from "echarts/core";
import { expect, test, vi } from "vitest";

import { analiseMercado } from "../testes/analiseMercado";
import { GraficoVol, seriesDoHistorico } from "./GraficoVol";

test("buracos viram null e a IV extrapolada vem marcada", () => {
  const series = seriesDoHistorico(analiseMercado().historico);
  expect(series.datas).toEqual(["2026-10-21", "2026-10-22", "2026-10-23"]);
  expect(series.fechamento).toEqual([29.5, 29.8, 30]);
  expect(series.iv30).toEqual([0.32, null, { value: 0.31, symbol: "triangle", symbolSize: 7 }]);
  expect(series.hv21).toEqual([0.28, 0.29, null]);
});

test("fica só com o último ano de pregões", () => {
  const pregao = analiseMercado().historico[0]!;
  const longo = Array.from({ length: 300 }, (_, i) => ({ ...pregao, fechamento: i }));
  const series = seriesDoHistorico(longo);
  expect(series.fechamento.length).toBe(252);
  expect(series.fechamento[0]).toBe(48);
});

test("desenha no ECharts com as três séries", () => {
  render(<GraficoVol ativo="PETR4" historico={analiseMercado().historico} />);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("IV 30 contra HV 21");
  const instancia = vi.mocked(echarts.init).mock.results.at(-1)?.value as {
    setOption: ReturnType<typeof vi.fn>;
  };
  const opcoes = instancia.setOption.mock.calls.at(-1)?.[0] as { series: { name: string }[] };
  expect(opcoes.series.map((s) => s.name)).toEqual(["Fechamento", "IV 30 (▲ extrapolada)", "HV 21"]);
});

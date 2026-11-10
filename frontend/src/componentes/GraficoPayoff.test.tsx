import { render, screen } from "@testing-library/react";
import * as echarts from "echarts/core";
import { expect, test, vi } from "vitest";

import { analiseCoberta } from "../testes/analise";
import { faixaDoEixo, GraficoPayoff, seriesDoGrafico } from "./GraficoPayoff";

test("séries: vencimento bruto (sem custos nem IR) e hoje tracejado", () => {
  const series = seriesDoGrafico(analiseCoberta());
  expect(series.map((s) => [s.nome, s.tracejada, s.pontos.length])).toEqual([
    ["Vencimento", false, 3],
    ["Hoje", true, 3],
  ]);
  expect(series[0]!.pontos).toEqual([
    [26.25, -2455],
    [52.51, 171],
    [78.76, 211],
  ]);
  const curvaSemPreco = analiseCoberta().curva.map((p) => ({ ...p, resultado: null, liquido: null }));
  const semPreco = seriesDoGrafico(
    analiseCoberta({ curva: curvaSemPreco, no_vencimento: null, hoje: null }),
  );
  expect(semPreco.map((s) => s.nome)).toEqual(["Vencimento (sem prêmio)"]);
});

test("desenha no ECharts e se descreve para leitor de tela", () => {
  render(<GraficoPayoff analise={analiseCoberta()} />);
  expect(screen.getByRole("img").getAttribute("aria-label")).toBe(
    "Resultado de venda coberta conforme o preço de PETR4",
  );
  const instancia = vi.mocked(echarts.init).mock.results.at(-1)?.value as {
    setOption: ReturnType<typeof vi.fn>;
  };
  expect(instancia.setOption).toHaveBeenCalled();
});

test("o eixo abre em volta do spot, dos strikes e dos breakevens", () => {
  expect(faixaDoEixo(analiseCoberta())).toEqual([45.72, 58.2]);
});

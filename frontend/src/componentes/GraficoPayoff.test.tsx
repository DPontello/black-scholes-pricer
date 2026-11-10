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

test("o gráfico se redimensiona quando o contêiner muda sem a janela mudar, e solta o observador", () => {
  const observe = vi.fn();
  const disconnect = vi.fn();
  let aoMudar: () => void = () => {};
  class ObservadorFalso {
    observe = observe;
    disconnect = disconnect;
    constructor(callback: () => void) {
      aoMudar = callback;
    }
  }
  vi.stubGlobal("ResizeObserver", ObservadorFalso);
  const { unmount } = render(<GraficoPayoff analise={analiseCoberta()} />);
  const instancia = vi.mocked(echarts.init).mock.results.at(-1)?.value as {
    resize: ReturnType<typeof vi.fn>;
  };
  expect(observe).toHaveBeenCalledWith(screen.getByRole("img"));
  instancia.resize.mockClear();
  aoMudar();
  expect(instancia.resize).toHaveBeenCalledTimes(1);
  unmount();
  expect(disconnect).toHaveBeenCalledTimes(1);
});

test("o tooltip fica dentro do gráfico, para não criar barra horizontal no cartão", () => {
  render(<GraficoPayoff analise={analiseCoberta()} />);
  const instancia = vi.mocked(echarts.init).mock.results.at(-1)?.value as {
    setOption: ReturnType<typeof vi.fn>;
  };
  const opcoes = instancia.setOption.mock.calls[0]![0] as { tooltip: { confine?: boolean } };
  expect(opcoes.tooltip.confine).toBe(true);
});

test("o eixo abre em volta do spot, dos strikes e dos breakevens", () => {
  expect(faixaDoEixo(analiseCoberta())).toEqual([45.72, 58.2]);
});

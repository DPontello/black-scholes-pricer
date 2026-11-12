import { LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo } from "react";

import type { Analise } from "../api/montador";
import { formatarPreco } from "../formatacao";
import { useGrafico } from "./useGrafico";

echarts.use([
  LineChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
  CanvasRenderer,
]);

type Ponto = [number, number];

export function seriesDoGrafico(analise: Analise): { nome: string; pontos: Ponto[]; tracejada: boolean }[] {
  const series = [];
  const resultado = analise.curva.map((p): Ponto => [p.spot, p.resultado ?? p.payoff]);
  series.push({
    nome: analise.no_vencimento === null ? "Vencimento (sem prêmio)" : "Vencimento",
    pontos: resultado,
    tracejada: false,
  });
  if (analise.hoje !== null)
    series.push({
      nome: "Hoje",
      pontos: analise.hoje.curva.map((p): Ponto => [p.spot, p.resultado]),
      tracejada: true,
    });
  return series;
}

// A curva vai de 0,5 a 1,5 x spot; o gráfico abre em volta do que importa, com 10% de folga.
export function faixaDoEixo(analise: Analise): [number, number] {
  const marcos = [
    analise.spot,
    ...analise.pernas.map((p) => p.strike),
    ...(analise.no_vencimento?.breakevens ?? []),
  ];
  const duasCasas = (v: number) => Math.round(v * 100) / 100;
  return [duasCasas(Math.min(...marcos) * 0.9), duasCasas(Math.max(...marcos) * 1.1)];
}

function opcoes(analise: Analise): echarts.EChartsCoreOption {
  const [minimo, maximo] = faixaDoEixo(analise);
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      confine: true,
      valueFormatter: (v: unknown) => `R$ ${formatarPreco(Number(v))}`,
    },
    legend: { top: 0, textStyle: { color: "#9aa3b2" } },
    grid: { left: 64, right: 16, top: 32, bottom: 32 },
    xAxis: { type: "value", min: minimo, max: maximo, name: analise.ativo, nameLocation: "end" },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatarPreco(v) } },
    series: seriesDoGrafico(analise).map((s, i) => ({
      name: s.nome,
      type: "line",
      showSymbol: false,
      data: s.pontos.filter(([spot]) => spot >= minimo && spot <= maximo),
      lineStyle: { type: s.tracejada ? "dashed" : "solid", width: 2 },
      markLine:
        i === 0
          ? {
              symbol: "none",
              silent: true,
              data: [{ xAxis: analise.spot, name: "spot" }, { yAxis: 0 }],
            }
          : undefined,
    })),
  };
}

export function GraficoPayoff({ analise }: { analise: Analise }) {
  const div = useGrafico(useMemo(() => opcoes(analise), [analise]));
  return (
    <div
      ref={div}
      className="grafico-payoff"
      role="img"
      aria-label={`Resultado de ${analise.nome} conforme o preço de ${analise.ativo}`}
    />
  );
}

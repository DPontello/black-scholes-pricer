import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo } from "react";

import type { Pregao } from "../api/analise";
import { formatarData, formatarPreco, formatarVol } from "../formatacao";
import { useGrafico } from "./useGrafico";

echarts.use([LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const PREGOES_NO_ANO = 252;

type PontoVol = number | null | { value: number; symbol: string; symbolSize: number };

/** O último ano do histórico; pregão sem o número fica `null` (buraco, nunca interpolado), e a IV 30
 * extrapolada vem marcada com um triângulo. */
export function seriesDoHistorico(historico: Pregao[]): {
  datas: string[];
  fechamento: number[];
  iv30: PontoVol[];
  hv21: (number | null)[];
} {
  const ano = historico.slice(-PREGOES_NO_ANO);
  return {
    datas: ano.map((p) => p.pregao),
    fechamento: ano.map((p) => p.fechamento),
    iv30: ano.map((p) =>
      p.iv30 !== null && p.extrapolada ? { value: p.iv30, symbol: "triangle", symbolSize: 7 } : p.iv30,
    ),
    hv21: ano.map((p) => p.hv21),
  };
}

function opcoes(historico: Pregao[]): echarts.EChartsCoreOption {
  const s = seriesDoHistorico(historico);
  return {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis" },
    legend: { top: 0, textStyle: { color: "#9aa3b2" } },
    grid: { left: 64, right: 64, top: 32, bottom: 32 },
    xAxis: { type: "category", data: s.datas, axisLabel: { formatter: formatarData } },
    yAxis: [
      { type: "value", scale: true, name: "fechamento", axisLabel: { formatter: formatarPreco } },
      { type: "value", scale: true, name: "vol", axisLabel: { formatter: formatarVol } },
    ],
    series: [
      { name: "Fechamento", type: "line", showSymbol: false, data: s.fechamento },
      {
        name: "IV 30 (▲ extrapolada)",
        type: "line",
        yAxisIndex: 1,
        showSymbol: false,
        connectNulls: false,
        data: s.iv30,
      },
      {
        name: "HV 21",
        type: "line",
        yAxisIndex: 1,
        showSymbol: false,
        connectNulls: false,
        lineStyle: { type: "dashed" },
        data: s.hv21,
      },
    ],
  };
}

export function GraficoVol({ ativo, historico }: { ativo: string; historico: Pregao[] }) {
  const div = useGrafico(useMemo(() => opcoes(historico), [historico]));
  return (
    <div
      ref={div}
      className="grafico-analise"
      role="img"
      aria-label={`Fechamento de ${ativo} e IV 30 contra HV 21 no último ano`}
    />
  );
}

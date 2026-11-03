import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo } from "react";

import type { Exemplo } from "../api/aprender";
import { useGrafico } from "../componentes/useGrafico";
import { formatarPreco } from "../formatacao";

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

// A curva da API vai de R$ 30 a R$ 70, mas os strikes do exemplo ficam perto do preço: o gráfico abre
// em volta dele, senão a parte que ensina vira um canto pequeno e o eixo do resultado se estica.
const FOLGA = 10;

function opcoes(exemplo: Exemplo, ativo: string): echarts.EChartsCoreOption {
  const minimo = exemplo.spot - FOLGA;
  const maximo = exemplo.spot + FOLGA;
  return {
    backgroundColor: "transparent",
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: unknown) => `R$ ${formatarPreco(Number(v))}`,
    },
    grid: { left: 64, right: 16, top: 16, bottom: 32 },
    xAxis: { type: "value", min: minimo, max: maximo, name: ativo, nameLocation: "end" },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => formatarPreco(v) } },
    series: [
      {
        type: "line",
        showSymbol: false,
        data: exemplo.curva.filter(([preco]) => preco >= minimo && preco <= maximo),
        lineStyle: { width: 2 },
        markLine: {
          symbol: "none",
          silent: true,
          data: [{ xAxis: exemplo.spot, name: "preço atual" }, { yAxis: 0 }],
        },
      },
    ],
  };
}

export function GraficoExemplo({ exemplo, ativo }: { exemplo: Exemplo; ativo: string }) {
  const div = useGrafico(useMemo(() => opcoes(exemplo, ativo), [exemplo, ativo]));
  return (
    <div
      ref={div}
      className="grafico-exemplo"
      role="img"
      aria-label={`Resultado no vencimento de ${exemplo.nome}`}
    />
  );
}

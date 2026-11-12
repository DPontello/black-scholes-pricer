import { LineChart } from "echarts/charts";
import { GridComponent, MarkLineComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useMemo } from "react";

import type { PontoTermo, Smile } from "../api/analise";
import { formatarData, formatarPreco, formatarVol } from "../formatacao";
import { useGrafico } from "./useGrafico";

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

const EIXO_VOL = { type: "value", scale: true, axisLabel: { formatter: formatarVol } };

export function pontosDoSmile(smile: Smile): [number, number][] {
  return smile.pontos.map((p) => [p.strike, p.iv]);
}

function opcoesSmile(smile: Smile, spot: number): echarts.EChartsCoreOption {
  return {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", valueFormatter: (v: unknown) => formatarVol(Number(v)) },
    grid: { left: 64, right: 16, top: 24, bottom: 32 },
    xAxis: { type: "value", scale: true, name: "strike", axisLabel: { formatter: formatarPreco } },
    yAxis: EIXO_VOL,
    series: [
      {
        name: `IV ${formatarData(smile.vencimento)}`,
        type: "line",
        data: pontosDoSmile(smile),
        markLine: { symbol: "none", silent: true, data: [{ xAxis: spot, name: "spot" }] },
      },
    ],
  };
}

function opcoesTermo(estrutura: PontoTermo[]): echarts.EChartsCoreOption {
  return {
    backgroundColor: "transparent",
    tooltip: { trigger: "axis", valueFormatter: (v: unknown) => formatarVol(Number(v)) },
    grid: { left: 64, right: 16, top: 24, bottom: 32 },
    xAxis: { type: "value", name: "dias úteis" },
    yAxis: EIXO_VOL,
    series: [
      {
        name: "IV no dinheiro",
        type: "line",
        data: estrutura.map((p) => [p.dias_uteis, p.iv]),
      },
    ],
  };
}

export function GraficoSmile({ smile, spot }: { smile: Smile; spot: number }) {
  const div = useGrafico(useMemo(() => opcoesSmile(smile, spot), [smile, spot]));
  return (
    <div
      ref={div}
      className="grafico-analise"
      role="img"
      aria-label={`Smile do vencimento ${formatarData(smile.vencimento)}: IV de cada série contra o strike`}
    />
  );
}

export function GraficoTermo({ estrutura }: { estrutura: PontoTermo[] }) {
  const div = useGrafico(useMemo(() => opcoesTermo(estrutura), [estrutura]));
  return (
    <div
      ref={div}
      className="grafico-analise"
      role="img"
      aria-label="Estrutura a termo: IV no dinheiro de cada vencimento contra os dias úteis"
    />
  );
}

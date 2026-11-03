import * as echarts from "echarts/core";
import { type RefObject, useEffect, useRef } from "react";

/** Um gráfico ECharts no `div` devolvido, redesenhado quando `opcoes` muda. */
export function useGrafico(opcoes: echarts.EChartsCoreOption): RefObject<HTMLDivElement> {
  const div = useRef<HTMLDivElement>(null);
  const grafico = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (div.current === null) return;
    const instancia = echarts.init(div.current, "dark");
    grafico.current = instancia;
    const redimensionar = () => instancia.resize();
    window.addEventListener("resize", redimensionar);
    return () => {
      window.removeEventListener("resize", redimensionar);
      instancia.dispose();
      grafico.current = null;
    };
  }, []);

  useEffect(() => {
    grafico.current?.setOption(opcoes, true);
  }, [opcoes]);

  return div;
}

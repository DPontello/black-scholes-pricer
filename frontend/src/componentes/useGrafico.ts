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
    // O ECharts só mede o contêiner no init e no resize(): a largura muda sem a janela mudar
    // (coluna da cadeia, barra de rolagem). O jsdom dos testes não tem ResizeObserver.
    const observador =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => instancia.resize());
    observador?.observe(div.current);
    return () => {
      observador?.disconnect();
      instancia.dispose();
      grafico.current = null;
    };
  }, []);

  useEffect(() => {
    grafico.current?.setOption(opcoes, true);
  }, [opcoes]);

  return div;
}

// Sem os globais do Vitest, o Testing Library não desmonta sozinho entre um teste e outro.
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// O Node 25+ cria um `localStorage` global próprio, `undefined` sem --localstorage-file, e o
// Vitest 2 não troca as chaves que já existem no global: o do jsdom precisa ser posto à mão.
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: (globalThis as unknown as { jsdom: { window: Window } }).jsdom.window.localStorage,
});

afterEach(() => {
  cleanup();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// As preferências guardadas não podem vazar de um teste para o outro.
afterEach(() => {
  localStorage.clear();
});

// O jsdom não tem canvas: o ECharts vira um falso que só registra as opções recebidas.
vi.mock("echarts/core", () => ({
  use: vi.fn(),
  init: vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
}));
vi.mock("echarts/charts", () => ({ LineChart: {} }));
vi.mock("echarts/components", () => ({
  GridComponent: {},
  LegendComponent: {},
  MarkLineComponent: {},
  TooltipComponent: {},
}));
vi.mock("echarts/renderers", () => ({ CanvasRenderer: {} }));

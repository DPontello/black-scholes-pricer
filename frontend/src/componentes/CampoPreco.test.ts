import { expect, test } from "vitest";

import { numero } from "./CampoPreco";

test.each([
  ["1,30", 1.3],
  ["1.30", 1.3],
  [" 1,30 ", 1.3],
  ["R$ 1,30", 1.3],
  ["R$1,30", 1.3],
  ["r$ 1,30", 1.3],
  ["1,30 ", 1.3],
  ["1.000,50", 1000.5],
  ["R$ 1.000,50", 1000.5],
  ["1.000", 1000],
  ["12.500", 12500],
  ["-1,30", -1.3],
  ["0,5", 0.5],
  [",5", 0.5],
  ["0.500", 0.5],
  ["0.5", 0.5],
])("%j lê como %d", (texto, esperado) => {
  expect(numero(texto)).toBeCloseTo(esperado);
});

test.each(["", "   ", "abc", "1,3x", "1,2,3", "1.2.3", "R$", "0.500,50"])("%j não é número", (texto) => {
  expect(numero(texto)).toBeNull();
});

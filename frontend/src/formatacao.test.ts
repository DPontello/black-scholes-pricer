import { expect, test } from "vitest";

import {
  formatarData,
  formatarHora,
  formatarInteiro,
  formatarPercentual,
  formatarPreco,
  formatarVolume,
} from "./formatacao";

test("formatação pt-BR", () => {
  expect(formatarPreco(52.51)).toBe("52,51");
  expect(formatarPreco(1234.5)).toBe("1.234,50");
  expect(formatarPreco(null)).toBe("—");
  expect(formatarPercentual(-0.0059)).toBe("-0,59%");
  expect(formatarPercentual(0.02)).toBe("+2,00%");
  expect(formatarPercentual(null)).toBe("—");
  expect(formatarVolume(679557741)).toBe("679,6 mi");
  expect(formatarVolume(1_250_000_000)).toBe("1,3 bi");
  expect(formatarVolume(48_400)).toBe("48,4 mil");
  expect(formatarVolume(812)).toBe("812");
  expect(formatarInteiro(22704)).toBe("22.704");
  expect(formatarData("2026-11-19")).toBe("19/11/2026");
});

test("hora no fuso da B3, com a data quando não é de hoje", () => {
  const hoje = new Date("2026-10-28T15:00:00Z");
  expect(formatarHora("2026-10-28T13:05:09-03:00", hoje)).toBe("13:05:09");
  expect(formatarHora("2026-10-23T21:00:00+00:00", hoje)).toBe("23/10 18:00:00");
  expect(formatarHora(null, hoje)).toBe("—");
});

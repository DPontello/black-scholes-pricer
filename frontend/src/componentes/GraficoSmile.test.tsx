import { render, screen } from "@testing-library/react";
import * as echarts from "echarts/core";
import { expect, test, vi } from "vitest";

import { analiseMercado } from "../testes/analiseMercado";
import { GraficoSmile, GraficoTermo, pontosDoSmile } from "./GraficoSmile";

type Opcoes = { series: { data: unknown }[] };

function ultimasOpcoes(): Opcoes {
  const instancia = vi.mocked(echarts.init).mock.results.at(-1)?.value as {
    setOption: ReturnType<typeof vi.fn>;
  };
  return instancia.setOption.mock.calls.at(-1)?.[0] as Opcoes;
}

test("o smile é a IV de cada série contra o strike", () => {
  const smile = analiseMercado().smiles[0]!;
  expect(pontosDoSmile(smile)).toEqual([
    [28, 0.31],
    [32, 0.29],
  ]);
  render(<GraficoSmile smile={smile} spot={30} />);
  expect(screen.getByRole("img").getAttribute("aria-label")).toContain("19/11/2026");
  expect(ultimasOpcoes().series[0]!.data).toEqual(pontosDoSmile(smile));
});

test("a estrutura a termo põe a IV no dinheiro contra os dias úteis", () => {
  render(<GraficoTermo estrutura={analiseMercado().estrutura} />);
  expect(ultimasOpcoes().series[0]!.data).toEqual([
    [18, 0.3],
    [38, 0.3],
  ]);
});

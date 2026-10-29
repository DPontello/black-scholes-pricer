import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Cadeia, Serie } from "../api/aoVivo";
import { TabelaCadeia } from "./TabelaCadeia";

function serie(parcial: Partial<Serie> & { ticker: string; strike: number }): Serie {
  return {
    tipo: "call",
    estilo: "american",
    compra: 1.2,
    venda: 1.25,
    ultimo: 1.22,
    negocios: 40,
    volume: 4840,
    iv: 0.312,
    delta: 0.55,
    ...parcial,
  };
}

const CADEIA: Cadeia = {
  ativo: "PETR4",
  spot: 52.51,
  fonte: "ao_vivo",
  hora: "2026-10-28T13:05:09-03:00",
  vencimentos: [
    {
      data: "2026-11-19",
      dias_uteis: 16,
      series: [
        serie({ ticker: "PETRK520", strike: 52, compra: null }),
        serie({ ticker: "PETRW520", strike: 52, tipo: "put", delta: -0.45 }),
        serie({ ticker: "PETRK540", strike: 54 }),
        serie({ ticker: "PETRK500", strike: 50 }),
      ],
    },
    { data: "2026-12-17", dias_uteis: 35, series: [serie({ ticker: "PETRL520", strike: 52 })] },
  ],
  rejeitadas: [{ ticker: "PETRK999", motivo: "sem estilo de exercício no cadastro" }],
};

test("lado ausente é — e a linha do strike mais perto do spot fica destacada", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} />);
  const linha = screen.getByText("52,00").closest("tr");
  expect(linha?.className).toContain("no-dinheiro");
  expect(within(linha as HTMLElement).getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.getByText("54,00").closest("tr")?.className ?? "").not.toContain("no-dinheiro");
});

test("calls e puts espelhadas no mesmo strike, com IV e delta formatados", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} />);
  const linha = screen.getByText("52,00").closest("tr") as HTMLElement;
  const celulas = within(linha).getAllByRole("cell").map((c) => c.textContent);
  expect(celulas[6]).toBe("52,00"); // o strike no meio
  expect(celulas[4]).toBe("0,55"); // delta da call
  expect(celulas[8]).toBe("-0,45"); // delta da put, espelhado
  expect(celulas).toContain("31,2%");
});

test("abas por vencimento com os dias úteis", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} />);
  expect(screen.getByRole("tab", { name: "19/11 (16 du)" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "17/12 (35 du)" }));
  expect(screen.queryByText("54,00")).toBeNull();
});

test("séries rejeitadas ficam num bloco recolhível com o motivo", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} />);
  expect(screen.getByText("1 série(s) fora da cadeia")).toBeTruthy();
  expect(screen.getByText("PETRK999: sem estilo de exercício no cadastro")).toBeTruthy();
});

test("cadeia indisponível mostra o motivo, e sem ativo pede para escolher", () => {
  const { rerender } = render(
    <TabelaCadeia
      ativo="VALE3"
      cadeia={null}
      indisponivel={{
        ativo: "VALE3",
        erro: "UnderlyingUnavailableError",
        mensagem: "VALE3: aguardando dados do Tryd",
      }}
    />,
  );
  expect(screen.getByText(/aguardando dados do Tryd/)).toBeTruthy();
  rerender(<TabelaCadeia ativo={null} cadeia={null} indisponivel={null} />);
  expect(screen.getByText(/Escolha um ativo/)).toBeTruthy();
});

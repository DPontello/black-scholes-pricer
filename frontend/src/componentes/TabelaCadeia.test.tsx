import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

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

const nada = () => {};

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
  disponiveis: [
    { data: "2026-11-06", dias_uteis: 7, semanal: true },
    { data: "2026-11-19", dias_uteis: 16, semanal: false },
    { data: "2026-12-17", dias_uteis: 35, semanal: false },
  ],
  rejeitadas: [{ ticker: "PETRK999", motivo: "sem estilo de exercício no cadastro" }],
};

test("lado ausente é — e a linha do strike mais perto do spot fica destacada", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const linha = screen.getByText("52,00").closest("tr");
  expect(linha?.className).toContain("no-dinheiro");
  expect(within(linha as HTMLElement).getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.getByText("54,00").closest("tr")?.className ?? "").not.toContain("no-dinheiro");
});

test("calls e puts espelhadas no mesmo strike, com IV e delta formatados", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const linha = screen.getByText("52,00").closest("tr") as HTMLElement;
  const celulas = within(linha).getAllByRole("cell").map((c) => c.textContent);
  expect(celulas[6]).toBe("52,00"); // o strike no meio
  expect(celulas[4]).toBe("0,55"); // delta da call
  expect(celulas[8]).toBe("-0,45"); // delta da put, espelhado
  expect(celulas).toContain("31,2%");
});

test("abas por vencimento com os dias úteis", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByRole("tab", { name: "19/11 (16 du)" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "17/12 (35 du)" }));
  expect(screen.queryByText("54,00")).toBeNull();
});

test("séries rejeitadas ficam num bloco recolhível com o motivo", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
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
      onVencimentos={nada}
    />,
  );
  expect(screen.getByText(/aguardando dados do Tryd/)).toBeTruthy();
  rerender(<TabelaCadeia ativo={null} cadeia={null} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByText(/Escolha um ativo/)).toBeTruthy();
});

test("vencimentos para escolher, com a semanal marcada e os escolhidos pressionados", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const grupo = within(screen.getByRole("group", { name: "Vencimentos" }));
  expect(grupo.getByRole("button", { name: "06/11 S" }).getAttribute("aria-pressed")).toBe("false");
  expect(grupo.getByRole("button", { name: "19/11" }).getAttribute("aria-pressed")).toBe("true");
});

test("marcar ou desmarcar um vencimento pede a nova escolha, nunca vazia", () => {
  const escolha = vi.fn();
  const { rerender } = render(
    <TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={escolha} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "06/11 S" }));
  expect(escolha).toHaveBeenLastCalledWith(["2026-11-06", "2026-11-19", "2026-12-17"]);
  fireEvent.click(screen.getByRole("button", { name: "19/11" }));
  expect(escolha).toHaveBeenLastCalledWith(["2026-12-17"]);

  const soNovembro = { ...CADEIA, vencimentos: CADEIA.vencimentos.slice(0, 1) };
  rerender(
    <TabelaCadeia ativo="PETR4" cadeia={soNovembro} indisponivel={null} onVencimentos={escolha} />,
  );
  escolha.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "19/11" }));
  expect(escolha).not.toHaveBeenCalled();
});

test("vencimento escolhido que ainda não tem série avisa no lugar da tabela", () => {
  const vazia = { ...CADEIA, vencimentos: [{ data: "2026-11-06", dias_uteis: 7, series: [] }] };
  render(<TabelaCadeia ativo="PETR4" cadeia={vazia} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByText("Nenhuma série deste vencimento chegou ainda.")).toBeTruthy();
});

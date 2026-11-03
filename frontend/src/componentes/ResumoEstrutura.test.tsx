import { render as renderBase, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import { analiseCoberta } from "../testes/analise";
import { frase, ResumoEstrutura } from "./ResumoEstrutura";

// Os "?" dos rótulos são links: o componente precisa de um roteador em volta.
function render(ui: ReactElement) {
  return renderBase(ui, { wrapper: MemoryRouter });
}

test("a venda coberta em português simples", () => {
  expect(frase(analiseCoberta())).toBe(
    "Você paga R$ 5.080,00 agora; no pior caso perde R$ 5.080,00; ganha no máximo R$ 211,00; " +
      "empata se PETR4 terminar em 50,80 no vencimento.",
  );
});

test("perda ilimitada diz ilimitada, crédito diz recebe, e sem preço o resumo avisa", () => {
  const base = analiseCoberta().no_vencimento!;
  const seca = analiseCoberta({
    no_vencimento: { ...base, caixa: 172, ganho_max: 172, perda_max: null, breakevens: [54.63] },
  });
  expect(frase(seca)).toContain("no pior caso a perda é ilimitada");
  expect(frase(seca)).toContain("Você recebe R$ 172,00 agora");
  expect(frase(analiseCoberta({ no_vencimento: null }))).toMatch(/Falta o preço/);
});

test("números, gregas e avisos aparecem; sem hoje, o motivo", () => {
  const { rerender } = render(<ResumoEstrutura analise={analiseCoberta()} />);
  expect(screen.getByText("R$ 183,43")).toBeTruthy();
  expect(screen.getByText("68,0%")).toBeTruthy();
  expect(screen.getByText("Theta por dia útil")).toBeTruthy();
  expect(screen.getByText(/ADR-0002/)).toBeTruthy();
  rerender(
    <ResumoEstrutura analise={analiseCoberta({ hoje: null, hoje_indisponivel: "put americana" })} />,
  );
  expect(screen.getByText("Sem avaliação de hoje: put americana.")).toBeTruthy();
});

test("melhor caso negativo diz que ainda perde, e zero diz que empata", () => {
  // Iron condor vendido em semanais pouco líquidas: pelo bid e pelo ask, sai com débito.
  const base = analiseCoberta().no_vencimento!;
  const debito = analiseCoberta({
    no_vencimento: { ...base, caixa: -6, ganho_max: -6, perda_max: -106, breakevens: [] },
  });
  expect(frase(debito)).toBe(
    "Você paga R$ 6,00 agora; no pior caso perde R$ 106,00; no melhor caso ainda perde R$ 6,00.",
  );
  const zero = analiseCoberta({ no_vencimento: { ...base, ganho_max: 0, breakevens: [] } });
  expect(frase(zero)).toContain("no melhor caso empata");
});

test("os rótulos com termo no glossário ganham um '?', sem repetir o mesmo termo lado a lado", () => {
  render(<ResumoEstrutura analise={analiseCoberta()} />);
  const destinos = screen
    .getAllByRole("link", { name: /^O que é/ })
    .map((link) => link.getAttribute("href")?.replace("/aprender/termos#", ""));
  expect(destinos).toEqual([
    "ganho-perda-maximos",
    "custos-ir",
    "chance-de-lucro",
    "delta",
    "gamma",
    "theta",
    "vega",
  ]);
});

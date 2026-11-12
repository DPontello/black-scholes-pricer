import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import { Ajuda } from "./Ajuda";
import { ComTermos, semMarcas, Termo, termosCitados } from "./Termo";

function montar(ui: ReactElement) {
  render(<MemoryRouter>{ui}</MemoryRouter>);
}

test("Termo é o texto sublinhado que leva ao termo na aba Termos", () => {
  montar(<Termo id="delta">o delta</Termo>);
  const link = screen.getByRole("link", { name: "o delta" });
  expect(link.getAttribute("href")).toBe("/aprender/termos#delta");
});

test("Ajuda é um '?' com o nome 'O que é <título>?'", () => {
  montar(<Ajuda id="chance-de-lucro" />);
  const link = screen.getByRole("link", { name: "O que é Chance de lucro?" });
  expect(link.textContent).toBe("?");
  expect(link.getAttribute("href")).toBe("/aprender/termos#chance-de-lucro");
});

test("ComTermos troca as marcas por links e deixa o resto como texto", () => {
  montar(
    <p data-testid="p">
      <ComTermos texto="Vende uma [call](call) acima do [strike](strike) atual." />
    </p>,
  );
  expect(screen.getByTestId("p").textContent).toBe("Vende uma call acima do strike atual.");
  expect(screen.getAllByRole("link").map((l) => l.getAttribute("href"))).toEqual([
    "/aprender/termos#call",
    "/aprender/termos#strike",
  ]);
});

test("texto sem marca fica como está", () => {
  montar(
    <p data-testid="p">
      <ComTermos texto="Sem termo nenhum." />
    </p>,
  );
  expect(screen.getByTestId("p").textContent).toBe("Sem termo nenhum.");
  expect(screen.queryByRole("link")).toBeNull();
});

test("semMarcas e termosCitados leem as marcas", () => {
  const texto = "o [prêmio](premio) e o [ponto de empate](empate)";
  expect(semMarcas(texto)).toBe("o prêmio e o ponto de empate");
  expect(termosCitados(texto)).toEqual(["premio", "empate"]);
});

import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test } from "vitest";

import { itemCoberta } from "../testes/book";
import { ItemBook } from "./ItemBook";

function Sonda() {
  const local = useLocation();
  return (
    <pre data-testid="destino">{JSON.stringify({ busca: local.search, estado: local.state })}</pre>
  );
}

function montar(item = itemCoberta()) {
  render(
    <MemoryRouter initialEntries={["/book"]}>
      <Routes>
        <Route path="/book" element={<ItemBook item={item} />} />
        <Route path="/montador" element={<Sonda />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("mostra o critério, os números, as pernas e o porquê", () => {
  montar();
  expect(screen.getByText("12,4%")).toBeTruthy();
  expect(screen.getByText("R$ 0,41")).toBeTruthy();
  expect(screen.getByText(/PETRK320 \(call 32,00\) a 0,41/)).toBeTruthy();
  expect(screen.getByText(/rende 12,4% ao ano/)).toBeTruthy();
  expect(screen.getByText(/100 ações junto/)).toBeTruthy();
  expect(screen.queryByText(/preço indicativo/)).toBeNull();
});

test("abrir no montador leva o pedido do item pelo estado da rota", async () => {
  const item = itemCoberta();
  montar(item);
  fireEvent.click(screen.getByRole("button", { name: "Abrir no montador" }));
  const destino = JSON.parse((await screen.findByTestId("destino")).textContent ?? "{}") as {
    busca: string;
    estado: { pedido: unknown };
  };
  expect(destino.busca).toBe("?ativo=PETR4");
  expect(destino.estado.pedido).toEqual(item.pedido);
});

test("referência e rótulos aparecem marcados", () => {
  montar(
    itemCoberta({
      qualidade: "teorico",
      rotulos: [{ chave: "perda_ilimitada", texto: "perda ilimitada" }],
    }),
  );
  expect(screen.getByText("preço teórico")).toBeTruthy();
  expect(screen.getByText("perda ilimitada")).toBeTruthy();
});

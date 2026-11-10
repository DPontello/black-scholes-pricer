import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test } from "vitest";

import type { FamiliaBook, ItemBook } from "../api/book";
import { itemCoberta } from "../testes/book";
import { motivoVazio, TabelaFamilia } from "./TabelaFamilia";

function Sonda() {
  const local = useLocation();
  return (
    <pre data-testid="destino">{JSON.stringify({ busca: local.search, estado: local.state })}</pre>
  );
}

function familia(itens: ItemBook[], extra: Partial<FamiliaBook> = {}): FamiliaBook {
  return { itens, referencias: [], exclusoes: [], ...extra };
}

function montar(f: FamiliaBook) {
  render(
    <MemoryRouter initialEntries={["/book"]}>
      <Routes>
        <Route path="/book" element={<TabelaFamilia familia={f} />} />
        <Route path="/montador" element={<Sonda />} />
      </Routes>
    </MemoryRouter>,
  );
}

// Outra série, para as duas linhas não terem a mesma chave.
function outraSerie(extra: Partial<ItemBook> = {}): ItemBook {
  const { pedido } = itemCoberta();
  return itemCoberta({
    ativo: "VALE3",
    pedido: { ...pedido, ativo: "VALE3", pernas: [{ ...pedido.pernas[0]!, ticker: "VALEK650" }] },
    ...extra,
  });
}

function celulas(linha: HTMLElement): string[] {
  return within(linha)
    .getAllByRole("cell")
    .map((c) => c.textContent ?? "");
}

test("uma linha por item com operação, vencimento, critério e resultado", () => {
  montar(familia([itemCoberta(), outraSerie({ resultado: null })]));
  const linhas = screen.getAllByRole("row");
  expect(linhas).toHaveLength(3); // cabeçalho + dois itens
  expect(within(linhas[0]!).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
    "Operação",
    "Vence",
    "Critério",
    "Ganha até ?",
    "Perde até ?",
    "Chance de lucro ?",
    "",
  ]);
  const ajudas = within(linhas[0]!).getAllByRole("link", { name: /^O que é/ });
  expect(ajudas.map((link) => link.getAttribute("href"))).toEqual([
    "/aprender/termos#ganho-perda-maximos",
    "/aprender/termos#ganho-perda-maximos",
    "/aprender/termos#chance-de-lucro",
  ]);
  expect(celulas(linhas[1]!)).toEqual([
    "▸ venda coberta PETR4 call 32,00",
    "19/11/2026 (18 dias úteis)",
    "12,4% anualizado",
    "R$ 350,11",
    "R$ 16.433,11",
    "62,0%",
    "abrir",
  ]);
  expect(celulas(linhas[2]!).slice(3, 6)).toEqual(["—", "—", "—"]);
});

test("ganho sem limite sai como o texto da API", () => {
  const resultado = { ...itemCoberta().resultado!, ganha_ate: null, ganha_ate_texto: "sem limite" };
  montar(familia([itemCoberta({ resultado })]));
  expect(celulas(screen.getAllByRole("row")[1]!)[3]).toBe("sem limite");
});

test("operação com várias pernas lista o tipo e o strike de cada uma", () => {
  const pernas = [
    { ...itemCoberta().pernas[0]!, ticker: "PETRK320", tipo: "call" as const, strike: 32 },
    { ...itemCoberta().pernas[0]!, ticker: "PETRW300", tipo: "put" as const, strike: 30, lado: "compra" as const },
  ];
  montar(familia([itemCoberta({ nome: "strangle", pernas })]));
  expect(celulas(screen.getAllByRole("row")[1]!)[0]).toBe("▸ strangle PETR4 call 32,00 / put 30,00");
});

test("clicar na linha expande o detalhe e clicar de novo fecha", () => {
  const item = itemCoberta({ rotulos: [{ chave: "americana", texto: "call americana avaliada como europeia" }] });
  montar(familia([item]));
  expect(screen.queryByText("prêmio por ação")).toBeNull();
  const botao = screen.getByRole("button", { name: "venda coberta" });
  expect(botao.getAttribute("aria-expanded")).toBe("false");

  fireEvent.click(screen.getByText("19/11/2026 (18 dias úteis)"));
  expect(botao.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("prêmio por ação")).toBeTruthy();
  expect(screen.getByText("R$ 0,41")).toBeTruthy();
  expect(screen.getByText(item.porque)).toBeTruthy();
  expect(screen.getByText("call americana avaliada como europeia")).toBeTruthy();
  expect(screen.getByText("vender").parentElement?.textContent).toBe(
    "vender 100 PETRK320 a 0,41 · comprar 100 PETR4",
  );

  fireEvent.click(screen.getByText("19/11/2026 (18 dias úteis)"));
  expect(botao.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText("prêmio por ação")).toBeNull();
  expect(screen.queryByText(item.porque)).toBeNull();
});

test("o botão da operação também expande, pelo teclado", () => {
  montar(familia([itemCoberta()]));
  fireEvent.click(screen.getByRole("button", { name: "venda coberta" }));
  expect(screen.getByText("prêmio por ação")).toBeTruthy();
});

test("abrir leva o pedido do item pelo estado da rota", async () => {
  const item = itemCoberta();
  montar(familia([item]));
  fireEvent.click(screen.getByRole("button", { name: "Abrir venda coberta PETR4 no montador" }));
  const destino = JSON.parse((await screen.findByTestId("destino")).textContent ?? "{}") as {
    busca: string;
    estado: { pedido: unknown };
  };
  expect(destino.busca).toBe("?ativo=PETR4");
  expect(destino.estado.pedido).toEqual(item.pedido);
});

test("família sem item diz nada hoje, com o mesmo motivo do cartão", () => {
  montar(familia([]));
  expect(screen.getByText("Nada hoje nesta família: nada passou nos filtros do preset.")).toBeTruthy();
  expect(screen.queryByRole("table")).toBeNull();
});

test("o motivo de família vazia vem das referências, depois das exclusões, depois do preset", () => {
  const referencia = itemCoberta({ qualidade: "indicativo" });
  const exclusao = { simbolo: "PETRL340/?", motivo: "sem strike" };
  expect(motivoVazio(familia([], { referencias: [referencia], exclusoes: [exclusao] }))).toBe(
    "sem preço de compra e venda agora",
  );
  expect(motivoVazio(familia([], { exclusoes: [exclusao] }))).toBe("nenhuma série passou nos filtros");
  expect(motivoVazio(familia([]))).toBe("nada passou nos filtros do preset");
});

test("a mensagem da aba vazia traz o motivo das referências ou das exclusões", () => {
  montar(familia([], { referencias: [itemCoberta({ qualidade: "indicativo" })] }));
  expect(screen.getByText("Nada hoje nesta família: sem preço de compra e venda agora.")).toBeTruthy();
  cleanup();
  montar(familia([], { exclusoes: [{ simbolo: "PETRL340/?", motivo: "sem strike" }] }));
  expect(screen.getByText("Nada hoje nesta família: nenhuma série passou nos filtros.")).toBeTruthy();
});

test("referências ficam recolhidas, com o selo de preço, e abrem no montador", async () => {
  const referencia = itemCoberta({ nome: "put coberta", qualidade: "teorico" });
  montar(familia([itemCoberta()], { referencias: [referencia] }));
  const detalhes = screen
    .getByText("Referências sem preço de compra e venda agora (1)")
    .closest("details")!;
  expect(detalhes.open).toBe(false);
  expect(within(detalhes).getByText("preço teórico")).toBeTruthy();
  expect(within(detalhes).getByText("put coberta")).toBeTruthy();

  fireEvent.click(within(detalhes).getByRole("button", { name: "Abrir put coberta PETR4 no montador" }));
  expect(await screen.findByTestId("destino")).toBeTruthy();
});

test("referência indicativa leva o selo de preço indicativo", () => {
  montar(familia([], { referencias: [itemCoberta({ qualidade: "indicativo" })] }));
  expect(screen.getByText("preço indicativo")).toBeTruthy();
});

test("exclusões ficam recolhidas com o motivo de cada uma", () => {
  montar(
    familia([itemCoberta()], {
      exclusoes: [{ simbolo: "PETRL340/?", motivo: "sem strike 1 passo mais fora" }],
    }),
  );
  const detalhes = screen.getByText("Fora do book por dado ruim (1)").closest("details")!;
  expect(detalhes.open).toBe(false);
  expect(within(detalhes).getByText("PETRL340/?: sem strike 1 passo mais fora")).toBeTruthy();
});

test("sem referências nem exclusões não há seções recolhidas", () => {
  montar(familia([itemCoberta()]));
  expect(screen.queryByText(/Referências sem preço/)).toBeNull();
  expect(screen.queryByText(/Fora do book/)).toBeNull();
});

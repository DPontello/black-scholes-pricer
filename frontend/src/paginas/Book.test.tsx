import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import type { Perfil } from "../api/cliente";
import { bookFalso, itemCoberta, PERFIL } from "../testes/book";
import { simularFetch } from "../testes/fetchFalso";
import { Book } from "./Book";

const ARROJADO: Perfil = { ...PERFIL, book: { ...PERFIL.book, preset: "arrojado", negocios_min: 3 } };

function api() {
  return simularFetch((url, init) => {
    if (url === "/api/book") return { corpo: bookFalso() };
    if (url === "/api/perfil/book" && init?.method === "PUT") return { corpo: ARROJADO };
    if (url === "/api/book/direcional")
      return {
        corpo: {
          itens: [itemCoberta({ nome: "trava de alta com call", estrutura: "trava_alta_call" })],
          referencias: [],
          exclusoes: [],
        },
      };
    return undefined;
  });
}

function ComEstado() {
  const [perfil, setPerfil] = useState<Perfil>(PERFIL);
  return <Book perfil={perfil} onPerfil={setPerfil} />;
}

function montar() {
  render(
    <MemoryRouter>
      <ComEstado />
    </MemoryRouter>,
  );
}

test("mostra o pregão do fim de dia, o contexto de vol e os itens da família", async () => {
  api();
  montar();
  expect(await screen.findByText("fim de dia (B3) do pregão 23/10/2026")).toBeTruthy();
  expect(screen.getByText("VALE3: sem histórico de IV")).toBeTruthy();
  expect(screen.getByText("12,0%")).toBeTruthy();
  expect(screen.getByRole("article", { name: "venda coberta PETR4" })).toBeTruthy();
});

test("referências aparecem à parte e rotuladas, e as exclusões com o motivo", async () => {
  api();
  montar();
  const referencias = await screen.findByRole("region", { name: "Referências" });
  expect(referencias.textContent).toContain("put coberta");
  expect(referencias.textContent).toContain("preço indicativo");
  expect(screen.getByText(/PETRL340\/\?: sem strike/)).toBeTruthy();
});

test("trocar o preset salva no perfil e varre o book de novo", async () => {
  const fetch = api();
  montar();
  await screen.findByText("fim de dia (B3) do pregão 23/10/2026");
  fireEvent.change(screen.getByLabelText("Preset"), { target: { value: "arrojado" } });
  await waitFor(() =>
    expect(fetch.mock.calls.filter(([u]) => u === "/api/book").length).toBe(2),
  );
  expect((screen.getByLabelText("Negócios mínimos por perna") as HTMLInputElement).value).toBe("3");
});

test("o formulário da visão manda o alvo e mostra as operações", async () => {
  const fetch = api();
  montar();
  fireEvent.click(await screen.findByRole("tab", { name: "Direcionais" }));
  fireEvent.change(screen.getByLabelText("Direção"), { target: { value: "alta" } });
  fireEvent.change(screen.getByLabelText("Preço-alvo"), { target: { value: "33.5" } });
  fireEvent.change(screen.getByLabelText("Vencimento"), { target: { value: "2026-11-19" } });
  fireEvent.click(screen.getByRole("button", { name: "Ver as operações" }));
  expect(await screen.findByRole("article", { name: "trava de alta com call PETR4" })).toBeTruthy();
  const pedido = fetch.mock.calls.find(([u]) => u === "/api/book/direcional");
  expect(JSON.parse(String(pedido?.[1]?.body))).toEqual({
    ativo: "PETR4",
    direcao: "alta",
    alvo: 33.5,
    vencimento: "2026-11-19",
  });
});

test("erro ao montar o book aparece", async () => {
  simularFetch(() => ({ status: 404, corpo: { erro: "NoActiveProfileError", mensagem: "abra um perfil" } }));
  montar();
  expect((await screen.findByRole("alert")).textContent).toBe("abra um perfil");
});

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { simularFetch } from "../testes/fetchFalso";
import { MODERADO, PERFIL } from "../testes/book";
import { EditorPreset } from "./EditorPreset";

function corpos(fetch: ReturnType<typeof simularFetch>): unknown[] {
  return fetch.mock.calls
    .filter(([u]) => u === "/api/perfil/book")
    .map(([, init]) => JSON.parse(String(init?.body)) as unknown);
}

function api() {
  return simularFetch((url, init) => {
    if (url === "/api/perfil/book" && init?.method === "PUT") return { corpo: PERFIL };
    return undefined;
  });
}

test("trocar o preset grava os padrões dele e devolve o perfil", async () => {
  const fetch = api();
  const salvo = vi.fn();
  render(<EditorPreset preset={MODERADO} onSalvo={salvo} />);
  fireEvent.change(screen.getByLabelText("Preset"), { target: { value: "arrojado" } });
  await waitFor(() => expect(salvo).toHaveBeenCalledWith(PERFIL));
  expect(corpos(fetch)).toEqual([{ preset: "arrojado" }]);
});

test("salvar valores manda o spread e o piso em fração", async () => {
  const fetch = api();
  render(<EditorPreset preset={MODERADO} onSalvo={vi.fn()} />);
  expect((screen.getByLabelText("Spread máximo (%)") as HTMLInputElement).value).toBe("20");
  fireEvent.change(screen.getByLabelText("Spread máximo (%)"), { target: { value: "15" } });
  fireEvent.change(screen.getByLabelText("Negócios mínimos por perna"), { target: { value: "30" } });
  fireEvent.click(screen.getByLabelText("Aceitar perda ilimitada (strangle vendido)"));
  fireEvent.click(screen.getByRole("button", { name: "Salvar valores" }));
  await waitFor(() => expect(corpos(fetch).length).toBe(1));
  const { preset: _preset, ...valores } = MODERADO;
  expect(corpos(fetch)[0]).toEqual({
    preset: "moderado",
    valores: { ...valores, spread_max: 0.15, negocios_min: 30, perda_ilimitada: true },
  });
});

test("voltar ao padrão manda só o preset", async () => {
  const fetch = api();
  render(<EditorPreset preset={MODERADO} onSalvo={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Voltar ao padrão" }));
  await waitFor(() => expect(corpos(fetch)).toEqual([{ preset: "moderado" }]));
});

test("valor recusado pela API aparece como erro", async () => {
  simularFetch(() => ({
    status: 422,
    corpo: { erro: "InvalidDomainValueError", mensagem: "faixa de delta exige mínimo <= máximo" },
  }));
  render(<EditorPreset preset={MODERADO} onSalvo={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Salvar valores" }));
  expect((await screen.findByRole("alert")).textContent).toContain("faixa de delta");
});

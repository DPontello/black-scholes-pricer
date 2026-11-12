import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { trava } from "../testes/carteira";
import { simularFetch } from "../testes/fetchFalso";
import { DialogoLimites } from "./DialogoLimites";

function montar(feito = vi.fn()) {
  render(
    <MemoryRouter>
      <DialogoLimites operacao={trava({ stop: 200, alvo: null })} onFeito={feito} onCancelar={vi.fn()} />
    </MemoryRouter>,
  );
  return feito;
}

test("abre com os limites da operação e grava pela rota de limites", async () => {
  const fetch = simularFetch(() => ({ corpo: { id: "op1" } }));
  const feito = montar();
  expect((screen.getByLabelText("Stop da operação") as HTMLInputElement).value).toBe("200");
  fireEvent.change(screen.getByLabelText("Stop da operação"), { target: { value: "" } });
  fireEvent.change(screen.getByLabelText("Alvo da operação"), { target: { value: "90" } });
  fireEvent.click(screen.getByRole("button", { name: "Gravar" }));
  await waitFor(() => expect(feito).toHaveBeenCalled());
  const [url, init] = fetch.mock.calls[0] ?? [];
  expect(url).toBe("/api/carteira/operacoes/op1/limites");
  expect(init?.method).toBe("PUT");
  expect(JSON.parse(String(init?.body))).toEqual({ stop: null, alvo: 90 });
});

test("o '?' leva ao termo de stop e alvo", () => {
  simularFetch(() => undefined);
  montar();
  expect(screen.getByRole("link", { name: "O que é Stop e alvo?" })).toBeTruthy();
});

test("valor negativo é recusado sem chamar a api", async () => {
  const fetch = simularFetch(() => ({ corpo: { id: "op1" } }));
  montar();
  fireEvent.change(screen.getByLabelText("Alvo da operação"), { target: { value: "-5" } });
  fireEvent.click(screen.getByRole("button", { name: "Gravar" }));
  expect((await screen.findByRole("alert")).textContent).toContain("maiores que zero");
  expect(fetch).not.toHaveBeenCalled();
});

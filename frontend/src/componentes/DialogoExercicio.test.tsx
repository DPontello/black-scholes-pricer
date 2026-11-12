import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { trava } from "../testes/carteira";
import { simularFetch } from "../testes/fetchFalso";
import { DialogoExercicio } from "./DialogoExercicio";

function corpo(fetch: ReturnType<typeof simularFetch>, url: string): unknown {
  const chamada = fetch.mock.calls.find(([u]) => u === url);
  return chamada === undefined ? undefined : (JSON.parse(String(chamada[1]?.body)) as unknown);
}

test("a perna comprada registra exercício; a vendida, atribuição", async () => {
  const fetch = simularFetch(() => ({ corpo: { id: "op1" } }));
  const feito = vi.fn();
  render(<DialogoExercicio operacao={trava()} onFeito={feito} onCancelar={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Registrar exercício" }));
  await waitFor(() => expect(feito).toHaveBeenCalledTimes(1));
  expect(corpo(fetch, "/api/carteira/operacoes/op1/exercer")).toEqual({
    perna: 0,
    quantidade: 100,
    data: "2026-11-19",
    custos: null,
  });
  fireEvent.change(screen.getByLabelText("Perna exercida"), { target: { value: "1" } });
  fireEvent.click(screen.getByRole("button", { name: "Registrar atribuição" }));
  await waitFor(() => expect(feito).toHaveBeenCalledTimes(2));
  expect(corpo(fetch, "/api/carteira/operacoes/op1/atribuir")).toMatchObject({ perna: 1 });
});

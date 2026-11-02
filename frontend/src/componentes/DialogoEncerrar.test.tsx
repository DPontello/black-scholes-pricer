import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { perna, trava } from "../testes/carteira";
import { simularFetch } from "../testes/fetchFalso";
import { DialogoEncerrar } from "./DialogoEncerrar";

function corpo(fetch: ReturnType<typeof simularFetch>, url: string): unknown {
  const chamada = fetch.mock.calls.find(([u]) => u === url);
  return chamada === undefined ? undefined : (JSON.parse(String(chamada[1]?.body)) as unknown);
}

test("encerrar parcial manda a perna, a quantidade e o preço de zerar sugerido", async () => {
  const fetch = simularFetch(() => ({ corpo: { id: "op1" } }));
  const feito = vi.fn();
  const operacao = trava({
    pernas: [
      perna(),
      perna({
        indice: 1,
        ticker: "PETRK320",
        lado: "venda",
        quantidade: 300,
        marca: { preco: 0.45, nao_realizado: 45, teorico: null, motivo: null },
      }),
    ],
  });
  render(<DialogoEncerrar operacao={operacao} onFeito={feito} onCancelar={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Perna a encerrar"), { target: { value: "1" } });
  expect((screen.getByLabelText("Quantidade a encerrar") as HTMLInputElement).value).toBe("300");
  expect((screen.getByLabelText("Preço do encerramento") as HTMLInputElement).value).toBe("0,45");
  fireEvent.change(screen.getByLabelText("Quantidade a encerrar"), { target: { value: "100" } });
  fireEvent.change(screen.getByLabelText("Data do encerramento"), { target: { value: "2026-11-10" } });
  fireEvent.click(screen.getByRole("button", { name: "Encerrar" }));
  await waitFor(() => expect(feito).toHaveBeenCalled());
  expect(corpo(fetch, "/api/carteira/operacoes/op1/encerrar")).toEqual({
    perna: 1,
    quantidade: 100,
    preco: 0.45,
    data: "2026-11-10",
    custos: null,
  });
});

test("sem preço de zerar o encerramento pede o preço", async () => {
  const fetch = simularFetch(() => ({ corpo: { id: "op1" } }));
  render(<DialogoEncerrar operacao={trava()} onFeito={vi.fn()} onCancelar={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Encerrar" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Informe o preço do encerramento.");
  expect(fetch).not.toHaveBeenCalled();
});

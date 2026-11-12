import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { simularFetch } from "../testes/fetchFalso";
import { AdicionarAcoes } from "./AdicionarAcoes";

test("adiciona as ações à mão pelo preço médio", async () => {
  const fetch = simularFetch(() => ({ status: 201, corpo: { id: "op3" } }));
  const feito = vi.fn();
  render(<AdicionarAcoes onFeito={feito} onCancelar={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Informe o ativo e o preço médio.");
  fireEvent.change(screen.getByLabelText("Ativo das ações"), { target: { value: "petr4" } });
  fireEvent.change(screen.getByLabelText("Quantidade de ações"), { target: { value: "300" } });
  fireEvent.change(screen.getByLabelText("Preço médio"), { target: { value: "28,45" } });
  fireEvent.change(screen.getByLabelText("Data das ações"), { target: { value: "2026-10-01" } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  await waitFor(() => expect(feito).toHaveBeenCalled());
  const [url, init] = fetch.mock.calls[0] ?? [];
  expect(url).toBe("/api/carteira/acoes");
  expect(JSON.parse(String(init?.body))).toEqual({
    ativo: "petr4",
    quantidade: 300,
    preco_medio: 28.45,
    data: "2026-10-01",
  });
});

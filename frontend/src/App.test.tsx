import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import { App } from "./App";
import { simularFetch } from "./testes/fetchFalso";

test("sem perfil aberto, qualquer rota leva à escolha de perfil", async () => {
  simularFetch((url) => {
    if (url === "/api/perfil")
      return { status: 404, corpo: { erro: "NoActiveProfileError", mensagem: "nenhum perfil" } };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
  render(
    <MemoryRouter initialEntries={["/arquivos"]}>
      <App />
    </MemoryRouter>,
  );
  expect(await screen.findByText("Quem está usando?")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Escolher perfil" })).toBeTruthy();
});

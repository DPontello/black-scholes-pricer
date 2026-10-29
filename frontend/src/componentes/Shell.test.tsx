import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import { Shell } from "./Shell";

test("menu com as seis áreas", () => {
  render(
    <MemoryRouter>
      <Shell status={null}>
        <div />
      </Shell>
    </MemoryRouter>,
  );
  for (const nome of ["Mercado", "Montador", "Book", "Carteira", "Alertas", "Arquivos B3"])
    expect(screen.getByRole("link", { name: nome })).toBeTruthy();
});

test("barra superior mostra o perfil aberto e o espaço do status", () => {
  render(
    <MemoryRouter>
      <Shell status={<span>Ao vivo (Tryd)</span>} perfil="Hugo">
        <p>conteúdo</p>
      </Shell>
    </MemoryRouter>,
  );
  expect(screen.getByText("Painel de Opções")).toBeTruthy();
  expect(screen.getByRole("link", { name: /Hugo/ })).toBeTruthy();
  expect(screen.getByText("Ao vivo (Tryd)")).toBeTruthy();
  expect(screen.getByText("conteúdo")).toBeTruthy();
});

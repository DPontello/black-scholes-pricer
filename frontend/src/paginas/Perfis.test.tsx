import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { simularFetch } from "../testes/fetchFalso";
import { Perfis } from "./Perfis";

const HUGO = { nome: "Hugo", ativos: ["PETR4", "VALE3"], cdi_anual: 0.15 };

test("a lista de perfis vem da API", async () => {
  simularFetch((url) =>
    url === "/api/perfis" ? { corpo: [{ nome: "Hugo", pasta: "G:/Meu Drive/opcoes" }] } : undefined,
  );
  render(<Perfis onAberto={() => {}} />);
  expect(await screen.findByText("Hugo")).toBeTruthy();
  expect(screen.getByText("G:/Meu Drive/opcoes")).toBeTruthy();
  expect(screen.getByText(/Google Drive, OneDrive, Dropbox/)).toBeTruthy();
});

test("perfil aberto em outro PC pede confirmação citando o PC e, confirmado, força", async () => {
  const fetch = simularFetch((url, init) => {
    if (url === "/api/perfis") return { corpo: [{ nome: "Hugo", pasta: "/p" }] };
    if (url === "/api/perfis/Hugo/abrir") {
      const { forcar } = JSON.parse(String(init?.body)) as { forcar: boolean };
      return forcar
        ? { corpo: HUGO }
        : {
            status: 409,
            corpo: {
              erro: "ProfileLockedError",
              mensagem: "perfil em uso",
              trava: { pc: "PC-SALA", desde: "2026-11-03T09:00:00-03:00" },
            },
          };
    }
    return undefined;
  });
  const aberto = vi.fn();
  render(<Perfis onAberto={aberto} />);
  fireEvent.click(await screen.findByRole("button", { name: "Abrir Hugo" }));
  expect(await screen.findByText(/aberto no PC PC-SALA desde .*Abrir mesmo assim\?/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Abrir mesmo assim" }));
  await waitFor(() => expect(aberto).toHaveBeenCalledWith(HUGO));
  const corpos = fetch.mock.calls
    .filter(([url]) => url === "/api/perfis/Hugo/abrir")
    .map(([, init]) => JSON.parse(String(init?.body)) as { forcar: boolean });
  expect(corpos).toEqual([{ forcar: false }, { forcar: true }]);
});

test("novo perfil com nome e pasta", async () => {
  let perfis: { nome: string; pasta: string }[] = [];
  simularFetch((url, init) => {
    if (url === "/api/perfis" && init?.method === "POST") {
      const corpo = JSON.parse(String(init.body)) as { nome: string; pasta: string };
      perfis = [...perfis, corpo];
      return { status: 201, corpo: { ...HUGO, nome: corpo.nome } };
    }
    if (url === "/api/perfis") return { corpo: perfis };
    return undefined;
  });
  render(<Perfis onAberto={() => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "Novo perfil" }));
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Mãe" } });
  fireEvent.change(screen.getByLabelText("Pasta de dados"), { target: { value: "C:/OneDrive/mae" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar perfil" }));
  expect(await screen.findByText("Mãe")).toBeTruthy();
});

test("erro da API aparece com a mensagem dela", async () => {
  simularFetch((url, init) => {
    if (url === "/api/perfis" && init?.method === "POST")
      return {
        status: 409,
        corpo: { erro: "DuplicateProfileError", mensagem: "já existe um perfil 'Hugo'" },
      };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
  render(<Perfis onAberto={() => {}} />);
  fireEvent.click(await screen.findByRole("button", { name: "Novo perfil" }));
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Hugo" } });
  fireEvent.change(screen.getByLabelText("Pasta de dados"), { target: { value: "/p" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar perfil" }));
  expect(await screen.findByText("já existe um perfil 'Hugo'")).toBeTruthy();
});

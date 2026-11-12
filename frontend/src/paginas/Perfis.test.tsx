import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { simularFetch } from "../testes/fetchFalso";
import { Perfis } from "./Perfis";

const HUGO = { nome: "Hugo", ativos: ["PETR4", "VALE3"], cdi_anual: 0.15 };

test("a lista de perfis vem da API", async () => {
  simularFetch((url) =>
    url === "/api/perfis" ? { corpo: [{ nome: "Hugo", pasta: "G:/Meu Drive/opcoes" }] } : undefined,
  );
  render(
    <MemoryRouter>
      <Perfis onAberto={() => {}} />
    </MemoryRouter>,
  );
  expect(await screen.findByText("Hugo")).toBeTruthy();
  expect(screen.getByText("G:/Meu Drive/opcoes")).toBeTruthy();
  expect(screen.getByText(/Em "Escolher pasta…", use uma pasta da sua nuvem/)).toBeTruthy();
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
  render(
    <MemoryRouter>
      <Perfis onAberto={aberto} />
    </MemoryRouter>,
  );
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
  render(
    <MemoryRouter>
      <Perfis onAberto={() => {}} />
    </MemoryRouter>,
  );
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
  render(
    <MemoryRouter>
      <Perfis onAberto={() => {}} />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Novo perfil" }));
  fireEvent.change(screen.getByLabelText("Nome"), { target: { value: "Hugo" } });
  fireEvent.change(screen.getByLabelText("Pasta de dados"), { target: { value: "/p" } });
  fireEvent.click(screen.getByRole("button", { name: "Criar perfil" }));
  expect(await screen.findByText("já existe um perfil 'Hugo'")).toBeTruthy();
});

const ESCOLHER_PASTA = "/api/perfis/escolher-pasta";

async function abrirNovoPerfil() {
  render(
    <MemoryRouter>
      <Perfis onAberto={() => {}} />
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Novo perfil" }));
}

test("Escolher pasta… põe o caminho escolhido no campo", async () => {
  const fetch = simularFetch((url, init) => {
    if (url === ESCOLHER_PASTA && init?.method === "POST") return { corpo: { pasta: "/nuvem/Mãe" } };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
  await abrirNovoPerfil();
  fireEvent.click(screen.getByRole("button", { name: "Escolher pasta…" }));
  await waitFor(() =>
    expect((screen.getByLabelText("Pasta de dados") as HTMLInputElement).value).toBe("/nuvem/Mãe"),
  );
  expect(fetch.mock.calls.some(([url]) => url === ESCOLHER_PASTA)).toBe(true);
});

test("cancelar a escolha deixa o que já estava digitado", async () => {
  const fetch = simularFetch((url) => {
    if (url === ESCOLHER_PASTA) return { corpo: { pasta: null } };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
  await abrirNovoPerfil();
  fireEvent.change(screen.getByLabelText("Pasta de dados"), { target: { value: "/tmp/x" } });
  fireEvent.click(screen.getByRole("button", { name: "Escolher pasta…" }));
  await waitFor(() => expect(fetch.mock.calls.some(([url]) => url === ESCOLHER_PASTA)).toBe(true));
  await waitFor(() =>
    expect((screen.getByRole("button", { name: "Escolher pasta…" }) as HTMLButtonElement).disabled).toBe(
      false,
    ),
  );
  expect((screen.getByLabelText("Pasta de dados") as HTMLInputElement).value).toBe("/tmp/x");
});

test("o botão fica desabilitado enquanto a janela de escolha está aberta", async () => {
  const base = simularFetch((url) => (url === "/api/perfis" ? { corpo: [] } : undefined));
  let responder = (_: Response) => {};
  const aberta = new Promise<Response>((resolve) => {
    responder = resolve;
  });
  vi.stubGlobal("fetch", (entrada: RequestInfo | URL, init?: RequestInit) =>
    String(entrada) === ESCOLHER_PASTA ? aberta : base(entrada, init),
  );
  await abrirNovoPerfil();
  const botao = screen.getByRole("button", { name: "Escolher pasta…" }) as HTMLButtonElement;
  fireEvent.click(botao);
  expect(botao.disabled).toBe(true);
  responder(new Response(JSON.stringify({ pasta: "/nuvem/Mãe" }), { status: 200 }));
  await waitFor(() => expect(botao.disabled).toBe(false));
});

test("sem seletor neste PC, a mensagem aparece", async () => {
  const mensagem = "Este PC não tem como abrir a escolha de pasta. Digite o caminho completo da pasta.";
  simularFetch((url) => {
    if (url === ESCOLHER_PASTA)
      return { status: 501, corpo: { erro: "SemSeletorDePasta", mensagem } };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
  await abrirNovoPerfil();
  fireEvent.click(screen.getByRole("button", { name: "Escolher pasta…" }));
  expect((await screen.findByRole("alert")).textContent).toBe(mensagem);
});

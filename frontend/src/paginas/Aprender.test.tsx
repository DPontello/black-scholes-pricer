import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { App } from "../App";
import { PERFIL } from "../testes/book";
import { simularFetch } from "../testes/fetchFalso";

// Com perfil, o App abre o WebSocket do ao vivo; o jsdom não tem servidor para ele.
class SocketFalso {
  static readonly OPEN = 1;
  readonly readyState = 0;
  close() {}
  send() {}
}

function Sonda() {
  return <output data-testid="endereco">{useLocation().pathname}</output>;
}

function montar(endereco: string) {
  render(
    <MemoryRouter initialEntries={[endereco]}>
      <App />
      <Sonda />
    </MemoryRouter>,
  );
}

function comPerfil() {
  vi.stubGlobal("WebSocket", SocketFalso);
  simularFetch((url) => {
    if (url === "/api/perfil") return { corpo: PERFIL };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
}

function semPerfil() {
  simularFetch((url) => {
    if (url === "/api/perfil")
      return { status: 404, corpo: { erro: "NoActiveProfileError", mensagem: "nenhum perfil" } };
    if (url === "/api/perfis") return { corpo: [] };
    return undefined;
  });
}

const endereco = () => screen.getByTestId("endereco").textContent;

function subAbas() {
  return within(screen.getByRole("navigation", { name: "Seções de Aprender" }));
}

// O App só monta a página depois de perguntar à API se há perfil aberto.
async function esperarAprender() {
  await screen.findByRole("navigation", { name: "Seções de Aprender" });
}

test("com perfil, o menu tem Aprender entre Carteira e Alertas", async () => {
  comPerfil();
  montar("/aprender");
  const menu = within(await screen.findByRole("navigation", { name: "Áreas do app" }));
  const nomes = menu.getAllByRole("link").map((link) => link.textContent);
  expect(nomes).toEqual(["Mercado", "Montador", "Book", "Carteira", "Aprender", "Alertas", "Arquivos B3"]);
  expect(menu.getByRole("link", { name: "Aprender" }).getAttribute("aria-current")).toBe("page");
});

test("/aprender abre em Comece aqui, com a sub-aba ativa", async () => {
  comPerfil();
  montar("/aprender");
  await esperarAprender();
  const comece = subAbas().getByRole("link", { name: "Comece aqui" });
  expect(endereco()).toBe("/aprender/comece");
  expect(comece.getAttribute("aria-current")).toBe("page");
  for (const nome of ["Operações", "Termos", "Telas do app"])
    expect(subAbas().getByRole("link", { name: nome }).getAttribute("aria-current")).toBeNull();
});

test("clicar numa sub-aba troca o endereço e a sub-aba ativa", async () => {
  comPerfil();
  montar("/aprender");
  await esperarAprender();
  for (const [nome, caminho] of [
    ["Operações", "/aprender/operacoes"],
    ["Termos", "/aprender/termos"],
    ["Telas do app", "/aprender/telas"],
    ["Comece aqui", "/aprender/comece"],
  ] as const) {
    fireEvent.click(subAbas().getByRole("link", { name: nome }));
    expect(endereco()).toBe(caminho);
    expect(subAbas().getByRole("link", { name: nome }).getAttribute("aria-current")).toBe("page");
  }
});

test("uma operação em /aprender/operacoes/:modelo mantém Operações ativa", async () => {
  comPerfil();
  montar("/aprender/operacoes/iron_condor_vendido");
  await esperarAprender();
  const operacoes = subAbas().getByRole("link", { name: "Operações" });
  expect(endereco()).toBe("/aprender/operacoes/iron_condor_vendido");
  expect(operacoes.getAttribute("aria-current")).toBe("page");
});

test("um endereço desconhecido dentro de Aprender volta para Comece aqui", async () => {
  comPerfil();
  montar("/aprender/xyz");
  await esperarAprender();
  expect(endereco()).toBe("/aprender/comece");
});

test("com perfil, a página não oferece voltar aos perfis", async () => {
  comPerfil();
  montar("/aprender/termos");
  await esperarAprender();
  expect(screen.queryByRole("link", { name: /voltar aos perfis/i })).toBeNull();
});

test("sem perfil, a tela de perfis tem o link Como usar o app para Comece aqui", async () => {
  semPerfil();
  montar("/mercado");
  expect(await screen.findByText("Quem está usando?")).toBeTruthy();
  const link = screen.getByRole("link", { name: "Como usar o app" });
  expect(link.getAttribute("href")).toBe("/aprender/comece");
  fireEvent.click(link);
  await esperarAprender();
  expect(endereco()).toBe("/aprender/comece");
});

test("sem perfil, /aprender/termos abre em vez de ir para os perfis", async () => {
  semPerfil();
  montar("/aprender/termos");
  await esperarAprender();
  const termos = subAbas().getByRole("link", { name: "Termos" });
  expect(endereco()).toBe("/aprender/termos");
  expect(termos.getAttribute("aria-current")).toBe("page");
  expect(screen.queryByText("Quem está usando?")).toBeNull();
});

test("sem perfil, /aprender abre em Comece aqui e dá o caminho de volta aos perfis", async () => {
  semPerfil();
  montar("/aprender");
  await esperarAprender();
  expect(endereco()).toBe("/aprender/comece");
  const voltar = screen.getByRole("link", { name: /voltar aos perfis/i });
  expect(voltar.getAttribute("href")).toBe("/perfis");
  fireEvent.click(voltar);
  expect(await screen.findByText("Quem está usando?")).toBeTruthy();
  expect(endereco()).toBe("/perfis");
});

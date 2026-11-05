import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test } from "vitest";

import { Aprender } from "../paginas/Aprender";

function Sonda() {
  const { pathname, hash } = useLocation();
  return <output data-testid="endereco">{pathname + hash}</output>;
}

function montar(endereco: string, comPerfil = true) {
  render(
    <MemoryRouter initialEntries={[endereco]}>
      <Routes>
        <Route path="/aprender/*" element={<Aprender comPerfil={comPerfil} />} />
        <Route path="/arquivos" element={<p>Arquivos B3</p>} />
      </Routes>
      <Sonda />
    </MemoryRouter>,
  );
}

const PASSOS = [
  "Crie o seu perfil",
  "Baixe os arquivos da semana",
  "Abra o Tryd",
  "Veja as melhores operações no Book",
  "Confira e ajuste no Montador",
  "Registre o que executou na Carteira",
  "No vencimento",
];

function passo(titulo: string) {
  return within(screen.getByRole("heading", { level: 3, name: titulo }).closest("li") as HTMLElement);
}

test("Comece aqui tem os sete passos, nesta ordem", () => {
  montar("/aprender/comece");
  const lista = screen.getByRole("list");
  const titulos = within(lista)
    .getAllByRole("heading", { level: 3 })
    .map((h) => h.textContent);
  expect(titulos).toEqual(PASSOS);
});

test("o passo do perfil manda escolher a pasta pelo botão, sem digitar o caminho", () => {
  montar("/aprender/comece");
  expect(passo("Crie o seu perfil").getByText(/em "Escolher pasta…", escolha a pasta/)).toBeTruthy();
});

test("o passo dos arquivos leva a Arquivos B3 e fala dos dois arquivos da semana", () => {
  montar("/aprender/comece");
  const arquivos = passo("Baixe os arquivos da semana");
  expect(arquivos.getByText(/pesquisa-pregao\.zip/)).toBeTruthy();
  expect(arquivos.getByRole("link", { name: "COTAHIST" }).getAttribute("href")).toBe(
    "/aprender/termos#cotahist",
  );
  fireEvent.click(arquivos.getByRole("link", { name: "Abrir Arquivos B3" }));
  expect(screen.getByTestId("endereco").textContent).toBe("/arquivos");
});

test("o passo do vencimento explica pó, exercício e atribuição, com os termos", () => {
  montar("/aprender/comece");
  const vencimento = passo("No vencimento");
  for (const [nome, id] of [
    ["pó", "po"],
    ["exercício", "exercicio"],
    ["atribuição", "atribuicao"],
  ])
    expect(vencimento.getByRole("link", { name: nome }).getAttribute("href")).toBe(
      `/aprender/termos#${id}`,
    );
});

test("sem perfil, só o link dos perfis aparece: as outras telas pedem um perfil aberto", () => {
  montar("/aprender/comece", false);
  expect(passo("Crie o seu perfil").getByRole("link", { name: "Abrir os perfis" })).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Abrir Arquivos B3" })).toBeNull();
  expect(screen.queryByRole("link", { name: "Abrir o Book" })).toBeNull();
});

test("Telas do app tem uma seção por aba do menu, na ordem, e as do indicador e dos rótulos", () => {
  montar("/aprender/telas");
  const secoes = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
  expect(secoes).toEqual([
    "Mercado",
    "Montador",
    "Book",
    "Carteira",
    "Aprender",
    "Alertas",
    "Arquivos B3",
    "O indicador do topo",
    "Rótulos e avisos",
  ]);
});

test("o indicador do topo explica os três estados com os rótulos da tela", () => {
  montar("/aprender/telas");
  const indicador = within(screen.getByRole("region", { name: "O indicador do topo" }));
  const rotulos = indicador.getAllByRole("term").map((dt) => dt.textContent);
  expect(rotulos).toEqual(["Ao vivo (Tryd)", "Atrasado", "Fim de dia (B3)"]);
});

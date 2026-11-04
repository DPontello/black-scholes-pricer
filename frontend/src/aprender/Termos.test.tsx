import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test } from "vitest";

import { semMarcas, termosCitados } from "../componentes/Termo";
import { TEXTOS_OPERACOES } from "./textosOperacoes";
import { TERMOS } from "./glossario";
import { Termos } from "./Termos";

// Os ids que os "?" do app usam: nenhum pode sumir do glossário.
const IDS = [
  "call",
  "put",
  "strike",
  "premio",
  "vencimento",
  "dias-uteis",
  "lote",
  "exercicio",
  "atribuicao",
  "po",
  "americana-europeia",
  "delta",
  "gamma",
  "theta",
  "vega",
  "iv",
  "iv-30",
  "hv-21",
  "iv-rank",
  "percentil",
  "vol-cara-barata",
  "spread",
  "negocios",
  "preco-executavel",
  "preco-de-zerar",
  "ao-vivo-fim-de-dia",
  "cadastro",
  "cotahist",
  "custos-ir",
  "anualizado",
  "retorno-sobre-risco",
  "chance-de-lucro",
  "probabilidade-de-exercicio",
  "empate",
  "ganho-perda-maximos",
];

function Sonda() {
  const { pathname, hash } = useLocation();
  return <output data-testid="endereco">{pathname + hash}</output>;
}

function montar(endereco: string) {
  render(
    <MemoryRouter initialEntries={[endereco]}>
      <Routes>
        <Route path="/aprender/termos" element={<Termos />} />
      </Routes>
      <Sonda />
    </MemoryRouter>,
  );
}

const titulos = () => screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
const busca = () => screen.getByRole("searchbox", { name: "Buscar termo" });

test("todo id usado pelos '?' existe no glossário, sem repetição e sem texto vazio", () => {
  expect(TERMOS.map((t) => t.id).sort()).toEqual([...IDS].sort());
  for (const termo of TERMOS)
    for (const campo of [termo.titulo, termo.texto, termo.exemplo, termo.onde])
      expect(campo.trim()).not.toBe("");
});

test("todo termo citado num texto (glossário ou operações) existe", () => {
  const textos = [
    ...TERMOS.flatMap((t) => [t.texto, t.exemplo, t.onde]),
    ...Object.values(TEXTOS_OPERACOES).flatMap((t) => [
      t.oQueE,
      t.quandoUsar,
      t.comoMontar,
      t.oQuePodeDarErrado,
      t.noApp,
    ]),
  ];
  const ids = new Set(TERMOS.map((t) => t.id));
  for (const texto of textos) for (const id of termosCitados(texto)) expect(ids).toContain(id);
});

test("a lista mostra todos os termos em ordem alfabética, cada um com o id dele", () => {
  montar("/aprender/termos");
  const esperados = [...TERMOS].sort((a, b) => a.titulo.localeCompare(b.titulo, "pt-BR"));
  expect(titulos()).toEqual(esperados.map((t) => t.titulo));
  expect(titulos()[0]).toBe("Americana e europeia");
  for (const termo of TERMOS) {
    const titulo = screen.getByRole("heading", { level: 3, name: termo.titulo });
    expect(titulo.closest("article")?.id).toBe(termo.id);
  }
});

test("cada termo mostra o texto, o exemplo e onde aparece no app", () => {
  montar("/aprender/termos");
  const delta = within(screen.getByRole("heading", { name: "Delta" }).closest("article") as HTMLElement);
  const termo = TERMOS.find((t) => t.id === "delta");
  const paragrafos = delta.getAllByText((_, el) => el?.tagName === "P").map((p) => p.textContent);
  expect(paragrafos).toEqual([
    semMarcas(termo?.texto ?? ""),
    `Exemplo: ${semMarcas(termo?.exemplo ?? "")}`,
    `No app: ${semMarcas(termo?.onde ?? "")}`,
  ]);
});

test("a busca ignora acento e maiúsculas", () => {
  montar("/aprender/termos");
  fireEvent.change(busca(), { target: { value: "exercicio" } });
  expect(titulos()).toContain("Exercício");
  expect(titulos()).not.toContain("Delta");
  fireEvent.change(busca(), { target: { value: "VOL" } });
  expect(titulos()).toContain("Vol cara, normal e barata");
  fireEvent.change(busca(), { target: { value: "volatilidade" } });
  expect(titulos()).toContain("Vol cara, normal e barata");
  expect(titulos()).toContain("IV (vol implícita)");
});

test("sem resultado, avisa que nenhum termo foi encontrado", () => {
  montar("/aprender/termos");
  fireEvent.change(busca(), { target: { value: "xyzzy" } });
  expect(screen.getByText("Nenhum termo encontrado.")).toBeTruthy();
  expect(screen.queryAllByRole("heading", { level: 3 })).toHaveLength(0);
});

test("#delta destaca o termo; os outros não", () => {
  montar("/aprender/termos#delta");
  const delta = screen.getByRole("heading", { level: 3, name: "Delta" }).closest("article");
  const gamma = screen.getByRole("heading", { level: 3, name: "Gamma" }).closest("article");
  expect(delta?.getAttribute("aria-current")).toBe("true");
  expect(gamma?.getAttribute("aria-current")).toBeNull();
});

test("um # que não existe mostra a lista inteira, sem erro", () => {
  montar("/aprender/termos#termo-inexistente");
  expect(titulos()).toHaveLength(TERMOS.length);
  expect(screen.queryByRole("alert")).toBeNull();
  expect(document.querySelector("[aria-current]")).toBeNull();
});

test("um link para outro termo leva a ele e limpa a busca, para ele aparecer", () => {
  montar("/aprender/termos");
  fireEvent.change(busca(), { target: { value: "gamma" } });
  expect(titulos()).toEqual(["Gamma"]);
  fireEvent.click(screen.getByRole("link", { name: "delta" }));
  expect(screen.getByTestId("endereco").textContent).toBe("/aprender/termos#delta");
  expect((busca() as HTMLInputElement).value).toBe("");
  expect(titulos()).toHaveLength(TERMOS.length);
  const delta = screen.getByRole("heading", { level: 3, name: "Delta" }).closest("article");
  expect(delta?.getAttribute("aria-current")).toBe("true");
});

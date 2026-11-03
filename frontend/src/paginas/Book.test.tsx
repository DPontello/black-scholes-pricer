import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import type { Book as Resposta, FamiliaBook } from "../api/book";
import type { Perfil } from "../api/cliente";
import { bookFalso, itemCoberta, PERFIL } from "../testes/book";
import { simularFetch } from "../testes/fetchFalso";
import { Book } from "./Book";

const ARROJADO: Perfil = { ...PERFIL, book: { ...PERFIL.book, preset: "arrojado", negocios_min: 3 } };

const VAZIA: FamiliaBook = { itens: [], referencias: [], exclusoes: [] };

function api(book: Resposta = bookFalso()) {
  return simularFetch((url, init) => {
    if (url === "/api/book") return { corpo: book };
    if (url === "/api/perfil/book" && init?.method === "PUT") return { corpo: ARROJADO };
    if (url === "/api/book/direcional")
      return {
        corpo: {
          itens: [itemCoberta({ nome: "trava de alta com call", estrutura: "trava_alta_call" })],
          referencias: [],
          exclusoes: [],
        },
      };
    return undefined;
  });
}

function ComEstado() {
  const [perfil, setPerfil] = useState<Perfil>(PERFIL);
  return <Book perfil={perfil} onPerfil={setPerfil} />;
}

function montar() {
  render(
    <MemoryRouter>
      <ComEstado />
    </MemoryRouter>,
  );
}

// Outra série, para a tabela não ter duas linhas com a mesma chave.
function itemVale3() {
  const { pernas, pedido } = itemCoberta();
  return itemCoberta({
    ativo: "VALE3",
    pernas: pernas.map((p) => ({ ...p, ticker: "VALEK650" })),
    pedido: { ...pedido, ativo: "VALE3", pernas: [{ ...pedido.pernas[0]!, ticker: "VALEK650" }] },
  });
}

const FAMILIAS = ["Renda", "Volatilidade", "Direcionais", "Proteção"];

test("o título é Melhores operações de hoje, com o pregão", async () => {
  api();
  montar();
  expect(screen.getByRole("heading", { name: "Melhores operações de hoje", level: 1 })).toBeTruthy();
  expect(await screen.findByText("pregão de 23/10/2026 · fim de dia (B3)")).toBeTruthy();
});

test("os ativos indisponíveis ficam recolhidos no fim, com o motivo de cada um", async () => {
  api(
    bookFalso({
      indisponiveis: [
        { simbolo: "BBDC4", motivo: "sem negócios no pregão" },
        { simbolo: "ITUB4", motivo: "ITUB4: sem fechamento nos COTAHIST" },
      ],
    }),
  );
  montar();
  const detalhes = (await screen.findByText("Ativos indisponíveis (2)")).closest("details")!;
  expect(detalhes.open).toBe(false);
  expect(within(detalhes).getAllByRole("listitem").map((i) => i.textContent)).toEqual([
    "BBDC4: sem negócios no pregão",
    "ITUB4: sem fechamento nos COTAHIST",
  ]);
  expect(
    screen.getByRole("tabpanel").compareDocumentPosition(detalhes) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
});

test("sem ativos indisponíveis não há a seção", async () => {
  api();
  montar();
  await screen.findByText(/pregão de/);
  expect(screen.queryByText(/Ativos indisponíveis/)).toBeNull();
});

test("o preset fica fechado e abre no ajustar", async () => {
  api();
  montar();
  await screen.findByText(/pregão de/);
  expect(screen.getByText(/Critérios:/).textContent).toContain("Critérios: Moderado");
  expect(screen.queryByLabelText("Delta mínimo")).toBeNull();
  const ajustar = screen.getByRole("button", { name: /ajustar/ });
  expect(ajustar.getAttribute("aria-expanded")).toBe("false");
  fireEvent.click(ajustar);
  expect(ajustar.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByLabelText("Delta mínimo")).toBeTruthy();
});

test("a vol vira etiquetas com palavras", async () => {
  const base = bookFalso().contextos[0]!;
  api(
    bookFalso({
      contextos: [
        { ...base, ativo: "BOVA11", regime: "baixa" },
        { ...base, ativo: "VALE3", regime: "alta" },
        { ...base, ativo: "PETR4", regime: "neutra", extrapolada: true },
        { ...base, ativo: "ITUB4", regime: "baixa", regime_pela_hv: true },
        { ...base, ativo: "BBDC4", regime: null, motivo: "BBDC4: sem histórico de IV" },
        { ...base, ativo: "ABEV3", regime: null, motivo: "arquivos da B3 ilegíveis: cadastro.xml" },
      ],
    }),
  );
  montar();
  const etiquetas = within(await screen.findByRole("list", { name: "Vol de cada ativo" })).getAllByRole(
    "listitem",
  );
  expect(etiquetas.map((e) => e.textContent)).toEqual([
    "BOVA11 · vol barata",
    "VALE3 · vol cara",
    "PETR4 · vol normal",
    "ITUB4 · vol barata (pela HV)",
    "BBDC4: sem histórico de IV",
    "ABEV3 · arquivos da B3 ilegíveis: cadastro.xml",
  ]);
  expect(etiquetas[0]!.title).toBe("IV 30: 30,0% · HV 21: 40,0% · IV rank: 12,0% · percentil: 8,0%");
  expect(etiquetas[2]!.title).toContain("IV 30: 30,0% (extrapolada)");
  expect(etiquetas[4]!.title).toBe("");
  expect(etiquetas[5]!.title).toBe("");
});

test("ao lado das etiquetas, o link explica vol barata ou cara", async () => {
  api();
  montar();
  const link = await screen.findByRole("link", { name: "o que é vol barata ou cara?" });
  expect(link.getAttribute("href")).toBe("/aprender/termos#vol-cara-barata");
});

test("um cartão por família, com o primeiro item", async () => {
  const base = bookFalso();
  api(
    bookFalso({
      familias: {
        ...base.familias,
        renda: {
          ...base.familias.renda,
          itens: [itemCoberta(), itemVale3()],
        },
      },
    }),
  );
  montar();
  await screen.findByText(/pregão de/);
  const cartoes = screen.getAllByRole("article");
  expect(cartoes).toEqual(FAMILIAS.map((nome) => screen.getByRole("article", { name: nome })));
  const renda = within(cartoes[0]!);
  expect(renda.getByText(/^venda coberta · PETR4 · vence 19\/11\/2026/)).toBeTruthy();
  expect(renda.queryByText(/VALE3/)).toBeNull();
  expect(renda.getByRole("button", { name: "Abrir no montador" })).toBeTruthy();
});

test("família sem item diz nada hoje com o motivo", async () => {
  const base = bookFalso();
  api(
    bookFalso({
      familias: {
        ...base.familias,
        volatilidade: { ...VAZIA, referencias: [itemCoberta({ qualidade: "indicativo" })] },
        direcionais: { ...VAZIA, exclusoes: [{ simbolo: "PETRL340/?", motivo: "sem strike" }] },
        protecao: VAZIA,
      },
    }),
  );
  montar();
  await screen.findByText(/pregão de/);
  const volatilidade = within(screen.getByRole("article", { name: "Volatilidade" }));
  expect(volatilidade.getByText("Nada hoje em Volatilidade")).toBeTruthy();
  expect(volatilidade.getByText("sem preço de compra e venda agora")).toBeTruthy();
  const direcionais = within(screen.getByRole("article", { name: "Direcionais" }));
  expect(direcionais.getByText("Nada hoje em Direcionais")).toBeTruthy();
  expect(direcionais.getByText("nenhuma série passou nos filtros")).toBeTruthy();
  const protecao = within(screen.getByRole("article", { name: "Proteção" }));
  expect(protecao.getByText("Nada hoje em Proteção")).toBeTruthy();
  expect(protecao.getByText("nada passou nos filtros do preset")).toBeTruthy();
});

test("o cartão vazio leva à aba da família", async () => {
  api();
  montar();
  await screen.findByText(/pregão de/);
  const aba = screen.getByRole("tab", { name: "Volatilidade (0)" });
  expect(aba.getAttribute("aria-selected")).toBe("false");
  fireEvent.click(
    within(screen.getByRole("article", { name: "Volatilidade" })).getByRole("button", {
      name: "ver a aba Volatilidade",
    }),
  );
  expect(aba.getAttribute("aria-selected")).toBe("true");
  expect(screen.getByRole("tab", { name: "Renda (1)" }).getAttribute("aria-selected")).toBe("false");
});

test("book sem pregão diz o motivo e não mostra cartões", async () => {
  api(
    bookFalso({
      pregao: null,
      contextos: [],
      indisponiveis: [{ simbolo: "PETR4", motivo: "sem cadeia no COTAHIST" }],
      familias: { renda: VAZIA, volatilidade: VAZIA, direcionais: VAZIA, protecao: VAZIA },
    }),
  );
  montar();
  expect(
    await screen.findByText("Sem pregão de fim de dia: importe um COTAHIST em Arquivos B3."),
  ).toBeTruthy();
  expect(screen.queryByRole("article")).toBeNull();
  expect(screen.queryByRole("tab")).toBeNull();
  expect(screen.getByText("Ativos indisponíveis (1)")).toBeTruthy();
});

test("as abas trazem a contagem e mostram a tabela da família", async () => {
  const base = bookFalso();
  api(
    bookFalso({
      familias: {
        ...base.familias,
        protecao: { ...VAZIA, itens: [itemCoberta({ nome: "put protetora" })] },
      },
    }),
  );
  montar();
  await screen.findByText(/pregão de/);
  expect(screen.getAllByRole("tab").map((a) => a.textContent)).toEqual([
    "Renda (1)",
    "Volatilidade (0)",
    "Direcionais (0)",
    "Proteção (1)",
  ]);
  const renda = screen.getByRole("tab", { name: "Renda (1)" });
  expect(renda.getAttribute("aria-selected")).toBe("true");
  expect(within(screen.getByRole("tabpanel")).getByRole("button", { name: "venda coberta" })).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: "Proteção (1)" }));
  expect(renda.getAttribute("aria-selected")).toBe("false");
  const painel = within(screen.getByRole("tabpanel"));
  expect(painel.getByRole("button", { name: "put protetora" })).toBeTruthy();
  expect(painel.queryByRole("button", { name: "venda coberta" })).toBeNull();
});

test("a linha expandida não sobrevive à troca de aba", async () => {
  const base = bookFalso();
  // A mesma série nas duas famílias: a chave da linha é a mesma.
  api(bookFalso({ familias: { ...base.familias, protecao: { ...VAZIA, itens: [itemCoberta()] } } }));
  montar();
  await screen.findByText(/pregão de/);
  fireEvent.click(within(screen.getByRole("tabpanel")).getByRole("button", { name: "venda coberta" }));
  expect(screen.getByText("prêmio por ação")).toBeTruthy();

  fireEvent.click(screen.getByRole("tab", { name: "Proteção (1)" }));
  expect(
    within(screen.getByRole("tabpanel")).getByRole("button", { name: "venda coberta" }).getAttribute("aria-expanded"),
  ).toBe("false");

  fireEvent.click(screen.getByRole("tab", { name: "Renda (1)" }));
  expect(
    within(screen.getByRole("tabpanel")).getByRole("button", { name: "venda coberta" }).getAttribute("aria-expanded"),
  ).toBe("false");
  expect(screen.queryByText("prêmio por ação")).toBeNull();
});

test("referências ficam recolhidas e rotuladas, e as exclusões com o motivo", async () => {
  api();
  montar();
  const referencias = (
    await screen.findByText("Referências sem preço de compra e venda agora (1)")
  ).closest("details")!;
  expect(referencias.open).toBe(false);
  expect(referencias.textContent).toContain("put coberta");
  expect(referencias.textContent).toContain("preço indicativo");
  const exclusoes = screen.getByText("Fora do book por dado ruim (1)").closest("details")!;
  expect(exclusoes.open).toBe(false);
  expect(exclusoes.textContent).toContain("PETRL340/?: sem strike 1 passo mais fora");
});

test("trocar o preset salva no perfil e varre o book de novo", async () => {
  const fetch = api();
  montar();
  await screen.findByText(/pregão de/);
  fireEvent.click(screen.getByRole("button", { name: /ajustar/ }));
  fireEvent.change(screen.getByLabelText("Preset"), { target: { value: "arrojado" } });
  await waitFor(() =>
    expect(fetch.mock.calls.filter(([u]) => u === "/api/book").length).toBe(2),
  );
  expect((screen.getByLabelText("Negócios mínimos por perna") as HTMLInputElement).value).toBe("3");
  expect(screen.getByText(/Critérios:/).textContent).toContain("Critérios: Arrojado");
});

test("o formulário da visão manda o alvo e mostra as operações", async () => {
  const fetch = api();
  montar();
  fireEvent.click(await screen.findByRole("tab", { name: "Direcionais (0)" }));
  fireEvent.change(screen.getByLabelText("Direção"), { target: { value: "alta" } });
  fireEvent.change(screen.getByLabelText("Preço-alvo"), { target: { value: "33.5" } });
  fireEvent.change(screen.getByLabelText("Vencimento"), { target: { value: "2026-11-19" } });
  fireEvent.click(screen.getByRole("button", { name: "Ver as operações" }));
  expect(await screen.findByRole("button", { name: "trava de alta com call" })).toBeTruthy();
  const pedido = fetch.mock.calls.find(([u]) => u === "/api/book/direcional");
  expect(JSON.parse(String(pedido?.[1]?.body))).toEqual({
    ativo: "PETR4",
    direcao: "alta",
    alvo: 33.5,
    vencimento: "2026-11-19",
  });
});

test("erro ao montar o book aparece", async () => {
  simularFetch(() => ({ status: 404, corpo: { erro: "NoActiveProfileError", mensagem: "abra um perfil" } }));
  montar();
  expect((await screen.findByRole("alert")).textContent).toBe("abra um perfil");
});

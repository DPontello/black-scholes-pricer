import { fireEvent, render, screen, within } from "@testing-library/react";
import * as echarts from "echarts/core";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";

import type { Exemplo } from "../api/aprender";
import { Aprender } from "../paginas/Aprender";
import { EXEMPLOS } from "../testes/aprender";
import { simularFetch } from "../testes/fetchFalso";
import { TEXTOS_OPERACOES, type TextoOperacao } from "./operacoes";

function Sonda() {
  const { pathname, search } = useLocation();
  return <output data-testid="endereco">{pathname + search}</output>;
}

function montar(endereco: string, opcoes: { comPerfil?: boolean; exemplos?: Exemplo[] } = {}) {
  const fetch = simularFetch((url) =>
    url === "/api/aprender/exemplos" ? { corpo: opcoes.exemplos ?? EXEMPLOS } : undefined,
  );
  render(
    <MemoryRouter initialEntries={[endereco]}>
      <Routes>
        <Route path="/aprender/*" element={<Aprender comPerfil={opcoes.comPerfil ?? true} />} />
        <Route path="/montador" element={<p>Montador</p>} />
      </Routes>
      <Sonda />
    </MemoryRouter>,
  );
  return fetch;
}

const endereco = () => screen.getByTestId("endereco").textContent;

// A operação aberta à direita: espera a lista chegar da API e devolve o painel dela.
async function operacao(nome: string) {
  const titulo = await screen.findByRole("heading", { level: 2, name: nome });
  return within(titulo.closest("article") as HTMLElement);
}

function exemploCom(chave: string, mudancas: Partial<Exemplo>): Exemplo[] {
  return EXEMPLOS.map((e) => (e.chave === chave ? { ...e, ...mudancas } : e));
}

const NOMES_NA_LISTA = [
  ["Renda", ["Venda coberta", "Put coberta", "Trava de alta com put", "Trava de baixa com call"]],
  [
    "Direcionais",
    ["Compra de call", "Compra de put", "Trava de alta com call", "Trava de baixa com put"],
  ],
  [
    "Volatilidade",
    [
      "Straddle comprado",
      "Straddle vendido",
      "Strangle comprado",
      "Strangle vendido",
      "Iron condor vendido",
      "Iron condor comprado",
      "Borboleta comprada",
      "Borboleta vendida",
    ],
  ],
  ["Proteção", ["Put protetora", "Collar"]],
] as const;

test("a lista tem as quatro famílias e as 18 operações, na ordem do catálogo", async () => {
  montar("/aprender/operacoes");
  const lista = within(await screen.findByRole("navigation", { name: "Lista de operações" }));
  expect(lista.getAllByRole("list")).toHaveLength(4);
  for (const [familia, nomes] of NOMES_NA_LISTA) {
    const grupo = within(lista.getByRole("list", { name: familia }));
    expect(grupo.getAllByRole("link").map((link) => link.textContent)).toEqual(nomes);
  }
  expect(lista.getAllByRole("link").map((link) => link.textContent)).toEqual(
    NOMES_NA_LISTA.flatMap(([, nomes]) => nomes),
  );
});

test("/aprender/operacoes abre a primeira operação (venda coberta)", async () => {
  montar("/aprender/operacoes");
  await operacao("Venda coberta");
  const lista = within(screen.getByRole("navigation", { name: "Lista de operações" }));
  expect(lista.getByRole("link", { name: "Venda coberta" }).getAttribute("aria-current")).toBe("page");
  expect(lista.getByRole("link", { name: "Put coberta" }).getAttribute("aria-current")).toBeNull();
});

test("/aprender/operacoes/iron_condor_vendido abre a dele", async () => {
  montar("/aprender/operacoes/iron_condor_vendido");
  await operacao("Iron condor vendido");
  const lista = within(screen.getByRole("navigation", { name: "Lista de operações" }));
  expect(
    lista.getByRole("link", { name: "Iron condor vendido" }).getAttribute("aria-current"),
  ).toBe("page");
  expect(lista.getByRole("link", { name: "Venda coberta" }).getAttribute("aria-current")).toBeNull();
});

test("um modelo desconhecido abre a primeira operação, sem erro", async () => {
  montar("/aprender/operacoes/xyz");
  await operacao("Venda coberta");
  expect(screen.queryByRole("alert")).toBeNull();
  expect(endereco()).toBe("/aprender/operacoes/xyz");
});

test("clicar numa operação da lista troca o painel sem pedir os exemplos de novo", async () => {
  const fetch = montar("/aprender/operacoes");
  await operacao("Venda coberta");
  fireEvent.click(screen.getByRole("link", { name: "Put coberta" }));
  await operacao("Put coberta");
  expect(endereco()).toBe("/aprender/operacoes/put_coberta");
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("a venda coberta mostra os seis blocos, com os textos dela", async () => {
  montar("/aprender/operacoes/venda_coberta");
  const painel = await operacao("Venda coberta");
  const blocos = painel.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
  expect(blocos).toEqual([
    "O que é",
    "Quando usar",
    "Como montar",
    "Exemplo",
    "O que pode dar errado",
    "No app",
  ]);
  const texto = TEXTOS_OPERACOES.venda_coberta;
  expect(texto).toBeDefined();
  for (const parte of [texto?.oQueE, texto?.quandoUsar, texto?.comoMontar])
    expect(painel.getByText(parte as string)).toBeTruthy();
  expect(painel.getByText(texto?.oQuePodeDarErrado as string)).toBeTruthy();
  expect(painel.getByText(texto?.noApp as string)).toBeTruthy();
});

test("as etiquetas começam pela família e seguem com as três do texto", async () => {
  montar("/aprender/operacoes/venda_coberta");
  const painel = await operacao("Venda coberta");
  const etiquetas = painel.getByRole("list", { name: "Etiquetas" });
  expect(within(etiquetas).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
    "Renda",
    ...(TEXTOS_OPERACOES.venda_coberta?.etiquetas ?? []),
  ]);
});

test("o exemplo da venda coberta sai dos números da API", async () => {
  montar("/aprender/operacoes/venda_coberta");
  const painel = await operacao("Venda coberta");
  expect(painel.getByText(/PETR4 a R\$ 50,00/)).toBeTruthy();
  expect(painel.getByText("compra 100 ações a R$ 50,00")).toBeTruthy();
  expect(painel.getByText("vende 100 calls de strike R$ 52,00 a R$ 1,14")).toBeTruthy();
  expect(painel.getByText("recebe R$ 114,00")).toBeTruthy();
  const cenarios: [string, string][] = [
    ["R$ 45,00 (cai 10%)", "perde R$ 386,00"],
    ["R$ 50,00 (fica)", "ganha R$ 114,00"],
    ["R$ 55,00 (sobe 10%)", "ganha R$ 314,00"],
  ];
  for (const [preco, resultado] of cenarios) {
    const linha = within(painel.getByText(preco).closest("tr") as HTMLElement);
    expect(linha.getByText(resultado)).toBeTruthy();
  }
  expect(painel.getByText("empata em R$ 48,86")).toBeTruthy();
  expect(painel.getByText("ganho máximo R$ 314,00")).toBeTruthy();
  expect(painel.getByText("perda máxima R$ 4.886,00")).toBeTruthy();
  expect(painel.getByText("exemplo, sem custos nem IR")).toBeTruthy();
});

test("o straddle vendido tem perda máxima sem limite", async () => {
  montar("/aprender/operacoes/straddle_vendido");
  const painel = await operacao("Straddle vendido");
  expect(painel.getByText("perda máxima sem limite")).toBeTruthy();
  expect(painel.getByText("ganho máximo R$ 346,00")).toBeTruthy();
});

test("sem ganho limitado, o exemplo diz ganho máximo sem limite; débito é 'paga'", async () => {
  montar("/aprender/operacoes/compra_call");
  const painel = await operacao("Compra de call");
  expect(painel.getByText("ganho máximo sem limite")).toBeTruthy();
  expect(painel.getByText("paga R$ 202,00")).toBeTruthy();
  expect(painel.queryByText(/ações a R\$/)).toBeNull();
});

test("dois empates viram 'empata em R$ X e em R$ Y'", async () => {
  montar("/aprender/operacoes/straddle_comprado");
  const painel = await operacao("Straddle comprado");
  expect(painel.getByText("empata em R$ 46,54 e em R$ 53,46")).toBeTruthy();
});

test("sem empate, a linha 'empata em' não aparece", async () => {
  montar("/aprender/operacoes/venda_coberta", {
    exemplos: exemploCom("venda_coberta", { empates: [] }),
  });
  const painel = await operacao("Venda coberta");
  expect(painel.queryByText(/empata em/)).toBeNull();
});

test("resultado zero vira 'fica no zero a zero'", async () => {
  montar("/aprender/operacoes/venda_coberta", {
    exemplos: exemploCom("venda_coberta", {
      cenarios: [
        { preco: 45, resultado: -386 },
        { preco: 50, resultado: 0 },
        { preco: 55, resultado: 314 },
      ],
    }),
  });
  const painel = await operacao("Venda coberta");
  const linha = within(painel.getByText("R$ 50,00 (fica)").closest("tr") as HTMLElement);
  expect(linha.getByText("fica no zero a zero")).toBeTruthy();
});

test("o gráfico do resultado no vencimento aparece e desenha a curva com o preço atual e o zero", async () => {
  montar("/aprender/operacoes/venda_coberta");
  await operacao("Venda coberta");
  expect(screen.getByRole("img", { name: "Resultado no vencimento de venda coberta" })).toBeTruthy();
  const instancia = vi.mocked(echarts.init).mock.results.at(-1)?.value as {
    setOption: ReturnType<typeof vi.fn>;
  };
  const opcoes = instancia.setOption.mock.calls.at(-1)?.[0] as {
    xAxis: { min: number; max: number };
    series: { data: [number, number][]; markLine: { data: object[] } }[];
  };
  // Só os pontos em volta do preço atual: a curva vai além e esticaria o eixo do resultado.
  expect(opcoes.xAxis).toMatchObject({ min: 40, max: 60 });
  expect(opcoes.series).toHaveLength(1);
  expect(opcoes.series[0]?.data).toEqual([
    [45, -386],
    [50, 114],
    [55, 314],
  ]);
  expect(opcoes.series[0]?.markLine.data).toEqual([{ xAxis: 50, name: "preço atual" }, { yAxis: 0 }]);
});

test("com perfil, 'Montar uma venda coberta no Montador' abre o Montador com o modelo", async () => {
  montar("/aprender/operacoes/venda_coberta");
  const painel = await operacao("Venda coberta");
  const botao = painel.getByRole("button", { name: "Montar uma venda coberta no Montador" });
  expect((botao as HTMLButtonElement).disabled).toBe(false);
  fireEvent.click(botao);
  expect(endereco()).toBe("/montador?modelo=venda_coberta");
  expect(screen.getByText("Montador")).toBeTruthy();
});

test("sem perfil, o botão fica desabilitado com o motivo", async () => {
  montar("/aprender/operacoes/venda_coberta", { comPerfil: false });
  const painel = await operacao("Venda coberta");
  const botao = painel.getByRole("button", { name: "Montar uma venda coberta no Montador" });
  expect((botao as HTMLButtonElement).disabled).toBe(true);
  expect(painel.getByText("abra um perfil primeiro")).toBeTruthy();
  fireEvent.click(botao);
  expect(endereco()).toBe("/aprender/operacoes/venda_coberta");
});

test("o botão concorda com o gênero do nome: um straddle, uma put", async () => {
  montar("/aprender/operacoes/straddle_vendido");
  const painel = await operacao("Straddle vendido");
  expect(painel.getByRole("button", { name: "Montar um straddle vendido no Montador" })).toBeTruthy();
});

test("enquanto os exemplos chegam, avisa; se a API falha, mostra o erro", async () => {
  simularFetch((url) =>
    url === "/api/aprender/exemplos"
      ? { status: 500, corpo: { erro: "Falha", mensagem: "a API caiu" } }
      : undefined,
  );
  render(
    <MemoryRouter initialEntries={["/aprender/operacoes"]}>
      <Routes>
        <Route path="/aprender/*" element={<Aprender comPerfil />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText("Carregando os exemplos…")).toBeTruthy();
  expect((await screen.findByRole("alert")).textContent).toBe("a API caiu");
  expect(screen.queryByText("Carregando os exemplos…")).toBeNull();
});

test("há texto para as 18 operações, sem vazio e sem número", () => {
  expect(Object.keys(TEXTOS_OPERACOES).sort()).toEqual(EXEMPLOS.map((e) => e.chave).sort());
  expect(EXEMPLOS).toHaveLength(18);
  for (const [chave, texto] of Object.entries(TEXTOS_OPERACOES)) {
    expect(texto.etiquetas, chave).toHaveLength(3);
    const frases = [
      ...texto.etiquetas,
      texto.oQueE,
      texto.quandoUsar,
      texto.comoMontar,
      texto.oQuePodeDarErrado,
      texto.noApp,
    ];
    for (const frase of frases) {
      expect(frase.trim(), chave).not.toBe("");
      expect(frase, chave).not.toMatch(/\d/);
    }
  }
});

const FORA_DO_BOOK = ["straddle_vendido", "iron_condor_comprado", "borboleta_vendida"];
const ROTULO_DA_FAMILIA = {
  renda: "Renda",
  direcionais: "Direcionais",
  volatilidade: "Volatilidade",
  protecao: "Proteção",
};

test("'No app' diz a família do Book; as três que o Book não varre dizem que só vão ao Montador", () => {
  for (const exemplo of EXEMPLOS) {
    const noApp = TEXTOS_OPERACOES[exemplo.chave]?.noApp ?? "";
    if (FORA_DO_BOOK.includes(exemplo.chave)) {
      expect(noApp, exemplo.chave).toMatch(/só se monta no Montador/);
      expect(noApp, exemplo.chave).not.toContain(ROTULO_DA_FAMILIA[exemplo.familia]);
    } else {
      expect(noApp, exemplo.chave).toContain(`família ${ROTULO_DA_FAMILIA[exemplo.familia]}`);
    }
  }
});

function texto(chave: string): TextoOperacao {
  const achado = TEXTOS_OPERACOES[chave];
  expect(achado, chave).toBeDefined();
  return achado as TextoOperacao;
}

test("compra de call e de put: perde tudo só além do strike; entre o strike e o empate, só parte", () => {
  expect(texto("compra_call").oQuePodeDarErrado).toMatch(/abaixo do strike.*perde o prêmio inteiro/);
  expect(texto("compra_call").oQuePodeDarErrado).toMatch(/Entre o strike e o ponto de empate.*só parte/);
  expect(texto("compra_put").oQuePodeDarErrado).toMatch(/acima do strike.*perde o prêmio inteiro/);
  expect(texto("compra_put").oQuePodeDarErrado).toMatch(/Entre o ponto de empate e o strike.*só parte/);
});

test("travas de crédito e iron condor vendido: o ganho encolhe e só vira perda além do empate", () => {
  for (const chave of ["trava_alta_put", "trava_baixa_call", "iron_condor_vendido"]) {
    expect(texto(chave).oQuePodeDarErrado, chave).toMatch(
      /ganho vai encolhendo e, além do ponto de empate, vira perda/,
    );
    expect(texto(chave).oQuePodeDarErrado, chave).toMatch(/perda para de crescer/);
  }
});

test("strangle comprado e iron condor comprado: só ganham passando do ponto de empate", () => {
  for (const chave of ["strangle_comprado", "iron_condor_comprado"]) {
    expect(texto(chave).oQueE, chave).toMatch(/passar do ponto de empate/);
    expect(texto(chave).oQuePodeDarErrado, chave).toMatch(/antes do ponto de empate, (você )?perde só parte/);
  }
});

test("travas de débito e borboleta comprada: dizem em que ponto perdem o que pagaram", () => {
  expect(texto("trava_alta_call").oQuePodeDarErrado).toMatch(/não subir acima do strike da call comprada/);
  expect(texto("trava_baixa_put").oQuePodeDarErrado).toMatch(/não cair abaixo do strike da put comprada/);
  expect(texto("borboleta_comprada").oQuePodeDarErrado).toMatch(/além dos strikes de fora.*perde tudo o que pagou/);
});

test("'Como montar' das travas com put segue a ordem das pernas do catálogo", () => {
  expect(texto("trava_alta_put").comoMontar).toMatch(/^Compra uma put com strike mais baixo e vende outra com strike mais alto/);
  expect(texto("trava_baixa_put").comoMontar).toMatch(/^Vende uma put com strike mais baixo e compra outra com strike mais alto/);
});

test("'No app': as de Volatilidade só podem aparecer no Book, conforme a vol e o preset", () => {
  for (const chave of ["straddle_comprado", "strangle_comprado"])
    expect(texto(chave).noApp, chave).toMatch(/^Pode aparecer no Book, na família Volatilidade, quando a vol do ativo não está cara\./);
  for (const chave of ["iron_condor_vendido", "borboleta_comprada"])
    expect(texto(chave).noApp, chave).toMatch(/^Pode aparecer no Book, na família Volatilidade, quando a vol do ativo não está barata\./);
  expect(texto("strangle_vendido").noApp).toMatch(
    /^Pode aparecer no Book, na família Volatilidade, quando a vol do ativo não está barata e .*"Aceitar perda ilimitada"/,
  );
  expect(texto("straddle_vendido").noApp).not.toMatch(/Pode aparecer/);
});

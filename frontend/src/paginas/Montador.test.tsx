import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";

import type { Cadeia, EstadoAoVivo } from "../api/aoVivo";
import { analiseCoberta } from "../testes/analise";
import { simularFetch } from "../testes/fetchFalso";
import { Montador } from "./Montador";

const MODELOS = [
  {
    chave: "venda_coberta",
    familia: "renda",
    nome: "venda coberta",
    pernas: [{ tipo: "call", lado: "venda", proporcao: 1, passo: 1 }],
    acao: "compra",
  },
];

const SUGESTAO = {
  ativo: "PETR4",
  pernas: [{ ticker: "PETRK541", lado: "venda", quantidade: 100, preco: null }],
  acao: { lado: "compra", quantidade: 100, origem: "compra", preco: null },
  modelo: "venda_coberta",
};

const CADEIA: Cadeia = {
  ativo: "PETR4",
  spot: 52.51,
  fonte: "fim_de_dia",
  hora: "2026-10-28T18:00:00-03:00",
  vencimentos: [
    { data: "2026-10-30", dias_uteis: 2, series: [] },
    {
      data: "2026-11-19",
      dias_uteis: 15,
      series: [
        {
          ticker: "PETRK541",
          tipo: "call",
          strike: 52.91,
          estilo: "american",
          compra: 1.72,
          venda: 1.94,
          ultimo: 1.8,
          negocios: 300,
          volume: 54000,
          iv: 0.31,
          delta: 0.48,
          lote: 100,
        },
      ],
    },
  ],
  disponiveis: [
    { data: "2026-10-30", dias_uteis: 2, semanal: true },
    { data: "2026-11-19", dias_uteis: 15, semanal: false },
  ],
  rejeitadas: [],
};

const AO_VIVO: EstadoAoVivo = {
  conectado: true,
  status: null,
  cotacoes: [],
  motivoCotacoes: null,
  cadeia: CADEIA,
  cadeiaIndisponivel: null,
  carteira: null,
  carteiraIndisponivel: null,
  alertas: null,
  alertasIndisponiveis: null,
};

function api(analise: unknown = analiseCoberta()) {
  return simularFetch((url, init) => {
    if (url === "/api/montador/modelos") return { corpo: MODELOS };
    if (url === "/api/simulacoes" && init?.method === "POST")
      return {
        status: 201,
        corpo: { id: "a1", nome: "x", criada_em: "2026-11-04T11:00:00Z", pedido: SUGESTAO },
      };
    if (url === "/api/simulacoes") return { corpo: { simulacoes: [], ilegiveis: [] } };
    if (url.startsWith("/api/montador/sugestao")) return { corpo: SUGESTAO };
    if (url === "/api/montador/analise") return analise as never;
    return undefined;
  });
}

function montar(seguir = vi.fn()) {
  render(
    <MemoryRouter initialEntries={["/montador?ativo=PETR4"]}>
      <Montador aoVivo={AO_VIVO} seguirCadeia={seguir} />
    </MemoryRouter>,
  );
  return seguir;
}

function corpos(fetch: ReturnType<typeof simularFetch>, url: string): unknown[] {
  return fetch.mock.calls
    .filter(([u, init]) => u === url && init?.body !== undefined)
    .map(([, init]) => JSON.parse(String(init?.body)) as unknown);
}

test("modelo pronto pede a sugestão no vencimento da cadeia e mostra a análise", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  const seguir = montar();
  expect(seguir).toHaveBeenCalledWith("PETR4", null);
  const modelo = await screen.findByLabelText("Modelo pronto");
  await screen.findByRole("option", { name: "venda coberta" });
  fireEvent.change(modelo, { target: { value: "venda_coberta" } });
  expect(await screen.findByText(/Você paga R\$ 5\.080,00 agora/)).toBeTruthy();
  expect(
    fetch.mock.calls.some(([u]) =>
      String(u).includes("sugestao?ativo=PETR4&modelo=venda_coberta&vencimento=2026-11-19"),
    ),
  ).toBe(true);
  expect(corpos(fetch, "/api/montador/analise").at(-1)).toEqual(SUGESTAO);
});

test("o + da cadeia põe a série como compra, sem modelo", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  montar();
  fireEvent.click(await screen.findByRole("tab", { name: "19/11 (15 du)" }));
  fireEvent.click(await screen.findByRole("button", { name: "Pôr PETRK541 no montador" }));
  await waitFor(() => expect(corpos(fetch, "/api/montador/analise").length).toBe(1));
  expect(corpos(fetch, "/api/montador/analise")[0]).toEqual({
    ativo: "PETR4",
    pernas: [{ ticker: "PETRK541", lado: "compra", quantidade: 100, preco: null }],
    acao: null,
    modelo: null,
  });
});

test("erro de forma do modelo aparece com a saída de montar sem o modelo", async () => {
  api({
    status: 422,
    corpo: { erro: "InvalidStrategyError", mensagem: "as pernas não formam o modelo venda coberta" },
  });
  montar();
  fireEvent.change(await screen.findByLabelText("Modelo pronto"), {
    target: { value: "venda_coberta" },
  });
  expect(await screen.findByRole("alert")).toBeTruthy();
  expect(screen.getByText(/não formam o modelo/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Montar sem o modelo" })).toBeTruthy();
});

test("salvar simulação manda o nome e o pedido", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  montar();
  fireEvent.change(await screen.findByLabelText("Modelo pronto"), {
    target: { value: "venda_coberta" },
  });
  await screen.findByText(/Você paga/);
  fireEvent.change(screen.getByLabelText("Nome da simulação"), {
    target: { value: "coberta nov" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Salvar simulação" }));
  await waitFor(() => expect(corpos(fetch, "/api/simulacoes").length).toBe(1));
  expect(corpos(fetch, "/api/simulacoes")[0]).toEqual({ nome: "coberta nov", ...SUGESTAO });
});

test("salvar e registrar ficam logo abaixo das pernas, antes do resumo e do gráfico", async () => {
  api({ corpo: analiseCoberta() });
  montar();
  fireEvent.change(await screen.findByLabelText("Modelo pronto"), {
    target: { value: "venda_coberta" },
  });
  const grafico = await screen.findByRole("img", { name: /Resultado de/ });
  for (const nome of ["Salvar simulação", "Registrar como executada"]) {
    const botao = screen.getByRole("button", { name: nome });
    expect(botao.compareDocumentPosition(grafico) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  }
});

function Sonda() {
  const local = useLocation();
  return <pre data-testid="estado">{JSON.stringify(local.state)}</pre>;
}

test("registrar como executada leva à carteira com as pernas e os preços da análise", async () => {
  api({ corpo: analiseCoberta() });
  render(
    <MemoryRouter initialEntries={["/montador?ativo=PETR4"]}>
      <Routes>
        <Route path="/montador" element={<Montador aoVivo={AO_VIVO} seguirCadeia={vi.fn()} />} />
        <Route path="/carteira" element={<Sonda />} />
      </Routes>
    </MemoryRouter>,
  );
  const registrar = (await screen.findByRole("button", {
    name: "Registrar como executada",
  })) as HTMLButtonElement;
  expect(registrar.disabled).toBe(true);
  fireEvent.change(await screen.findByLabelText("Modelo pronto"), {
    target: { value: "venda_coberta" },
  });
  await screen.findByText(/Você paga/);
  fireEvent.click(registrar);
  const estado = JSON.parse((await screen.findByTestId("estado")).textContent ?? "null") as {
    registro: { nome: string; pernas: unknown[]; acao: unknown };
  };
  expect(estado.registro.nome).toBe("venda coberta");
  expect(estado.registro.pernas).toEqual([
    { ticker: "PETRK541", lado: "venda", execucoes: [{ quantidade: 100, preco: 1.72, custos: null }] },
  ]);
  expect(estado.registro.acao).toEqual({
    lado: "compra",
    origem: "compra",
    execucoes: [{ quantidade: 100, preco: 52.52, custos: null }],
  });
});

test("o modelo usa o primeiro mensal, e o vencimento pode ser trocado", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  montar();
  const vencimento = (await screen.findByLabelText("Vencimento do modelo")) as HTMLSelectElement;
  expect(vencimento.value).toBe("2026-11-19");
  fireEvent.change(vencimento, { target: { value: "2026-10-30" } });
  await screen.findByRole("option", { name: "venda coberta" });
  fireEvent.change(screen.getByLabelText("Modelo pronto"), { target: { value: "venda_coberta" } });
  await waitFor(() =>
    expect(
      fetch.mock.calls.some(([u]) => String(u).includes("vencimento=2026-10-30")),
    ).toBe(true),
  );
});

test("o pedido que vem do book abre direto e é analisado pela cadeia do momento", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  render(
    <MemoryRouter
      initialEntries={[{ pathname: "/montador", search: "?ativo=PETR4", state: { pedido: SUGESTAO } }]}
    >
      <Montador aoVivo={AO_VIVO} seguirCadeia={vi.fn()} />
    </MemoryRouter>,
  );
  await waitFor(() => expect(corpos(fetch, "/api/montador/analise").length).toBe(1));
  expect(corpos(fetch, "/api/montador/analise")[0]).toEqual(SUGESTAO);
});

// O Aprender abre o Montador só com o modelo: o ativo é o primeiro da lista do perfil.
const COTACAO_PETR4 = {
  ativo: "PETR4",
  ultimo: 52.51,
  compra: 52.5,
  venda: 52.52,
  fechamento_anterior: 52.0,
  variacao_pct: 0.0098,
  negocios: 1000,
  volume: 1e6,
  hora: "2026-10-28T15:00:00-03:00",
  fonte: "ao_vivo" as const,
  motivo: null,
};

function SondaEndereco() {
  const { pathname, search } = useLocation();
  return <span data-testid="endereco">{pathname + search}</span>;
}

// A análise espera a digitação parar (300 ms): com a máquina carregada, o 1 s padrão é pouco.
const FOLGA = { timeout: 3000 };

function comModeloNoEndereco(endereco: string, cadeia: Cadeia | null) {
  const aoVivo = { ...AO_VIVO, cotacoes: [COTACAO_PETR4], cadeia };
  const vista = render(
    <MemoryRouter initialEntries={[endereco]}>
      <Routes>
        <Route path="/montador" element={<Montador aoVivo={aoVivo} seguirCadeia={vi.fn()} />} />
      </Routes>
      <SondaEndereco />
    </MemoryRouter>,
  );
  return (nova: Cadeia) =>
    vista.rerender(
      <MemoryRouter initialEntries={[endereco]}>
        <Routes>
          <Route
            path="/montador"
            element={<Montador aoVivo={{ ...aoVivo, cadeia: nova }} seguirCadeia={vi.fn()} />}
          />
        </Routes>
        <SondaEndereco />
      </MemoryRouter>,
    );
}

function sugestoes(fetch: ReturnType<typeof simularFetch>): string[] {
  return fetch.mock.calls.map(([u]) => String(u)).filter((u) => u.includes("/api/montador/sugestao"));
}

test("?modelo= espera a cadeia ('aguardando a cadeia') e então monta o modelo, uma vez só", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  const chegou = comModeloNoEndereco("/montador?modelo=venda_coberta", null);
  expect((await screen.findByRole("status")).textContent).toBe("venda coberta: aguardando a cadeia…");
  expect(sugestoes(fetch)).toEqual([]);
  chegou(CADEIA);
  await waitFor(() => expect(sugestoes(fetch)).toHaveLength(1), FOLGA);
  expect(sugestoes(fetch)[0]).toContain("sugestao?ativo=PETR4&modelo=venda_coberta&vencimento=2026-11-19");
  await waitFor(() => expect(corpos(fetch, "/api/montador/analise").at(-1)).toEqual(SUGESTAO), FOLGA);
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.getByTestId("endereco").textContent).toBe("/montador");
  chegou({ ...CADEIA, hora: "2026-10-28T18:05:00-03:00" });
  await waitFor(() => expect(corpos(fetch, "/api/montador/analise").length).toBeGreaterThan(1), FOLGA);
  expect(sugestoes(fetch)).toHaveLength(1);
});

test("?modelo= que não cabe na cadeia mostra o erro de hoje, e o resto da tela segue", async () => {
  simularFetch((url) => {
    if (url === "/api/montador/modelos") return { corpo: MODELOS };
    if (url === "/api/simulacoes") return { corpo: { simulacoes: [], ilegiveis: [] } };
    if (url.startsWith("/api/montador/sugestao"))
      return {
        status: 422,
        corpo: { erro: "InvalidStrategyError", mensagem: "faltam strikes para montar o modelo" },
      };
    return undefined;
  });
  comModeloNoEndereco("/montador?modelo=venda_coberta", CADEIA);
  expect((await screen.findByRole("alert", {}, FOLGA)).textContent).toContain("faltam strikes para montar o modelo");
  expect(screen.queryByRole("status")).toBeNull();
  expect((screen.getByLabelText("Modelo pronto") as HTMLSelectElement).disabled).toBe(false);
});

test("?modelo= desconhecido é ignorado", async () => {
  const fetch = api({ corpo: analiseCoberta() });
  comModeloNoEndereco("/montador?modelo=xyz", CADEIA);
  await screen.findByRole("option", { name: "venda coberta" });
  await waitFor(() => expect(screen.getByTestId("endereco").textContent).toBe("/montador"), FOLGA);
  expect(sugestoes(fetch)).toEqual([]);
  expect(screen.queryByRole("status")).toBeNull();
  expect(screen.queryByRole("alert")).toBeNull();
});

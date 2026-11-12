import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { simularFetch } from "../testes/fetchFalso";
import { ArquivosB3 } from "./ArquivosB3";

const STATUS_VELHO = {
  fonte: "fim_de_dia",
  cadastro: { data: "2026-10-20", dias_uteis: 6, velho: true },
  cadastro_motivo: null,
  cotahist: { de: "2026-01-02", ate: "2026-10-23", dias_uteis: 6, velho: true },
};

const LINK_CADASTRO =
  "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/";
const LINK_COTAHIST =
  "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/";

afterEach(() => {
  vi.useRealTimers();
});

function apiComArquivos(
  extra?: (url: string, init?: RequestInit) => ReturnType<Parameters<typeof simularFetch>[0]>,
  status: object = STATUS_VELHO,
) {
  return simularFetch((url, init) => {
    const resposta = extra?.(url, init);
    if (resposta !== undefined) return resposta;
    if (url === "/api/mercado/status") return { corpo: status };
    if (url === "/api/mercado/arquivos")
      return {
        corpo: [
          {
            tipo: "cotahist",
            nome: "COTAHIST_A2026.ZIP",
            data: "2026-10-23",
            importado_em: "2026-10-24T10:00:00-03:00",
          },
        ],
      };
    return undefined;
  });
}

// Cada passo da rotina é um item de lista com o link da B3 dentro.
async function passoDe(nome: RegExp) {
  const link = await screen.findByRole("link", { name: nome });
  const passo = link.closest("li");
  if (passo === null) throw new Error("o link não está dentro de um passo da rotina");
  return within(passo);
}

test("lista os arquivos com tipo e data", async () => {
  apiComArquivos();
  render(<ArquivosB3 />);
  expect(await screen.findByText("COTAHIST_A2026.ZIP")).toBeTruthy();
  expect(screen.getByText("23/10/2026")).toBeTruthy();
});

test("a rotina da semana tem os dois links exatos da B3", async () => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-03T15:00:00Z"));
  apiComArquivos();
  render(<ArquivosB3 />);
  const cadastro = await passoDe(/Cadastro de Instrumentos/);
  const cotahist = await passoDe(/COTAHIST anual/);
  expect(cadastro.getByRole("link", { name: /Cadastro de Instrumentos/ }).getAttribute("href")).toBe(
    LINK_CADASTRO,
  );
  expect(cotahist.getByRole("link", { name: /COTAHIST anual/ }).getAttribute("href")).toBe(
    LINK_COTAHIST,
  );
  expect(cadastro.getByText("pesquisa-pregao.zip")).toBeTruthy();
  expect(cotahist.getByText("COTAHIST_A2026.zip")).toBeTruthy();
  await cotahist.findByText(/hora de baixar/); // deixa o status chegar antes de desmontar
});

test("cadastro velho e cotahist velho dizem hora de baixar", async () => {
  apiComArquivos();
  render(<ArquivosB3 />);
  const cadastro = await passoDe(/Cadastro de Instrumentos/);
  const cotahist = await passoDe(/COTAHIST anual/);
  expect(await cadastro.findByText(/hora de baixar/)).toBeTruthy();
  expect(await cotahist.findByText(/hora de baixar/)).toBeTruthy();
  expect(cadastro.getByText(/20\/10\/2026/)).toBeTruthy();
  expect(cotahist.getByText(/23\/10\/2026/)).toBeTruthy();
});

test("arquivo recente diz em dia com a data", async () => {
  apiComArquivos(undefined, {
    ...STATUS_VELHO,
    cadastro: { data: "2026-11-03", dias_uteis: 0, velho: false },
    cotahist: { de: "2026-01-02", ate: "2026-10-30", dias_uteis: 1, velho: false },
  });
  render(<ArquivosB3 />);
  const cadastro = await passoDe(/Cadastro de Instrumentos/);
  const cotahist = await passoDe(/COTAHIST anual/);
  expect(await cadastro.findByText(/em dia/)).toBeTruthy();
  expect(cadastro.getByText(/03\/11\/2026/)).toBeTruthy();
  expect(await cotahist.findByText(/em dia/)).toBeTruthy();
  expect(cotahist.getByText(/30\/10\/2026/)).toBeTruthy();
  expect(screen.queryByText(/hora de baixar/)).toBeNull();
});

test("cotahist sem idade mostra só a data", async () => {
  apiComArquivos(undefined, {
    ...STATUS_VELHO,
    cotahist: { de: "2026-01-02", ate: "2026-10-30", dias_uteis: null, velho: false },
  });
  render(<ArquivosB3 />);
  const cotahist = await passoDe(/COTAHIST anual/);
  expect(await cotahist.findByText(/30\/10\/2026/)).toBeTruthy();
  expect(cotahist.queryByText(/em dia/)).toBeNull();
  expect(cotahist.queryByText(/hora de baixar/)).toBeNull();
});

test("sem arquivo diz ainda não baixado e o cadastro mostra o motivo", async () => {
  const motivo = "nenhum Cadastro de Instrumentos importado";
  apiComArquivos(undefined, {
    ...STATUS_VELHO,
    cadastro: null,
    cadastro_motivo: motivo,
    cotahist: null,
  });
  render(<ArquivosB3 />);
  const cadastro = await passoDe(/Cadastro de Instrumentos/);
  const cotahist = await passoDe(/COTAHIST anual/);
  expect(await cotahist.findByText(/ainda não baixado/)).toBeTruthy();
  expect(await cadastro.findByText(motivo)).toBeTruthy();
  expect(screen.getAllByText(motivo)).toHaveLength(1); // o motivo não repete fora do passo
  expect(cadastro.queryByText(/em dia/)).toBeNull();
  expect(cotahist.queryByText(/em dia/)).toBeNull();
});

test("cadastro velho mostra o aviso com os dias úteis", async () => {
  apiComArquivos();
  render(<ArquivosB3 />);
  expect(
    await screen.findByText("Cadastro com 6 dias úteis: séries novas podem estar faltando"),
  ).toBeTruthy();
});

test("upload recusado mostra a mensagem do 422", async () => {
  const mensagem = "O arquivo 'extrato.pdf' foi recusado: tipo de arquivo não reconhecido.";
  apiComArquivos((url, init) =>
    url.startsWith("/api/mercado/arquivos?nome=") && init?.method === "POST"
      ? { status: 422, corpo: { erro: "B3FileRejectedError", mensagem } }
      : undefined,
  );
  render(<ArquivosB3 />);
  const campo = await screen.findByLabelText("Escolher arquivo");
  fireEvent.change(campo, {
    target: { files: [new File(["%PDF"], "extrato.pdf", { type: "application/pdf" })] },
  });
  expect(await screen.findByText(mensagem)).toBeTruthy();
});

test("mostra a pasta Downloads vigiada e o que entrou sozinho", async () => {
  apiComArquivos((url) =>
    url === "/api/mercado/arquivos/automatico"
      ? {
          corpo: {
            pasta: "C:\Users\Hugo\Downloads",
            eventos: [
              {
                nome: "InstrumentsConsolidatedFile_20261028_1.csv",
                quando: "2026-10-28T13:00:00+00:00",
                importado: true,
                detalhe: "Cadastro de Instrumentos, pregão de 28/10/2026",
              },
            ],
          },
        }
      : undefined,
  );
  render(<ArquivosB3 />);
  expect(await screen.findByText("C:\Users\Hugo\Downloads")).toBeTruthy();
  expect(screen.getByText(/importado \(Cadastro de Instrumentos, pregão de 28\/10\/2026\)/)).toBeTruthy();
});

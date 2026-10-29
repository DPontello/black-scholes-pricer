import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { simularFetch } from "../testes/fetchFalso";
import { ArquivosB3 } from "./ArquivosB3";

const STATUS_VELHO = {
  fonte: "fim_de_dia",
  cadastro: { data: "2026-10-20", dias_uteis: 6, velho: true },
  cadastro_motivo: null,
  cotahist: { de: "2026-01-02", ate: "2026-10-23" },
};

function apiComArquivos(extra?: (url: string, init?: RequestInit) => ReturnType<Parameters<typeof simularFetch>[0]>) {
  return simularFetch((url, init) => {
    const resposta = extra?.(url, init);
    if (resposta !== undefined) return resposta;
    if (url === "/api/mercado/status") return { corpo: STATUS_VELHO };
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

test("lista os arquivos com tipo e data e os links da B3", async () => {
  apiComArquivos();
  render(<ArquivosB3 />);
  expect(await screen.findByText("COTAHIST_A2026.ZIP")).toBeTruthy();
  expect(screen.getByText("23/10/2026")).toBeTruthy();
  expect(screen.getByRole("link", { name: /COTAHIST/ })).toBeTruthy();
  expect(screen.getByRole("link", { name: /Cadastro de Instrumentos/ })).toBeTruthy();
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

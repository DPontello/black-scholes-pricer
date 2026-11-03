import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { type RascunhoOperacao, rascunhoDaAnalise } from "../api/carteira";
import { analiseCoberta } from "../testes/analise";
import { simularFetch } from "../testes/fetchFalso";
import { FormOperacao } from "./FormOperacao";

const PEDIDO = {
  ativo: "PETR4",
  pernas: [{ ticker: "PETRK541", lado: "venda" as const, quantidade: 100, preco: null }],
  acao: { lado: "compra" as const, quantidade: 100, origem: "compra" as const, preco: null },
  modelo: "venda_coberta",
};

function corpos(fetch: ReturnType<typeof simularFetch>): unknown[] {
  return fetch.mock.calls
    .filter(([u]) => u === "/api/carteira/operacoes")
    .map(([, init]) => JSON.parse(String(init?.body)) as unknown);
}

test("o formulário vindo do montador traz pernas, ação e preços da análise", async () => {
  const fetch = simularFetch(() => ({ status: 201, corpo: { id: "op1" } }));
  const registrada = vi.fn();
  const inicial = rascunhoDaAnalise(PEDIDO, analiseCoberta(), "2026-11-04");
  render(<FormOperacao inicial={inicial} onRegistrada={registrada} onCancelar={vi.fn()} />);
  expect((screen.getByLabelText("Nome da operação") as HTMLInputElement).value).toBe("venda coberta");
  expect((screen.getByLabelText("Preço de PETRK541 (1)") as HTMLInputElement).value).toBe("1,72");
  expect((screen.getByLabelText("Preço de ação PETR4 (1)") as HTMLInputElement).value).toBe("52,52");
  fireEvent.change(screen.getByLabelText("Custos de PETRK541 (1)"), { target: { value: "0,37" } });
  fireEvent.click(screen.getByRole("button", { name: "Registrar" }));
  await waitFor(() => expect(registrada).toHaveBeenCalledWith("op1"));
  expect(corpos(fetch)).toEqual([
    {
      ativo: "PETR4",
      nome: "venda coberta",
      data: "2026-11-04",
      pernas: [
        { ticker: "PETRK541", lado: "venda", execucoes: [{ quantidade: 100, preco: 1.72, custos: 0.37 }] },
      ],
      acao: { lado: "compra", origem: "compra", execucoes: [{ quantidade: 100, preco: 52.52, custos: null }] },
    },
  ]);
});

test("o campo da série cabe o ticker inteiro", () => {
  simularFetch(() => ({ status: 201, corpo: { id: "op1" } }));
  const pedido = {
    ...PEDIDO,
    ativo: "BOVA11",
    pernas: [{ ticker: "BOVAK168W1", lado: "venda" as const, quantidade: 100, preco: null }],
  };
  const inicial = rascunhoDaAnalise(pedido, analiseCoberta(), "2026-11-04");
  render(<FormOperacao inicial={inicial} onRegistrada={vi.fn()} onCancelar={vi.fn()} />);
  const ticker = screen.getByLabelText("Ticker da perna 1") as HTMLInputElement;
  expect(ticker.value).toBe("BOVAK168W1");
  expect(ticker.classList.contains("campo-ticker")).toBe(true);
});

test("ação da carteira vai sem execução e preço faltando não sai do formulário", async () => {
  const fetch = simularFetch(() => ({ status: 201, corpo: { id: "op2" } }));
  const inicial: RascunhoOperacao = {
    ativo: "PETR4",
    nome: "coberta da carteira",
    data: "2026-11-04",
    pernas: [{ ticker: "PETRK541", lado: "venda", execucoes: [{ quantidade: 100, preco: null, custos: null }] }],
    acao: null,
  };
  render(<FormOperacao inicial={inicial} onRegistrada={vi.fn()} onCancelar={vi.fn()} />);
  fireEvent.change(screen.getByLabelText("Ação da operação"), { target: { value: "carteira" } });
  fireEvent.click(screen.getByRole("button", { name: "Registrar" }));
  expect((await screen.findByRole("alert")).textContent).toBe("Preencha o preço de PETRK541.");
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Preço de PETRK541 (1)"), { target: { value: "1,05" } });
  fireEvent.click(screen.getByRole("button", { name: "+ execução" }));
  fireEvent.change(screen.getByLabelText("Preço de PETRK541 (2)"), { target: { value: "1,10" } });
  fireEvent.click(screen.getByRole("button", { name: "Registrar" }));
  await waitFor(() => expect(corpos(fetch).length).toBe(1));
  expect(corpos(fetch)[0]).toMatchObject({
    pernas: [
      {
        execucoes: [
          { quantidade: 100, preco: 1.05, custos: null },
          { quantidade: 100, preco: 1.1, custos: null },
        ],
      },
    ],
    acao: { lado: "compra", origem: "carteira", execucoes: [] },
  });
});

test("o erro de regra da API aparece no formulário", async () => {
  simularFetch(() => ({
    status: 422,
    corpo: { erro: "InvalidDomainValueError", mensagem: "PETR4: 0 ações livres na carteira; a operação cobre 100" },
  }));
  const inicial = rascunhoDaAnalise(PEDIDO, analiseCoberta(), "2026-11-04");
  render(<FormOperacao inicial={inicial} onRegistrada={vi.fn()} onCancelar={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Registrar" }));
  expect((await screen.findByRole("alert")).textContent).toContain("0 ações livres");
});

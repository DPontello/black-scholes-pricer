import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { Cotacao } from "../api/aoVivo";
import { ListaAtivos } from "./ListaAtivos";

function cotacao(parcial: Partial<Cotacao> & { ativo: string }): Cotacao {
  return {
    ultimo: 52.51,
    compra: 52.5,
    venda: 52.52,
    fechamento_anterior: 52.82,
    variacao_pct: -0.0059,
    negocios: 22704,
    volume: 679557741,
    hora: "2026-10-28T13:05:09-03:00",
    fonte: "ao_vivo",
    motivo: null,
    ...parcial,
  };
}

const SEM_ACAO = { selecionado: null, onEscolher: () => {}, onDefinirAtivos: () => {} };

test("variação negativa tem a classe baixa e o texto pt-BR", () => {
  render(<ListaAtivos cotacoes={[cotacao({ ativo: "PETR4" })]} {...SEM_ACAO} />);
  const variacao = screen.getByText("-0,59%");
  expect(variacao.className).toContain("baixa");
  expect(screen.getByText("52,51")).toBeTruthy();
  expect(screen.getByText("679,6 mi")).toBeTruthy();
  expect(screen.getByText("22.704")).toBeTruthy();
});

test("linha com motivo mostra o motivo no lugar dos números", () => {
  const sem = cotacao({
    ativo: "PETR44",
    ultimo: null,
    compra: null,
    venda: null,
    variacao_pct: null,
    negocios: null,
    volume: null,
    hora: null,
    fonte: null,
    motivo: "ativo desconhecido",
  });
  render(<ListaAtivos cotacoes={[sem]} {...SEM_ACAO} />);
  expect(screen.getByText("ativo desconhecido")).toBeTruthy();
  expect(screen.queryByText("—")).toBeNull();
});

test("adicionar e remover gravam a lista nova; clique escolhe o ativo da cadeia", () => {
  const definir = vi.fn();
  const escolher = vi.fn();
  render(
    <ListaAtivos
      cotacoes={[cotacao({ ativo: "PETR4" }), cotacao({ ativo: "VALE3" })]}
      selecionado={null}
      onEscolher={escolher}
      onDefinirAtivos={definir}
    />,
  );
  fireEvent.change(screen.getByLabelText("Adicionar ativo"), { target: { value: " bova11 " } });
  fireEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  expect(definir).toHaveBeenLastCalledWith(["PETR4", "VALE3", "BOVA11"]);
  fireEvent.click(screen.getByRole("button", { name: "Remover PETR4" }));
  expect(definir).toHaveBeenLastCalledWith(["VALE3"]);
  fireEvent.click(screen.getByRole("button", { name: "VALE3" }));
  expect(escolher).toHaveBeenCalledWith("VALE3");
});

test("dado que não é ao vivo diz a fonte ao lado da hora", () => {
  render(
    <ListaAtivos
      cotacoes={[cotacao({ ativo: "PETR4", fonte: "fim_de_dia", hora: "2026-10-23T18:00:00-03:00" })]}
      {...SEM_ACAO}
    />,
  );
  expect(screen.getByText("(fim de dia)")).toBeTruthy();
});

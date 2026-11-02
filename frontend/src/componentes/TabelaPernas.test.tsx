import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { PedidoAnalise } from "../api/montador";
import { analiseCoberta } from "../testes/analise";
import { TabelaPernas } from "./TabelaPernas";

const PEDIDO: PedidoAnalise = {
  ativo: "PETR4",
  pernas: [{ ticker: "PETRK541", lado: "venda", quantidade: 100, preco: null }],
  acao: { lado: "compra", quantidade: 100, origem: "compra", preco: null },
  modelo: "venda_coberta",
};

test("sem perna nenhuma, explica como começar", () => {
  render(
    <TabelaPernas pedido={{ ...PEDIDO, pernas: [], acao: null }} analise={null} onMudar={vi.fn()} />,
  );
  expect(screen.getByText(/Escolha um modelo pronto/)).toBeTruthy();
});

test("o preço automático aparece no campo vazio, com a origem", () => {
  render(<TabelaPernas pedido={PEDIDO} analise={analiseCoberta()} onMudar={vi.fn()} />);
  const campo = screen.getByLabelText("Preço de PETRK541") as HTMLInputElement;
  expect(campo.placeholder).toBe("1,72");
  expect(screen.getAllByText("book").length).toBe(2);
  expect(screen.getByText(/call 52,91 · americana/)).toBeTruthy();
});

test("preço digitado com vírgula vira número e o campo guarda o texto", () => {
  const mudar = vi.fn();
  render(<TabelaPernas pedido={PEDIDO} analise={null} onMudar={mudar} />);
  const campo = screen.getByLabelText("Preço de PETRK541") as HTMLInputElement;
  fireEvent.change(campo, { target: { value: "1," } });
  expect(campo.value).toBe("1,");
  fireEvent.change(campo, { target: { value: "1,05" } });
  expect(mudar).toHaveBeenLastCalledWith({
    ...PEDIDO,
    pernas: [{ ticker: "PETRK541", lado: "venda", quantidade: 100, preco: 1.05 }],
  });
});

test("lado, origem da ação, tirar perna e quantidade fora do lote", () => {
  const mudar = vi.fn();
  const analise = analiseCoberta();
  const { rerender } = render(<TabelaPernas pedido={PEDIDO} analise={analise} onMudar={mudar} />);
  fireEvent.change(screen.getByLabelText("Lado de PETRK541"), { target: { value: "compra" } });
  expect(mudar.mock.lastCall?.[0].pernas[0].lado).toBe("compra");
  fireEvent.change(screen.getByLabelText("De onde vem a ação"), { target: { value: "carteira" } });
  expect(mudar.mock.lastCall?.[0].acao.origem).toBe("carteira");
  fireEvent.click(screen.getByLabelText("Tirar PETRK541"));
  expect(mudar.mock.lastCall?.[0].pernas).toEqual([]);
  const fora = { ...PEDIDO, pernas: [{ ...PEDIDO.pernas[0]!, quantidade: 150 }] };
  rerender(<TabelaPernas pedido={fora} analise={analise} onMudar={mudar} />);
  expect(screen.getByLabelText("Quantidade de PETRK541").className).toBe("fora-do-lote");
});

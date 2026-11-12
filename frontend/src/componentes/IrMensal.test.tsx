import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import type { MesIr } from "../api/carteira";
import { mesIr, mesIrOutubro } from "../testes/carteira";
import { simularFetch } from "../testes/fetchFalso";
import { IrMensal } from "./IrMensal";

function api(meses: MesIr[]) {
  return simularFetch((url) => (url === "/api/carteira/ir-mensal" ? { corpo: meses } : undefined));
}

function montar() {
  return render(
    <MemoryRouter>
      <IrMensal />
    </MemoryRouter>,
  );
}

// A linha do mês na tabela de cima: a que tem o botão que abre o mês.
async function linhaDo(rotulo: string): Promise<HTMLElement> {
  const botao = await screen.findByRole("button", { name: new RegExp(rotulo) });
  return botao.closest("tr") as HTMLElement;
}

// O texto que se vê: o espaço que não quebra entre "R$" e o valor conta como espaço.
function texto(celula: HTMLElement): string {
  return (celula.textContent ?? "").replace(/ /g, " ");
}

test("mostra o rótulo de estimativa e um mês por linha, o mais recente primeiro", async () => {
  api([mesIr(), mesIrOutubro()]);
  montar();
  expect(
    await screen.findByText("Estimativa, só opções, sem IR retido na fonte e sem prejuízo de antes do app."),
  ).toBeTruthy();
  expect(screen.getByRole("link", { name: "O que é IR mensal?" }).getAttribute("href")).toBe(
    "/aprender/termos#ir-mensal",
  );
  const cabecalho = screen.getAllByRole("columnheader").map((c) => c.textContent);
  expect(cabecalho).toEqual([
    "Mês",
    "Comum",
    "Day trade",
    "Prejuízo a compensar",
    "Base",
    "IR do mês",
    "A pagar",
  ]);
  const linhas = screen.getAllByRole("row");
  expect(linhas).toHaveLength(3);
  expect(linhas[1]?.textContent).toContain("nov/2026");
  expect(linhas[2]?.textContent).toContain("out/2026");
});

test("a pagar mostra o valor e o prazo", async () => {
  api([mesIr()]);
  montar();
  const linha = await linhaDo("nov/2026");
  expect(within(linha).getByText("R$ 18,35 até 30/12/2026")).toBeTruthy();
});

test("a pagar sem prazo mostra só o valor", async () => {
  api([mesIr({ pagar_ate: null })]);
  montar();
  const linha = await linhaDo("nov/2026");
  expect(within(linha).getByText("R$ 18,35")).toBeTruthy();
});

test("abaixo de R$ 10 diz que soma com o IR dos próximos meses", async () => {
  api([mesIrOutubro()]);
  montar();
  const linha = await linhaDo("out/2026");
  expect(within(linha).getByText("abaixo de R$ 10: soma com o IR dos próximos meses")).toBeTruthy();
});

test("sem IR a pagar nem a somar, a pagar fica em traço", async () => {
  api([mesIr({ ir_do_mes: 0, ir_de_antes: 0, ir_a_pagar: 0, ir_para_depois: 0, pagar_ate: null })]);
  montar();
  const celulas = within(await linhaDo("nov/2026")).getAllByRole("cell");
  expect(celulas.at(-1)?.textContent).toBe("—");
});

test("o prejuízo a compensar lista só o que não é zero, ou traço", async () => {
  api([mesIrOutubro(), mesIr()]);
  montar();
  const outubro = within(await linhaDo("out/2026")).getAllByRole("cell")[3] as HTMLElement;
  expect(texto(outubro)).toBe("comum R$ 52,00");
  const novembro = within(await linhaDo("nov/2026")).getAllByRole("cell")[3] as HTMLElement;
  expect(texto(novembro)).toBe("—");
});

test("o prejuízo a compensar mostra os dois tipos quando os dois existem", async () => {
  api([mesIrOutubro({ prejuizo_day_trade: 10 })]);
  montar();
  const celula = within(await linhaDo("out/2026")).getAllByRole("cell")[3] as HTMLElement;
  expect(texto(celula)).toContain("comum R$ 52,00");
  expect(texto(celula)).toContain("day trade R$ 10,00");
});

test("a base do mês lista só o que não é zero, ou traço", async () => {
  api([mesIrOutubro(), mesIr(), mesIr({ mes: "2026-09", base_comum: 0, base_day_trade: 0 })]);
  montar();
  const outubro = within(await linhaDo("out/2026")).getAllByRole("cell")[4] as HTMLElement;
  expect(texto(outubro)).toBe("day trade R$ 28,00");
  const novembro = within(await linhaDo("nov/2026")).getAllByRole("cell")[4] as HTMLElement;
  expect(texto(novembro)).toBe("comum R$ 85,00");
  const setembro = within(await linhaDo("set/2026")).getAllByRole("cell")[4] as HTMLElement;
  expect(texto(setembro)).toBe("—");
});

test("a base do mês mostra os dois tipos quando os dois existem", async () => {
  api([mesIr({ base_day_trade: 10 })]);
  montar();
  const celula = within(await linhaDo("nov/2026")).getAllByRole("cell")[4] as HTMLElement;
  expect(texto(celula)).toContain("comum R$ 85,00");
  expect(texto(celula)).toContain("day trade R$ 10,00");
});

test("o mês com exercício ou atribuição leva a marca ao lado do botão", async () => {
  api([mesIr(), mesIrOutubro()]);
  montar();
  const novembro = await linhaDo("nov/2026");
  expect(within(novembro).getByText("com exercício ou atribuição").className).toBe("secundario");
  const outubro = await linhaDo("out/2026");
  expect(within(outubro).queryByText("com exercício ou atribuição")).toBeNull();
});

test("abrir o mês mostra a base, as peças e a nota de exercício", async () => {
  api([mesIr()]);
  montar();
  const botao = await screen.findByRole("button", { name: /nov\/2026/ });
  expect(botao.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText(/^Base:/)).toBeNull();

  fireEvent.click(botao);
  expect(botao.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getByText("Base: comum R$ 85,00 (15%) · day trade R$ 0,00 (20%)")).toBeTruthy();
  expect(
    screen.getByText("IR do mês R$ 12,75 + R$ 5,60 de meses anteriores = R$ 18,35"),
  ).toBeTruthy();

  const pecas = screen.getAllByRole("table")[1] as HTMLElement;
  expect(within(pecas).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
    "Data",
    "Série",
    "Operação",
    "Tipo",
    "Categoria",
    "Resultado",
  ]);
  const linhas = within(pecas).getAllByRole("row");
  expect(linhas).toHaveLength(3);
  expect(linhas[1]?.textContent).toBe("12/11/2026PETRW280venda de putEncerramentoComum58,00");
  expect(linhas[2]?.textContent).toBe("19/11/2026PETRW280venda de putPóComum79,00");

  expect(
    screen.getByText(
      "Exercício ou atribuição de PETRK320 (call exercida) em 19/11/2026: o prêmio vai para o preço da ação, e o resultado da ação fica fora desta conta (o app não apura o IR de ações).",
    ),
  ).toBeTruthy();

  fireEvent.click(botao);
  expect(botao.getAttribute("aria-expanded")).toBe("false");
  expect(screen.queryByText(/^Base:/)).toBeNull();
});

test("a soma do mês abaixo de R$ 10 mostra o acumulado e avisa que soma com os próximos meses", async () => {
  api([mesIr({ ir_do_mes: 3, ir_de_antes: 5.6, ir_a_pagar: 0, ir_para_depois: 8.6, pagar_ate: null })]);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /nov\/2026/ }));
  expect(
    screen.getByText(
      "IR do mês R$ 3,00 + R$ 5,60 de meses anteriores = R$ 8,60 (abaixo de R$ 10: soma com o IR dos próximos meses)",
    ),
  ).toBeTruthy();
});

test("sem IR de meses anteriores, a linha da soma não aparece", async () => {
  api([mesIrOutubro()]);
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /out\/2026/ }));
  expect(screen.getByText("Base: comum R$ 0,00 (15%) · day trade R$ 28,00 (20%)")).toBeTruthy();
  expect(screen.queryByText(/de meses anteriores/)).toBeNull();
  const pecas = screen.getAllByRole("table")[1] as HTMLElement;
  expect(within(pecas).getAllByRole("row")[1]?.textContent).toBe(
    "01/10/2026PETRK300call de outubroEncerramentoDay trade28,00",
  );
  expect(screen.queryByText(/Exercício ou atribuição/)).toBeNull();
});

test("sem meses mostra o vazio", async () => {
  api([]);
  montar();
  expect(await screen.findByText("Nenhuma opção encerrada ou virada pó neste perfil ainda.")).toBeTruthy();
  expect(screen.queryByRole("table")).toBeNull();
});

test("erro da API aparece", async () => {
  simularFetch(() => ({ status: 404, corpo: { erro: "NoProfileOpen", mensagem: "Nenhum perfil aberto." } }));
  montar();
  expect((await screen.findByRole("alert")).textContent).toBe("Nenhum perfil aberto.");
});

test("falha sem corpo da API mostra a mensagem padrão", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("falhou")));
  montar();
  expect((await screen.findByRole("alert")).textContent).toBe("Não foi possível calcular o IR mensal.");
});

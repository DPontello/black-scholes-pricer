import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import type { Analise } from "../api/montador";
import { analiseCoberta } from "../testes/analise";
import { rolagem } from "../testes/alertas";
import { FaixaRolagem } from "./FaixaRolagem";

function montar(dados = rolagem(), analise: Analise | null = null, fechar = vi.fn()) {
  render(
    <MemoryRouter>
      <FaixaRolagem rolagem={dados} analise={analise} onFechar={fechar} />
    </MemoryRouter>,
  );
  return screen.getByRole("complementary", { name: "Rolagem" }).textContent ?? "";
}

test("com o pedido: o custo de zerar, a estrutura nova e o caixa líquido", () => {
  const base = analiseCoberta();
  const analise = { ...base, no_vencimento: { ...(base.no_vencimento as NonNullable<Analise["no_vencimento"]>), caixa: 60 } };
  const texto = montar(rolagem(), analise);
  expect(texto).toContain("Rolagem de put coberta");
  expect(texto).toContain("Zerar as pernas atuais (vencimento 19/11/2026) paga R$\u00a035,00 pelo preço de zerar.");
  expect(texto).toContain("Abaixo, a mesma estrutura em 17/12/2026.");
  expect(texto).toContain("Caixa líquido da rolagem: recebe R$\u00a025,00.");
});

test("sem modelo: pede para montar pela cadeia, sem caixa líquido", () => {
  const texto = montar(rolagem({ pedido: null }));
  expect(texto).toContain("monte a estrutura nova pela cadeia, em 17/12/2026");
  expect(texto).not.toContain("Caixa líquido");
});

test("sem vencimento seguinte e sem preço de zerar", () => {
  const texto = montar(rolagem({ vencimento_novo: null, pedido: null, caixa_de_zerar: null }));
  expect(texto).toContain("sem preço de zerar agora");
  expect(texto).toContain("A cadeia não tem vencimento depois de 19/11/2026.");
});

test("fechar a faixa e o '?' da rolagem", () => {
  const fechar = vi.fn();
  montar(rolagem(), null, fechar);
  expect(screen.getByRole("link", { name: "O que é Rolagem?" })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Fechar a faixa" }));
  expect(fechar).toHaveBeenCalled();
});

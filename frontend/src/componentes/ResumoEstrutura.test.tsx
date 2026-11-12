import { render as renderBase, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import { analiseCoberta } from "../testes/analise";
import { AvisosEstrutura, DetalhesEstrutura, frase, ResumoEstrutura } from "./ResumoEstrutura";

// Os "?" dos rótulos são links: o componente precisa de um roteador em volta.
function render(ui: ReactElement) {
  return renderBase(ui, { wrapper: MemoryRouter });
}

test("a venda coberta em português simples", () => {
  expect(frase(analiseCoberta())).toBe(
    "Você paga R$ 5.080,00 agora; no pior caso perde R$ 5.080,00; ganha no máximo R$ 211,00; " +
      "empata se PETR4 terminar em 50,80 no vencimento.",
  );
});

test("perda ilimitada diz ilimitada, crédito diz recebe, e sem preço o resumo avisa", () => {
  const base = analiseCoberta().no_vencimento!;
  const seca = analiseCoberta({
    no_vencimento: { ...base, caixa: 172, ganho_max: 172, perda_max: null, breakevens: [54.63] },
  });
  expect(frase(seca)).toContain("no pior caso a perda é ilimitada");
  expect(frase(seca)).toContain("Você recebe R$ 172,00 agora");
  expect(frase(analiseCoberta({ no_vencimento: null }))).toMatch(/Falta o preço/);
});

// O número ao lado do rótulo, sem o "?".
function numero(rotulo: string): string {
  return screen.getByText(rotulo).closest(".numero")?.querySelector("strong")?.textContent ?? "";
}

test("ganho e perda máximos são os brutos, como na corretora; só os três números, sem custos nem IR", () => {
  render(<ResumoEstrutura analise={analiseCoberta()} />);
  expect(numero("Ganho máximo")).toBe("R$ 211,00");
  expect(numero("Perda máxima")).toBe("R$ -5.080,00");
  expect(numero("Chance de lucro")).toBe("68,0%");
  expect(screen.queryByText("Custos de montagem")).toBeNull();
  expect(screen.queryByText(/IR/)).toBeNull();
});

test("os detalhes trazem custos, dias úteis, gregas e a grade, só com hoje", () => {
  const { rerender } = render(<DetalhesEstrutura analise={analiseCoberta()} />);
  expect(numero("Custos de montagem")).toBe("R$ 1,81");
  expect(numero("Dias úteis")).toBe("15");
  expect(screen.getByText("Delta")).toBeTruthy();
  expect(screen.getByText("Theta por dia útil")).toBeTruthy();
  expect(
    screen.getByText("Resultado hoje se o preço e a volatilidade mudarem agora"),
  ).toBeTruthy();
  rerender(
    <DetalhesEstrutura analise={analiseCoberta({ hoje: null, hoje_indisponivel: "put americana" })} />,
  );
  expect(numero("Custos de montagem")).toBe("R$ 1,81");
  expect(screen.queryByText("Theta por dia útil")).toBeNull();
  expect(screen.queryByText(/Resultado hoje se/)).toBeNull();
});

test("os avisos e, sem hoje, o motivo; sem nenhum dos dois, nada é desenhado", () => {
  const { container, rerender } = render(<AvisosEstrutura analise={analiseCoberta()} />);
  expect(screen.getByText(/ADR-0002/)).toBeTruthy();
  rerender(
    <AvisosEstrutura analise={analiseCoberta({ hoje: null, hoje_indisponivel: "put americana" })} />,
  );
  expect(screen.getByText("Sem avaliação de hoje: put americana.")).toBeTruthy();
  rerender(<AvisosEstrutura analise={analiseCoberta({ avisos: [] })} />);
  expect(container.innerHTML).toBe("");
});

test("melhor caso negativo diz que ainda perde, e zero diz que empata", () => {
  // Iron condor vendido em semanais pouco líquidas: pelo bid e pelo ask, sai com débito.
  const base = analiseCoberta().no_vencimento!;
  const debito = analiseCoberta({
    no_vencimento: { ...base, caixa: -6, ganho_max: -6, perda_max: -106, breakevens: [] },
  });
  expect(frase(debito)).toBe(
    "Você paga R$ 6,00 agora; no pior caso perde R$ 106,00; no melhor caso ainda perde R$ 6,00.",
  );
  const zero = analiseCoberta({ no_vencimento: { ...base, ganho_max: 0, breakevens: [] } });
  expect(frase(zero)).toContain("no melhor caso empata");
});

// Os destinos dos "?" na ordem em que aparecem.
function destinos(): (string | undefined)[] {
  return screen
    .getAllByRole("link", { name: /^O que é/ })
    .map((link) => link.getAttribute("href")?.replace("/aprender/termos#", ""));
}

test("os rótulos com termo no glossário ganham um '?', sem repetir o mesmo termo lado a lado", () => {
  const { unmount } = render(<ResumoEstrutura analise={analiseCoberta()} />);
  expect(destinos()).toEqual(["ganho-perda-maximos", "chance-de-lucro"]);
  unmount();
  render(<DetalhesEstrutura analise={analiseCoberta()} />);
  expect(destinos()).toEqual(["custos-ir", "delta", "gamma", "theta", "vega"]);
});

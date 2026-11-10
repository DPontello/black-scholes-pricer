import { fireEvent, render as renderBase, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import { analiseCoberta } from "../testes/analise";
import { CartaoResultado } from "./CartaoResultado";

// Os "?" dos rótulos são links: o componente precisa de um roteador em volta.
function render(ui: ReactElement) {
  return renderBase(ui, { wrapper: MemoryRouter });
}

// O número ao lado do rótulo, sem o "?".
function numero(rotulo: string): string {
  return screen.getByText(rotulo).closest(".numero")?.querySelector("strong")?.textContent ?? "";
}

test("abre com a frase, os três números e o gráfico, e os detalhes fechados", () => {
  render(<CartaoResultado analise={analiseCoberta()} />);
  expect(screen.getByRole("heading", { level: 2 }).textContent).toBe(
    "venda coberta vence 19/11/2026 · preços fim de dia (B3)",
  );
  expect(screen.getByText(/Você paga R\$ 5\.080,00 agora/)).toBeTruthy();
  expect(numero("Ganho máximo")).toBe("R$ 211,00");
  expect(numero("Perda máxima")).toBe("R$ -5.080,00");
  expect(numero("Chance de lucro")).toBe("68,0%");
  expect(screen.getByRole("img", { name: /Resultado de/ })).toBeTruthy();
  expect(screen.queryByText("Theta por dia útil")).toBeNull();
  expect(screen.queryByText("Custos de montagem")).toBeNull();
  const botao = screen.getByRole("button", { name: "▸ ver detalhes" });
  expect(botao.getAttribute("aria-expanded")).toBe("false");
});

test("ver detalhes abre custos, dias úteis, gregas e a grade, e a escolha fica guardada", () => {
  const { unmount } = render(<CartaoResultado analise={analiseCoberta()} />);
  fireEvent.click(screen.getByRole("button", { name: "▸ ver detalhes" }));
  expect(numero("Custos de montagem")).toBe("R$ 1,81");
  expect(numero("Dias úteis")).toBe("15");
  expect(screen.getByText("Theta por dia útil")).toBeTruthy();
  expect(
    screen.getByText("Resultado hoje se o preço e a volatilidade mudarem agora"),
  ).toBeTruthy();
  const aberto = screen.getByRole("button", { name: "▾ esconder detalhes" });
  expect(aberto.getAttribute("aria-expanded")).toBe("true");

  unmount();
  render(<CartaoResultado analise={analiseCoberta()} />);
  expect(screen.getByRole("button", { name: "▾ esconder detalhes" })).toBeTruthy();
  expect(screen.getByText("Custos de montagem")).toBeTruthy();
});

test("avisos e 'Sem avaliação de hoje' aparecem com os detalhes fechados", () => {
  const { rerender } = render(<CartaoResultado analise={analiseCoberta()} />);
  expect(screen.getByText(/ADR-0002/)).toBeTruthy();
  rerender(
    <CartaoResultado
      analise={analiseCoberta({ hoje: null, hoje_indisponivel: "put americana" })}
    />,
  );
  expect(screen.getByText("Sem avaliação de hoje: put americana.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "▸ ver detalhes" })).toBeTruthy();
});

test("sem o preço de alguma perna, a frase avisa e os números grandes somem", () => {
  render(<CartaoResultado analise={analiseCoberta({ no_vencimento: null })} />);
  expect(screen.getByText(/Falta o preço/)).toBeTruthy();
  expect(screen.queryByText("Ganho máximo")).toBeNull();
});

test("ganho ilimitado aparece como ilimitado", () => {
  const base = analiseCoberta().no_vencimento!;
  render(
    <CartaoResultado analise={analiseCoberta({ no_vencimento: { ...base, ganho_max: null } })} />,
  );
  expect(numero("Ganho máximo")).toBe("ilimitado");
});

test("a ordem é título, frase, números, gráfico, avisos e ver detalhes", () => {
  render(<CartaoResultado analise={analiseCoberta()} />);
  const ordem = [
    screen.getByRole("heading", { level: 2 }),
    screen.getByText(/Você paga/),
    screen.getByText("Ganho máximo"),
    screen.getByRole("img", { name: /Resultado de/ }),
    screen.getByText(/ADR-0002/),
    screen.getByRole("button", { name: "▸ ver detalhes" }),
  ];
  for (let i = 0; i < ordem.length - 1; i++)
    expect(
      ordem[i]!.compareDocumentPosition(ordem[i + 1]!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
});

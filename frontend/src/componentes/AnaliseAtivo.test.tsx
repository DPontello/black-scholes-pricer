import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { AnaliseMercado } from "../api/analise";
import { analiseMercado } from "../testes/analiseMercado";
import { simularFetch } from "../testes/fetchFalso";
import { AnaliseAtivo } from "./AnaliseAtivo";

function api(analise: AnaliseMercado = analiseMercado()) {
  return simularFetch((url) => (url === "/api/mercado/analise/PETR4" ? { corpo: analise } : undefined));
}

function cartao(rotulo: string): string | null | undefined {
  return screen.getByText(rotulo).parentElement?.querySelector("strong")?.textContent;
}

test("os cartões mostram a IV de hoje, a HV, o rank, o percentil e o regime", async () => {
  api();
  render(<AnaliseAtivo ativo="PETR4" />);
  await screen.findByText("IV 30 hoje");
  expect(cartao("IV 30 hoje")).toBe("30,0%");
  expect(cartao("HV 21")).toBe("40,0%");
  expect(cartao("IV rank")).toBe("12,0%");
  expect(cartao("Percentil")).toBe("8,0%");
  expect(cartao("Regime de vol")).toBe("baixa");
  expect(screen.getByText(/constante em todo o histórico/)).toBeTruthy();
  expect(screen.getByText(/fim de dia \(B3\)/)).toBeTruthy();
});

test("sem rank, os cartões dizem histórico curto e o regime vem pela HV", async () => {
  const base = analiseMercado();
  api(
    analiseMercado({
      hoje: { ...base.hoje!, iv_rank: null, iv_percentil: null, regime_pela_hv: true },
    }),
  );
  render(<AnaliseAtivo ativo="PETR4" />);
  await screen.findByText("IV 30 hoje");
  expect(cartao("IV rank")).toBe("histórico curto");
  expect(cartao("Percentil")).toBe("histórico curto");
  expect(cartao("Regime de vol")).toBe("baixa (pela HV)");
});

test("o smile troca com o vencimento escolhido", async () => {
  api();
  render(<AnaliseAtivo ativo="PETR4" />);
  const smile = await screen.findByRole("img", { name: /Smile do vencimento 19\/11\/2026/ });
  expect(smile).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "18/12/2026 (38 du)" }));
  expect(await screen.findByRole("img", { name: /Smile do vencimento 18\/12\/2026/ })).toBeTruthy();
});

test("sem histórico e sem IV de hoje, os motivos aparecem e o resto segue", async () => {
  api(
    analiseMercado({
      historico: [],
      historico_motivo: "sem COTAHIST na biblioteca",
      hoje: null,
      hoje_motivo: "PETR4: sem IV 30 hoje (nenhum vencimento com smile no spot)",
    }),
  );
  render(<AnaliseAtivo ativo="PETR4" />);
  expect(await screen.findByText("sem COTAHIST na biblioteca")).toBeTruthy();
  expect(screen.getByText(/sem IV 30 hoje/)).toBeTruthy();
  expect(screen.getByRole("img", { name: /Estrutura a termo/ })).toBeTruthy();
});

test("erro da API aparece no lugar da análise", async () => {
  simularFetch(() => ({
    status: 422,
    corpo: { erro: "UnderlyingUnavailableError", mensagem: "PETR4: aguardando dados" },
  }));
  render(<AnaliseAtivo ativo="PETR4" />);
  expect((await screen.findByRole("alert")).textContent).toBe("PETR4: aguardando dados");
});

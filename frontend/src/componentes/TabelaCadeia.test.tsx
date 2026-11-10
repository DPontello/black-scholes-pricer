import { render as renderBase, fireEvent, screen, within } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import type { Cadeia, Serie } from "../api/aoVivo";
import { TabelaCadeia } from "./TabelaCadeia";

// Os "?" dos rótulos são links: o componente precisa de um roteador em volta.
function render(ui: ReactElement) {
  return renderBase(ui, { wrapper: MemoryRouter });
}

function serie(parcial: Partial<Serie> & { ticker: string; strike: number }): Serie {
  return {
    tipo: "call",
    estilo: "american",
    compra: 1.2,
    venda: 1.25,
    ultimo: 1.22,
    negocios: 40,
    volume: 4840,
    iv: 0.312,
    delta: 0.55,
    lote: 100,
    ...parcial,
  };
}

const nada = () => {};

// A cadeia do Montador: só um vencimento, que vem de fora, e as colunas essenciais.
function enxuta(vencimento: string) {
  return (
    <TabelaCadeia
      ativo="PETR4"
      cadeia={CADEIA}
      indisponivel={null}
      enxuta
      vencimento={vencimento}
      onEscolherSerie={nada}
    />
  );
}

function celulasDa(strike: string): (string | null)[] {
  const linha = screen.getByText(strike).closest("tr") as HTMLElement;
  return within(linha).getAllByRole("cell").map((c) => c.textContent);
}

const CADEIA: Cadeia = {
  ativo: "PETR4",
  spot: 52.51,
  fonte: "ao_vivo",
  hora: "2026-10-28T13:05:09-03:00",
  vencimentos: [
    {
      data: "2026-11-19",
      dias_uteis: 16,
      series: [
        serie({ ticker: "PETRK520", strike: 52, compra: null }),
        serie({ ticker: "PETRW520", strike: 52, tipo: "put", delta: -0.45 }),
        serie({ ticker: "PETRK540", strike: 54 }),
        serie({ ticker: "PETRK500", strike: 50 }),
      ],
    },
    { data: "2026-12-17", dias_uteis: 35, series: [serie({ ticker: "PETRL520", strike: 52 })] },
  ],
  disponiveis: [
    { data: "2026-11-06", dias_uteis: 7, semanal: true },
    { data: "2026-11-19", dias_uteis: 16, semanal: false },
    { data: "2026-12-17", dias_uteis: 35, semanal: false },
  ],
  rejeitadas: [{ ticker: "PETRK999", motivo: "sem estilo de exercício no cadastro" }],
};

test("lado ausente é — e a linha do strike mais perto do spot fica destacada", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const linha = screen.getByText("52,00").closest("tr");
  expect(linha?.className).toContain("no-dinheiro");
  expect(within(linha as HTMLElement).getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.getByText("54,00").closest("tr")?.className ?? "").not.toContain("no-dinheiro");
});

test("calls e puts espelhadas no mesmo strike, com IV e delta formatados", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const linha = screen.getByText("52,00").closest("tr") as HTMLElement;
  const celulas = within(linha).getAllByRole("cell").map((c) => c.textContent);
  expect(celulas[6]).toBe("52,00"); // o strike no meio
  expect(celulas[4]).toBe("0,55"); // delta da call
  expect(celulas[8]).toBe("-0,45"); // delta da put, espelhado
  expect(celulas).toContain("31,2%");
});

test("abas por vencimento com os dias úteis", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByRole("tab", { name: "19/11 (16 du)" })).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "17/12 (35 du)" }));
  expect(screen.queryByText("54,00")).toBeNull();
});

test("séries rejeitadas ficam num bloco recolhível com o motivo", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByText("1 série(s) fora da cadeia")).toBeTruthy();
  expect(screen.getByText("PETRK999: sem estilo de exercício no cadastro")).toBeTruthy();
});

test("cadeia indisponível mostra o motivo, e sem ativo pede para escolher", () => {
  const { rerender } = render(
    <TabelaCadeia
      ativo="VALE3"
      cadeia={null}
      indisponivel={{
        ativo: "VALE3",
        erro: "UnderlyingUnavailableError",
        mensagem: "VALE3: aguardando dados do Tryd",
      }}
      onVencimentos={nada}
    />,
  );
  expect(screen.getByText(/aguardando dados do Tryd/)).toBeTruthy();
  rerender(<TabelaCadeia ativo={null} cadeia={null} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByText(/Escolha um ativo/)).toBeTruthy();
});

test("vencimentos para escolher, com a semanal marcada e os escolhidos pressionados", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const grupo = within(screen.getByRole("group", { name: "Vencimentos" }));
  expect(grupo.getByRole("button", { name: "06/11 S" }).getAttribute("aria-pressed")).toBe("false");
  expect(grupo.getByRole("button", { name: "19/11" }).getAttribute("aria-pressed")).toBe("true");
});

test("marcar ou desmarcar um vencimento pede a nova escolha, nunca vazia", () => {
  const escolha = vi.fn();
  const { rerender } = render(
    <TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={escolha} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "06/11 S" }));
  expect(escolha).toHaveBeenLastCalledWith(["2026-11-06", "2026-11-19", "2026-12-17"]);
  fireEvent.click(screen.getByRole("button", { name: "19/11" }));
  expect(escolha).toHaveBeenLastCalledWith(["2026-12-17"]);

  const soNovembro = { ...CADEIA, vencimentos: CADEIA.vencimentos.slice(0, 1) };
  rerender(
    <TabelaCadeia ativo="PETR4" cadeia={soNovembro} indisponivel={null} onVencimentos={escolha} />,
  );
  escolha.mockClear();
  fireEvent.click(screen.getByRole("button", { name: "19/11" }));
  expect(escolha).not.toHaveBeenCalled();
});

test("vencimento escolhido que ainda não tem série avisa no lugar da tabela", () => {
  const vazia = { ...CADEIA, vencimentos: [{ data: "2026-11-06", dias_uteis: 7, series: [] }] };
  render(<TabelaCadeia ativo="PETR4" cadeia={vazia} indisponivel={null} onVencimentos={nada} />);
  expect(screen.getByText("Nenhuma série deste vencimento chegou ainda.")).toBeTruthy();
});

test("com onEscolherSerie, cada lado ganha o + que põe a série no montador", () => {
  const escolher = vi.fn();
  render(
    <TabelaCadeia
      ativo="PETR4"
      cadeia={CADEIA}
      indisponivel={null}
      onVencimentos={nada}
      onEscolherSerie={escolher}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Pôr PETRW520 no montador" }));
  expect(escolher).toHaveBeenCalledWith(expect.objectContaining({ ticker: "PETRW520" }));
});

test("sem onEscolherSerie, a cadeia não tem os botões de +", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  expect(screen.queryByRole("button", { name: /no montador/ })).toBeNull();
});

test("IV e Delta têm um '?' cada, só no lado das calls, para não repetir", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  const ajudas = screen.getAllByRole("link", { name: /^O que é/ });
  expect(ajudas.map((link) => [link.getAttribute("aria-label"), link.getAttribute("href")])).toEqual([
    ["O que é IV (vol implícita)?", "/aprender/termos#iv"],
    ["O que é Delta?", "/aprender/termos#delta"],
  ]);
  const cabecalhos = screen.getAllByRole("columnheader").map((c) => c.textContent);
  expect(cabecalhos.filter((c) => c === "IV ?")).toHaveLength(1);
  expect(cabecalhos.filter((c) => c === "IV")).toHaveLength(1);
});

test("enxuta: 7 colunas, sem a fileira de vencimentos nem as abas", () => {
  render(enxuta("2026-11-19"));
  expect(celulasDa("52,00")).toEqual(["+", "—", "1,25", "52,00", "1,25", "1,20", "+"]);
  expect(screen.queryByRole("group", { name: "Vencimentos" })).toBeNull();
  expect(screen.queryAllByRole("tab")).toHaveLength(0);
});

test("enxuta mostra o vencimento que vem de fora", () => {
  render(enxuta("2026-12-17"));
  expect(screen.getByText("52,00")).toBeTruthy();
  expect(screen.queryByText("54,00")).toBeNull();
});

test("enxuta com um vencimento que ainda não chegou avisa no lugar da tabela", () => {
  render(enxuta("2026-11-06"));
  expect(screen.getByText("Carregando o vencimento 06/11…")).toBeTruthy();
  expect(screen.queryByRole("table")).toBeNull();
});

test("mostrar IV, delta e negócios abre as 4 colunas de cada lado, e a escolha fica guardada", () => {
  const { unmount } = render(enxuta("2026-11-19"));
  expect(screen.queryAllByRole("link", { name: /^O que é/ })).toHaveLength(0);
  const botao = screen.getByRole("button", { name: "mostrar IV, delta e negócios" });
  expect(botao.getAttribute("aria-expanded")).toBe("false");

  fireEvent.click(botao);
  expect(celulasDa("52,00")).toHaveLength(15);
  const aberto = screen.getByRole("button", { name: "esconder IV, delta e negócios" });
  expect(aberto.getAttribute("aria-expanded")).toBe("true");
  expect(screen.getAllByRole("link", { name: /^O que é/ })).toHaveLength(2);

  unmount();
  render(enxuta("2026-11-19"));
  expect(celulasDa("52,00")).toHaveLength(15);
});

test("sem enxuta, a cadeia do Mercado continua com as 15 colunas, a fileira e as abas", () => {
  render(<TabelaCadeia ativo="PETR4" cadeia={CADEIA} indisponivel={null} onVencimentos={nada} />);
  expect(celulasDa("52,00")).toHaveLength(13);
  expect(screen.getByRole("group", { name: "Vencimentos" })).toBeTruthy();
  expect(screen.getAllByRole("tab")).toHaveLength(2);
  expect(screen.queryByRole("button", { name: /IV, delta e negócios/ })).toBeNull();
});

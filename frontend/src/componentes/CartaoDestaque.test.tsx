import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";

import type { ItemBook } from "../api/book";
import { itemCoberta } from "../testes/book";
import { CartaoDestaque } from "./CartaoDestaque";

function Sonda() {
  const local = useLocation();
  return (
    <pre data-testid="destino">{JSON.stringify({ busca: local.search, estado: local.state })}</pre>
  );
}

function itemBova(extra: Partial<ItemBook> = {}): ItemBook {
  return itemCoberta({
    ativo: "BOVA11",
    vencimento: "2026-11-06",
    dias_uteis: 4,
    pernas: [
      {
        ticker: "BOVAK168W1",
        tipo: "call",
        strike: 168,
        lado: "venda",
        quantidade: 100,
        premio: 1.12,
        qualidade: "executavel",
      },
    ],
    criterio: {
      chave: "anual",
      rotulo: "anualizado",
      valor: 0.412,
      unidade: "percentual",
      texto: "41,2%",
    },
    pedido: {
      ativo: "BOVA11",
      pernas: [{ ticker: "BOVAK168W1", lado: "venda", quantidade: 100, preco: null }],
      acao: { lado: "compra", quantidade: 100, origem: "compra", preco: null },
      modelo: "venda_coberta",
    },
    ...extra,
  });
}

function montar(item: ItemBook | null = itemBova(), motivoVazio = "nada passou nos filtros do preset") {
  render(
    <MemoryRouter initialEntries={["/book"]}>
      <Routes>
        <Route
          path="/book"
          element={
            <CartaoDestaque familia="renda" rotulo="Renda" item={item} motivoVazio={motivoVazio} />
          }
        />
        <Route path="/montador" element={<Sonda />} />
      </Routes>
    </MemoryRouter>,
  );
}

// O número pequeno é um rótulo e um valor lado a lado; o teste lê os dois juntos, sem o "?".
function numero(rotulo: string): string {
  const copia = screen.getByText(rotulo).closest(".resultado-numero")?.cloneNode(true) as HTMLElement;
  copia.querySelectorAll(".ajuda").forEach((ajuda) => ajuda.remove());
  return (copia.textContent ?? "").replace(/\s+/g, " ").trim();
}

const destino = (nome: string) => screen.getByRole("link", { name: nome }).getAttribute("href");

test("mostra a família, a operação, o número grande, o resultado e o porquê curto", () => {
  montar();
  expect(screen.getByRole("article", { name: "Renda" })).toBeTruthy();
  expect(screen.getByText("venda coberta · BOVA11 · vence 06/11/2026 (4 dias úteis)")).toBeTruthy();
  expect(screen.getByText("vender").parentElement?.textContent).toBe(
    "vender 100 BOVAK168W1 a 1,12 · comprar 100 BOVA11",
  );
  expect(screen.getByText("41,2%").parentElement?.textContent).toBe("41,2% anualizado ?");
  expect(numero("ganha até")).toBe("ganha até R$ 350,11");
  expect(numero("perde até")).toBe("perde até R$ 16.433,11");
  expect(numero("chance de lucro")).toBe("chance de lucro 62,0%");
  expect(
    screen.getByText("Renda com as suas ações: recebe o prêmio e aceita vender no strike."),
  ).toBeTruthy();
  expect(screen.getByRole("button", { name: "Abrir no montador" })).toBeTruthy();
});

test("a ação da carteira entra como comprar da carteira", () => {
  montar(itemBova({ acao: { lado: "compra", quantidade: 100, origem: "carteira" } }));
  expect(screen.getByText("vender").parentElement?.textContent).toBe(
    "vender 100 BOVAK168W1 a 1,12 · comprar 100 BOVA11 da carteira",
  );
});

test("vence em um dia útil só", () => {
  montar(itemBova({ dias_uteis: 1 }));
  expect(screen.getByText("venda coberta · BOVA11 · vence 06/11/2026 (1 dia útil)")).toBeTruthy();
});

test("sem resultado os três números mostram —", () => {
  montar(itemBova({ resultado: null }));
  expect(numero("ganha até")).toBe("ganha até —");
  expect(numero("perde até")).toBe("perde até —");
  expect(numero("chance de lucro")).toBe("chance de lucro —");
});

test("os '?' do cartão levam ao termo de cada número", () => {
  montar();
  expect(destino("O que é Anualizado?")).toBe("/aprender/termos#anualizado");
  const ganhoPerda = screen.getAllByRole("link", { name: "O que é Ganho e perda máximos?" });
  expect(ganhoPerda.map((link) => link.getAttribute("href"))).toEqual([
    "/aprender/termos#ganho-perda-maximos",
    "/aprender/termos#ganho-perda-maximos",
  ]);
  expect(destino("O que é Chance de lucro?")).toBe("/aprender/termos#chance-de-lucro");
});

test("critério sem termo no glossário fica sem '?' no número grande", () => {
  const criterio = { ...itemBova().criterio, chave: "custo_mensal", rotulo: "custo mensal equivalente" };
  montar(itemBova({ criterio }));
  expect(screen.getByText("41,2%").parentElement?.textContent).toBe("41,2% custo mensal equivalente");
  expect(screen.getAllByRole("link", { name: /^O que é/ })).toHaveLength(3);
});

test("ganho sem limite diz sem limite", () => {
  const resultado = { ...itemBova().resultado!, ganha_ate: null, ganha_ate_texto: "sem limite" };
  montar(itemBova({ resultado }));
  expect(numero("ganha até")).toBe("ganha até sem limite");
});

test("os avisos do item aparecem pequenos", () => {
  montar(itemBova({ rotulos: [{ chave: "perda_ilimitada", texto: "perda ilimitada" }] }));
  expect(screen.getByText("perda ilimitada")).toBeTruthy();
});

test("família sem item diz nada hoje com o motivo e sem botão", () => {
  render(
    <MemoryRouter>
      <CartaoDestaque
        familia="volatilidade"
        rotulo="Volatilidade"
        item={null}
        motivoVazio="sem preço de compra e venda agora"
      />
    </MemoryRouter>,
  );
  expect(screen.getByRole("article", { name: "Volatilidade" })).toBeTruthy();
  expect(screen.getByText("Nada hoje em Volatilidade")).toBeTruthy();
  expect(screen.getByText("sem preço de compra e venda agora")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Abrir no montador" })).toBeNull();
});

test("o cartão vazio tem o botão que leva à aba da família", () => {
  const verFamilia = vi.fn();
  render(
    <MemoryRouter>
      <CartaoDestaque
        familia="volatilidade"
        rotulo="Volatilidade"
        item={null}
        motivoVazio="sem preço de compra e venda agora"
        onVerFamilia={verFamilia}
      />
    </MemoryRouter>,
  );
  expect(verFamilia).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "ver a aba Volatilidade" }));
  expect(verFamilia).toHaveBeenCalledTimes(1);
});

test("o cartão com item não tem o botão da aba, nem o vazio sem o callback", () => {
  const { unmount } = render(
    <MemoryRouter>
      <CartaoDestaque
        familia="renda"
        rotulo="Renda"
        item={itemBova()}
        motivoVazio="nada passou nos filtros do preset"
        onVerFamilia={vi.fn()}
      />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button", { name: "ver a aba Renda" })).toBeNull();
  unmount();
  render(
    <MemoryRouter>
      <CartaoDestaque
        familia="volatilidade"
        rotulo="Volatilidade"
        item={null}
        motivoVazio="nada passou nos filtros do preset"
      />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("button")).toBeNull();
});

test("abrir no montador leva o pedido do item pelo estado da rota", async () => {
  const item = itemBova();
  montar(item);
  fireEvent.click(screen.getByRole("button", { name: "Abrir no montador" }));
  const destino = JSON.parse((await screen.findByTestId("destino")).textContent ?? "{}") as {
    busca: string;
    estado: { pedido: unknown };
  };
  expect(destino.busca).toBe("?ativo=BOVA11");
  expect(destino.estado.pedido).toEqual(item.pedido);
});

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test } from "vitest";

import type { EstadoAoVivo } from "../api/aoVivo";
import type { Carteira as CarteiraDados, RascunhoOperacao } from "../api/carteira";
import { carteira, mesIr, mesIrOutubro, trava } from "../testes/carteira";
import { simularFetch } from "../testes/fetchFalso";
import { Carteira } from "./Carteira";

const AO_VIVO: EstadoAoVivo = {
  conectado: true,
  status: null,
  cotacoes: [],
  motivoCotacoes: null,
  cadeia: null,
  cadeiaIndisponivel: null,
  carteira: null,
  carteiraIndisponivel: null,
};

function api(dados: CarteiraDados = carteira()) {
  return simularFetch((url, init) => {
    if (url === "/api/carteira") return { corpo: dados };
    if (url === "/api/carteira/historico") return { corpo: [trava({ id: "op9", nome: "coberta" })] };
    if (url === "/api/carteira/ir-mensal") return { corpo: [mesIr(), mesIrOutubro()] };
    if (url.startsWith("/api/carteira/operacoes") && init?.method === "POST")
      return { status: 201, corpo: { id: "op1" } };
    return undefined;
  });
}

function montar(aoVivo: EstadoAoVivo = AO_VIVO, registro?: RascunhoOperacao) {
  return render(
    <MemoryRouter
      initialEntries={[{ pathname: "/carteira", state: registro === undefined ? null : { registro } }]}
    >
      <Carteira aoVivo={aoVivo} />
    </MemoryRouter>,
  );
}

test("perna sem preço de zerar mostra o teórico rotulado e a operação fica sem total executável", async () => {
  api();
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /trava de alta/ }));
  const pernas = screen.getAllByRole("table")[1] as HTMLElement;
  const comprada = within(pernas).getByText("PETRK300").closest("tr");
  expect(comprada?.textContent).toContain("teórico 1,23");
  expect(comprada?.textContent).toContain("sem oferta de compra para zerar");
  expect(within(pernas).getByText("PETRK320").closest("tr")?.textContent).toContain("0,45");
  expect(screen.getAllByText("sem preço de zerar").length).toBeGreaterThan(0);
  expect(screen.getByText("preços de zerar ao vivo (Tryd)")).toBeTruthy();
});

test("o cabeçalho Preço de zerar tem o '?' que leva ao termo", async () => {
  api();
  montar();
  fireEvent.click(await screen.findByRole("button", { name: /trava de alta/ }));
  const ajudas = screen.getAllByRole("link", { name: "O que é Preço de zerar?" });
  expect(ajudas.length).toBeGreaterThan(0);
  for (const ajuda of ajudas) expect(ajuda.getAttribute("href")).toBe("/aprender/termos#preco-de-zerar");
});

test("o total por ativo vem por ativo e o total executável deixa de fora quem não tem preço", async () => {
  api();
  montar();
  const totais = (await screen.findByText("Total por ativo")).closest("table");
  expect(totais).not.toBeNull();
  const linhas = within(totais as HTMLTableElement).getAllByRole("row");
  expect(linhas.at(1)?.textContent).toContain("PETR4");
  expect(linhas.at(1)?.textContent).toContain("200");
  const rodape = linhas.at(-1)?.textContent ?? "";
  expect(rodape).toContain("Total executável");
  expect(rodape).toContain("245,00"); // 200 + 45; a PETRK300 sem preço fica de fora
  expect(rodape).toContain("1 sem preço de zerar");
});

test("o aviso de registrar o exercício abre o diálogo na perna vencida", async () => {
  api(
    carteira({
      avisos: [
        {
          operacao: "op1",
          perna: 1,
          ticker: "PETRK320",
          vencimento: "2026-11-19",
          situacao: "registrar_exercicio",
        },
        {
          operacao: "op1",
          perna: 0,
          ticker: "PETRK300",
          vencimento: "2026-11-19",
          situacao: "aguardando_fechamento",
        },
      ],
    }),
  );
  montar();
  expect(await screen.findByText(/aguardando o fechamento do pregão/)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Registrar" }));
  const dialogo = screen.getByRole("form", { name: "Exercício ou atribuição em trava de alta" });
  expect((within(dialogo).getByLabelText("Perna exercida") as HTMLSelectElement).value).toBe("1");
  expect(within(dialogo).getByRole("button", { name: "Registrar atribuição" })).toBeTruthy();
  expect((within(dialogo).getByLabelText("Data do exercício") as HTMLInputElement).value).toBe(
    "2026-11-19",
  );
});

test("o que vem do montador abre o formulário preenchido", async () => {
  api();
  montar(AO_VIVO, {
    ativo: "PETR4",
    nome: "venda coberta",
    data: "2026-11-04",
    pernas: [{ ticker: "PETRK541", lado: "venda", execucoes: [{ quantidade: 100, preco: 1.72, custos: null }] }],
    acao: null,
  });
  const form = await screen.findByRole("form", { name: "Registrar operação" });
  expect((within(form).getByLabelText("Ticker da perna 1") as HTMLInputElement).value).toBe("PETRK541");
  expect((within(form).getByLabelText("Preço de PETRK541 (1)") as HTMLInputElement).value).toBe("1,72");
});

test("a carteira do ao vivo substitui a lida pela API", async () => {
  api();
  const { rerender } = montar();
  await screen.findByRole("button", { name: /trava de alta/ });
  const nova = carteira({ operacoes: [trava({ id: "op2", nome: "strangle" })] });
  rerender(
    <MemoryRouter initialEntries={["/carteira"]}>
      <Carteira aoVivo={{ ...AO_VIVO, carteira: nova }} />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("button", { name: /strangle/ })).toBeTruthy();
});

test("o histórico traz as encerradas com os eventos", async () => {
  api();
  montar();
  fireEvent.click(await screen.findByRole("tab", { name: "Histórico" }));
  expect(await screen.findByText("coberta")).toBeTruthy();
  await waitFor(() => expect(screen.getByText(/abertura · PETRK300 · compra · 100 a 1,20/)).toBeTruthy());
});

test("a aba IR mensal busca e mostra o IR", async () => {
  const fetchFalso = api();
  montar();
  await screen.findByRole("button", { name: /trava de alta/ });
  const buscouIr = () => fetchFalso.mock.calls.some(([url]) => url === "/api/carteira/ir-mensal");
  expect(buscouIr()).toBe(false);
  fireEvent.click(screen.getByRole("tab", { name: "IR mensal" }));
  expect(await screen.findByText("R$ 18,35 até 30/12/2026")).toBeTruthy();
  expect(buscouIr()).toBe(true);
  expect(screen.getByText("abaixo de R$ 10: soma com o IR dos próximos meses")).toBeTruthy();
  expect(screen.getByRole("tab", { name: "IR mensal" }).getAttribute("aria-selected")).toBe("true");
  expect(screen.queryByRole("button", { name: /trava de alta/ })).toBeNull();
});

test("a aba IR mensal recarrega quando a Carteira recarrega", async () => {
  const fetchFalso = api();
  montar();
  await screen.findByRole("button", { name: /trava de alta/ });
  const leiturasDoIr = () =>
    fetchFalso.mock.calls.filter(([url]) => url === "/api/carteira/ir-mensal").length;
  fireEvent.click(screen.getByRole("tab", { name: "IR mensal" }));
  expect(await screen.findByText("R$ 18,35 até 30/12/2026")).toBeTruthy();
  expect(leiturasDoIr()).toBe(1);
  fireEvent.click(screen.getByRole("button", { name: "Registrar operação" }));
  const form = await screen.findByRole("form", { name: "Registrar operação" });
  fireEvent.click(within(form).getByRole("button", { name: "Cancelar" }));
  await waitFor(() => expect(leiturasDoIr()).toBe(2));
});

test("sem perfil ou com a pasta fora do ar aparece o motivo", async () => {
  simularFetch(() => ({ status: 422, corpo: { erro: "ProfileFolderUnavailableError", mensagem: "pasta do perfil fora do ar" } }));
  montar();
  expect((await screen.findByRole("alert")).textContent).toBe("pasta do perfil fora do ar");
});

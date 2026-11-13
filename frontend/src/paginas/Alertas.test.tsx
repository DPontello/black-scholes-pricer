import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, test } from "vitest";

import type { Alertas as AlertasDados } from "../api/alertas";
import type { EstadoAoVivo } from "../api/aoVivo";
import type { Perfil } from "../api/cliente";
import { alerta, alertas, rolagem } from "../testes/alertas";
import { PERFIL } from "../testes/book";
import { simularFetch } from "../testes/fetchFalso";
import { Alertas, frase } from "./Alertas";

const AO_VIVO: EstadoAoVivo = {
  conectado: true,
  status: null,
  cotacoes: [],
  motivoCotacoes: null,
  cadeia: null,
  cadeiaIndisponivel: null,
  carteira: null,
  carteiraIndisponivel: null,
  alertas: null,
  alertasIndisponiveis: null,
};

function api(dados: AlertasDados = alertas()) {
  return simularFetch((url, init) => {
    if (url === "/api/alertas") return { corpo: dados };
    if (url.endsWith("/dispensar") || url === "/api/alertas/restaurar") return { status: 204 };
    if (url === "/api/alertas/rolagem/op1") return { corpo: rolagem() };
    if (url === "/api/perfil/alertas" && init?.method === "PUT")
      return { corpo: { ...PERFIL, alertas: JSON.parse(String(init.body)) as Perfil["alertas"] } };
    return undefined;
  });
}

function Destino() {
  const local = useLocation();
  return (
    <p>
      destino {local.pathname}
      {local.search} {JSON.stringify(local.state)}
    </p>
  );
}

function montar(aoVivo: EstadoAoVivo = AO_VIVO, onPerfil: (p: Perfil) => void = () => {}) {
  return render(
    <MemoryRouter initialEntries={["/alertas"]}>
      <Routes>
        <Route path="/alertas" element={<Alertas aoVivo={aoVivo} perfil={PERFIL} onPerfil={onPerfil} />} />
        <Route path="*" element={<Destino />} />
      </Routes>
    </MemoryRouter>,
  );
}

test("sem alertas mostra o vazio", async () => {
  api(alertas({ alertas: [] }));
  montar();
  expect(await screen.findByText("Nenhum alerta agora.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /Mostrar dispensados/ })).toBeNull();
});

test("agrupa por operação na ordem de gravidade, com as frases", async () => {
  api();
  montar();
  const grupos = await screen.findAllByRole("article");
  expect(grupos.map((g) => g.getAttribute("aria-label"))).toEqual(["ações à mão", "put coberta"]);
  expect(grupos[0]?.textContent).toContain("Stop: resultado R$ -210,00 (limite R$ -200,00)");
  const put = within(grupos[1] as HTMLElement);
  expect(put.getByText("PETRW280 vendida perto do strike: risco de exercício, vence em 2 dias úteis")).toBeTruthy();
  expect(put.getByText("PETRW280 vence em 2 dias úteis (19/11/2026)")).toBeTruthy();
  expect(put.getByRole("button", { name: "Rolar" })).toBeTruthy();
  expect(within(grupos[0] as HTMLElement).queryByRole("button", { name: "Rolar" })).toBeNull();
});

test("frases dos outros tipos", () => {
  expect(frase(alerta({ tipo: "vencimento_proximo", dias_uteis: 0 }))).toContain("vence hoje");
  expect(frase(alerta({ tipo: "exercicio_a_registrar" }))).toContain("registre o exercício");
  expect(frase(alerta({ tipo: "aguardando_fechamento" }))).toContain("aguardando o fechamento");
  expect(frase(alerta({ tipo: "risco_de_exercicio", dentro_do_dinheiro: true }))).toContain(
    "dentro do dinheiro",
  );
  expect(frase(alerta({ tipo: "alvo", total: 150, limite: 100 }))).toBe(
    "Alvo: resultado R$ 150,00 (alvo R$ 100,00)",
  );
});

test("o stop estimado e o stop sem preço dizem de onde vem o número", () => {
  expect(frase(alerta({ tipo: "stop", total: -60, limite: 50, estimado: true }))).toBe(
    "Stop: resultado estimado R$ -60,00, pelo teórico da perna sem oferta para zerar (limite R$ -50,00)",
  );
  expect(frase(alerta({ tipo: "stop_sem_preco", limite: 50 }))).toBe(
    "Stop sem preço para avaliar: uma perna está sem oferta para zerar e sem teórico (limite R$ -50,00)",
  );
});

test("dispensar chama a rota e lê de novo", async () => {
  const fetch = api();
  montar();
  const grupo = (await screen.findAllByRole("article"))[0] as HTMLElement;
  fireEvent.click(within(grupo).getByRole("button", { name: "Dispensar" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([url]) => url === "/api/alertas/stop%3Aop2%3A-/dispensar")).toBe(true),
  );
  await waitFor(() => expect(fetch.mock.calls.filter(([url]) => url === "/api/alertas").length).toBe(2));
});

test("mostrar os dispensados restaura todos", async () => {
  const fetch = api(alertas({ dispensados: 2 }));
  montar();
  fireEvent.click(await screen.findByRole("button", { name: "Mostrar dispensados (2)" }));
  await waitFor(() =>
    expect(fetch.mock.calls.some(([url]) => url === "/api/alertas/restaurar")).toBe(true),
  );
});

test("abrir na carteira vai à operação", async () => {
  api();
  montar();
  const grupo = (await screen.findAllByRole("article"))[1] as HTMLElement;
  fireEvent.click(within(grupo).getByRole("button", { name: "Abrir na Carteira" }));
  expect(await screen.findByText(/destino \/carteira\?operacao=op1/)).toBeTruthy();
});

test("rolar abre o montador com o pedido e a rolagem", async () => {
  api();
  montar();
  const grupo = (await screen.findAllByRole("article"))[1] as HTMLElement;
  fireEvent.click(within(grupo).getByRole("button", { name: "Rolar" }));
  const destino = await screen.findByText(/destino \/montador\?ativo=PETR4/);
  expect(destino.textContent).toContain('"pedido":{"ativo":"PETR4"');
  expect(destino.textContent).toContain('"caixa_de_zerar":-35');
});

test("a lista do websocket substitui a da api, e o fim de dia aparece rotulado", async () => {
  api();
  const { rerender } = montar();
  await screen.findAllByRole("article");
  const aoVivo = { ...AO_VIVO, alertas: alertas({ alertas: [alerta()], fonte: "fim_de_dia" }) };
  rerender(
    <MemoryRouter initialEntries={["/alertas"]}>
      <Routes>
        <Route path="/alertas" element={<Alertas aoVivo={aoVivo} perfil={PERFIL} onPerfil={() => {}} />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(await screen.findByText("pelo fim de dia (B3)")).toBeTruthy();
  expect(screen.getAllByRole("article")).toHaveLength(1);
});

test("os limites gravam no perfil, em fração", async () => {
  const fetch = api();
  let gravado: Perfil | null = null;
  montar(AO_VIVO, (p) => {
    gravado = p;
  });
  const form = screen.getByRole("form", { name: "Limites dos alertas" });
  const [dias, distancia] = within(form).getAllByRole("spinbutton") as HTMLInputElement[];
  expect([dias?.value, distancia?.value]).toEqual(["5", "2"]);
  fireEvent.change(dias as HTMLInputElement, { target: { value: "10" } });
  fireEvent.change(distancia as HTMLInputElement, { target: { value: "3.5" } });
  fireEvent.click(within(form).getByRole("button", { name: "Gravar" }));
  expect(await screen.findByText("Limites gravados no perfil.")).toBeTruthy();
  const put = fetch.mock.calls.find(([url]) => url === "/api/perfil/alertas");
  expect(JSON.parse(String(put?.[1]?.body))).toEqual({ dias_vencimento: 10, distancia_strike: 0.035 });
  expect(gravado).not.toBeNull();
});

test("sem perfil aberto mostra o motivo", async () => {
  simularFetch(() => ({ status: 404, corpo: { erro: "NoActiveProfileError", mensagem: "nenhum perfil aberto" } }));
  montar();
  expect((await screen.findByRole("alert")).textContent).toBe("nenhum perfil aberto");
});

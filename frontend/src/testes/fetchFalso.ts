import { vi } from "vitest";

type Resposta = { status?: number; corpo?: unknown };
type Rota = (url: string, init?: RequestInit) => Resposta | undefined;

/** Troca o fetch global por um que responde pelas rotas dadas; devolve o mock para inspeção. */
export function simularFetch(rota: Rota) {
  const mock = vi.fn(async (entrada: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof entrada === "string" ? entrada : entrada.toString();
    const resposta = rota(url, init) ?? { status: 404, corpo: { erro: "NaoEncontrado", mensagem: url } };
    const status = resposta.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(resposta.corpo ?? null), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

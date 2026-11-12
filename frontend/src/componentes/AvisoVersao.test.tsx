import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { EstadoAtualizacao, InfoVersao } from "../api/versao";
import { simularFetch } from "../testes/fetchFalso";
import { AvisoVersao } from "./AvisoVersao";

const NOVIDADES = ["Atualização pelo app", "Correção no book"];

function info(novidades: string[] = NOVIDADES): InfoVersao {
  return { atual: "0.5.0", nova: { versao: "0.5.1", novidades, tamanho: 31457280 } };
}

function estado(fase: EstadoAtualizacao["fase"], baixado = 0, mensagem = ""): EstadoAtualizacao {
  return { fase, baixado, total: 31457280, mensagem };
}

const BAIXANDO_12 = estado("baixando", 12582912);
const INSTALANDO = estado("instalando", 31457280);

function chamadasPost(fetch: ReturnType<typeof simularFetch>): number {
  return fetch.mock.calls.filter(([, init]) => init?.method === "POST").length;
}

// O ouvinte do Esc é registrado num efeito, um instante depois de a janela aparecer.
async function esc(): Promise<void> {
  await waitFor(() => {
    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
}

function esperar(ms: number): Promise<void> {
  return new Promise((resolver) => setTimeout(resolver, ms));
}

test("com versão nova, a janela diz a versão, a atual e o que mudou", async () => {
  simularFetch((url) => (url === "/api/versao" ? { corpo: info() } : undefined));
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  expect(await screen.findByRole("dialog", { name: "Versão nova do app: 0.5.1" })).toBeTruthy();
  expect(screen.getByText("Você está usando a 0.5.0. O que mudou:")).toBeTruthy();
  for (const item of NOVIDADES) expect(screen.getByText(item)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Agora não" })).toBeTruthy();
  const atualizar = screen.getByRole("button", { name: "Atualizar" });
  expect(atualizar.className).toBe("botao-principal");
  // O foco sai de um efeito, que pode rodar um instante depois de a janela aparecer.
  await waitFor(() => expect(document.activeElement).toBe(atualizar));
});

test("sem versão nova, ou com a consulta falhando, nada aparece", async () => {
  const semNova = simularFetch((url) =>
    url === "/api/versao" ? { corpo: { atual: "0.5.0", nova: null } } : undefined,
  );
  const { unmount } = render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  await waitFor(() => expect(semNova).toHaveBeenCalledWith("/api/versao", undefined));
  await esperar(20);
  expect(screen.queryByRole("dialog")).toBeNull();
  unmount();

  const falhando = simularFetch(() => undefined);
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  await waitFor(() => expect(falhando).toHaveBeenCalledWith("/api/versao", undefined));
  await esperar(20);
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("mais de 5 novidades mostram 5 e 'e mais N'", async () => {
  const sete = Array.from({ length: 7 }, (_, i) => `Novidade ${i + 1}`);
  simularFetch((url) => (url === "/api/versao" ? { corpo: info(sete) } : undefined));
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  await screen.findByRole("dialog");
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(sete.slice(0, 5));
  expect(screen.getByText("e mais 2")).toBeTruthy();
});

test("Agora não e Esc fecham a janela", async () => {
  simularFetch((url) => (url === "/api/versao" ? { corpo: info() } : undefined));
  const { unmount } = render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Agora não" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  unmount();

  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  await screen.findByRole("dialog");
  await esc();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("Atualizar mostra o andamento em MB e depois Instalando", async () => {
  let atual = estado("baixando", 0);
  const fetch = simularFetch((url) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") return { corpo: atual };
    if (url === "/api/saude?janela=1") return { corpo: { status: "ok", versao: "0.5.0", app: "painel-de-opcoes" } };
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  expect(chamadasPost(fetch)).toBe(1);

  atual = BAIXANDO_12;
  expect(await screen.findByText("Baixando a versão nova: 12 de 30 MB")).toBeTruthy();
  const barra = screen.getByRole("progressbar", { name: "Andamento do download" }) as HTMLProgressElement;
  expect(barra.value).toBe(12582912);
  expect(barra.max).toBe(31457280);
  expect(screen.queryAllByRole("button")).toHaveLength(0);

  atual = INSTALANDO;
  expect(
    await screen.findByText("Instalando. O app fecha e abre de novo sozinho, em menos de um minuto."),
  ).toBeTruthy();
  expect(screen.queryByRole("progressbar")).toBeNull();
  expect(screen.queryAllByRole("button")).toHaveLength(0);
});

test("durante o download e a instalação o Esc não fecha a janela", async () => {
  simularFetch((url) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") return { corpo: BAIXANDO_12 };
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  await screen.findByText("Baixando a versão nova: 12 de 30 MB");
  await esperar(20);
  fireEvent.keyDown(document.body, { key: "Escape" });
  expect(screen.getByRole("dialog")).toBeTruthy();
});

test("se o servidor some durante o andamento, é porque está instalando", async () => {
  let fora = false;
  simularFetch((url, init) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") {
      if (fora) throw new TypeError("Failed to fetch");
      return { corpo: init?.method === "POST" ? estado("baixando", 0) : BAIXANDO_12 };
    }
    if (url === "/api/saude?janela=1") throw new TypeError("Failed to fetch");
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  await screen.findByText("Baixando a versão nova: 12 de 30 MB");

  fora = true;
  expect(await screen.findByText(/^Instalando/)).toBeTruthy();
  expect(screen.queryByRole("progressbar")).toBeNull();
});

function leiturasDeAndamento(fetch: ReturnType<typeof simularFetch>): number {
  return fetch.mock.calls.filter(
    ([url, init]) => url === "/api/versao/atualizar" && init?.method !== "POST",
  ).length;
}

function chamouSaude(fetch: ReturnType<typeof simularFetch>): boolean {
  return fetch.mock.calls.some(([url]) => url === "/api/saude?janela=1");
}

test("um erro HTTP isolado na consulta do andamento não vira Instalando", async () => {
  const fetch = simularFetch((url, init) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") {
      if (init?.method === "POST") return { corpo: estado("baixando", 0) };
      if (leiturasDeAndamento(fetch) === 1)
        return { status: 500, corpo: { erro: "ErroInterno", mensagem: "o servidor falhou" } };
      return { corpo: BAIXANDO_12 };
    }
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  expect(await screen.findByText("Baixando a versão nova: 12 de 30 MB")).toBeTruthy();
  await esperar(30);
  expect(leiturasDeAndamento(fetch)).toBeGreaterThan(1);
  expect(screen.getByText("Baixando a versão nova: 12 de 30 MB")).toBeTruthy();
  expect(screen.queryByText(/^Instalando/)).toBeNull();
  expect(chamouSaude(fetch)).toBe(false);
});

test("3 erros HTTP seguidos na consulta do andamento mostram o erro, com os botões", async () => {
  const fetch = simularFetch((url, init) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") {
      if (init?.method === "POST") return { corpo: estado("baixando", 0) };
      return { status: 503, corpo: { erro: "ErroInterno", mensagem: "o servidor falhou" } };
    }
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  expect(
    await screen.findByText(
      "Não deu para baixar a versão nova: o servidor falhou. O app continua na versão 0.5.0.",
    ),
  ).toBeTruthy();
  expect(leiturasDeAndamento(fetch)).toBeGreaterThanOrEqual(3);
  expect(screen.getByRole("button", { name: "Tentar de novo" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Fechar" })).toBeTruthy();
  expect(screen.queryByText(/^Instalando/)).toBeNull();
  expect(chamouSaude(fetch)).toBe(false);
});

test("uma resposta boa no meio zera a contagem dos erros HTTP", async () => {
  // Erro, erro, bom, erro, erro, bom: só 2 seguidos de cada vez, então nunca chega a 3.
  const sequencia = [500, 500, 200, 500, 500, 200];
  const fetch = simularFetch((url, init) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") {
      if (init?.method === "POST") return { corpo: estado("baixando", 0) };
      const status = sequencia[leiturasDeAndamento(fetch) - 1] ?? 200;
      return status === 200
        ? { corpo: BAIXANDO_12 }
        : { status, corpo: { erro: "ErroInterno", mensagem: "o servidor falhou" } };
    }
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  await waitFor(() => expect(leiturasDeAndamento(fetch)).toBeGreaterThan(sequencia.length + 2));
  expect(screen.getByText("Baixando a versão nova: 12 de 30 MB")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Tentar de novo" })).toBeNull();
  expect(screen.queryByText(/^Instalando/)).toBeNull();
});

test("quando o app volta na versão nova, a página recarrega", async () => {
  const vistas: string[] = [];
  let vistasAoRecarregar: string[] = [];
  const recarregar = vi.fn(() => {
    vistasAoRecarregar = [...vistas];
  });
  const fetch = simularFetch((url) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") return { corpo: INSTALANDO };
    if (url === "/api/saude?janela=1") {
      const versao = vistas.length < 2 ? "0.5.0" : "0.5.1";
      vistas.push(versao);
      return { corpo: { status: "ok", versao, app: "painel-de-opcoes" } };
    }
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={recarregar} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  await waitFor(() => expect(recarregar).toHaveBeenCalledTimes(1));
  expect(vistasAoRecarregar).toEqual(["0.5.0", "0.5.0", "0.5.1"]);
  expect(fetch).toHaveBeenCalledWith("/api/saude?janela=1", undefined);

  await esperar(40);
  expect(recarregar).toHaveBeenCalledTimes(1);
});

test("passado o limite sem voltar, diz para abrir pelo atalho", async () => {
  simularFetch((url) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") return { corpo: INSTALANDO };
    return undefined;
  });
  const recarregar = vi.fn();
  render(<AvisoVersao intervaloMs={5} limiteMs={40} recarregar={recarregar} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  const atalho = "Se o app não abrir sozinho, abra pelo atalho Painel de Opções.";
  expect(screen.queryByText(atalho)).toBeNull();
  expect(await screen.findByText(atalho)).toBeTruthy();
  expect(screen.queryAllByRole("button")).toHaveLength(0);
  expect(recarregar).not.toHaveBeenCalled();
});

test("erro no download mostra o motivo, e Tentar de novo começa outra vez", async () => {
  let atual = estado("erro", 0, "o arquivo baixado não confere");
  const fetch = simularFetch((url, init) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar") {
      if (init?.method === "POST") atual = chamadasPost(fetch) === 1 ? atual : estado("baixando", 0);
      return { corpo: atual };
    }
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  expect(
    await screen.findByText(
      "Não deu para baixar a versão nova: o arquivo baixado não confere. O app continua na versão 0.5.0.",
    ),
  ).toBeTruthy();
  expect(chamadasPost(fetch)).toBe(1);

  fireEvent.click(screen.getByRole("button", { name: "Tentar de novo" }));
  expect(chamadasPost(fetch)).toBe(2);
  expect(await screen.findByText("Baixando a versão nova: 0 de 30 MB")).toBeTruthy();

  atual = estado("erro", 0, "a conexão com o GitHub falhou");
  expect(
    await screen.findByText(
      "Não deu para baixar a versão nova: a conexão com o GitHub falhou. O app continua na versão 0.5.0.",
    ),
  ).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "Fechar" }));
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("no erro o Esc também fecha a janela", async () => {
  simularFetch((url) => {
    if (url === "/api/versao") return { corpo: info() };
    if (url === "/api/versao/atualizar")
      return { corpo: estado("erro", 0, "não deu para abrir o instalador") };
    return undefined;
  });
  render(<AvisoVersao intervaloMs={5} recarregar={vi.fn()} />);
  fireEvent.click(await screen.findByRole("button", { name: "Atualizar" }));
  await screen.findByRole("button", { name: "Tentar de novo" });
  await esc();
  expect(screen.queryByRole("dialog")).toBeNull();
});

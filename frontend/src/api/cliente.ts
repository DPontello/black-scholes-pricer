
export type Fonte = "ao_vivo" | "atrasado" | "fim_de_dia";

export type EntradaPerfil = { nome: string; pasta: string };

export type Perfil = { nome: string; ativos: string[]; cdi_anual: number };

export type ArquivoB3 = {
  tipo: "cotahist" | "cadastro";
  nome: string;
  data: string | null;
  importado_em?: string;
};

export type StatusMercado = {
  fonte: Fonte;
  cadastro: { data: string; dias_uteis: number; velho: boolean } | null;
  cadastro_motivo: string | null;
  cotahist: { de: string; ate: string } | null;
};

export type Trava = { pc: string; desde: string };

export class ErroApi extends Error {
  readonly status: number;
  readonly erro: string;
  readonly trava: Trava | undefined;

  constructor(status: number, erro: string, mensagem: string, trava?: Trava) {
    super(mensagem);
    this.name = "ErroApi";
    this.status = status;
    this.erro = erro;
    this.trava = trava;
  }

  get mensagem(): string {
    return this.message;
  }
}

async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
  const resposta = await fetch(caminho, init);
  if (!resposta.ok) {
    let corpo: { erro?: string; mensagem?: string; trava?: Trava } = {};
    try {
      corpo = (await resposta.json()) as typeof corpo;
    } catch {
      // corpo vazio ou não-JSON: fica a mensagem genérica
    }
    throw new ErroApi(
      resposta.status,
      corpo.erro ?? "ErroHttp",
      corpo.mensagem ?? `Erro ${resposta.status} ao falar com o app.`,
      corpo.trava,
    );
  }
  if (resposta.status === 204) return undefined as T;
  return (await resposta.json()) as T;
}

function json(metodo: string, corpo: unknown): RequestInit {
  return {
    method: metodo,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  };
}

export function listarPerfis(): Promise<EntradaPerfil[]> {
  return pedir("/api/perfis");
}

export function criarPerfil(nome: string, pasta: string): Promise<Perfil> {
  return pedir("/api/perfis", json("POST", { nome, pasta }));
}

export function abrirPerfil(nome: string, forcar: boolean): Promise<Perfil> {
  return pedir(`/api/perfis/${encodeURIComponent(nome)}/abrir`, json("POST", { forcar }));
}

export async function perfilAtivo(): Promise<Perfil | null> {
  try {
    return await pedir<Perfil>("/api/perfil");
  } catch (erro) {
    if (erro instanceof ErroApi && erro.status === 404) return null;
    throw erro;
  }
}

export function definirAtivos(ativos: string[]): Promise<Perfil> {
  return pedir("/api/perfil/ativos", json("PUT", { ativos }));
}

export function listarArquivos(): Promise<ArquivoB3[]> {
  return pedir("/api/mercado/arquivos");
}

// Corpo binário com o nome na query: a API não usa multipart.
export function enviarArquivo(arquivo: File): Promise<ArquivoB3> {
  return pedir(`/api/mercado/arquivos?nome=${encodeURIComponent(arquivo.name)}`, {
    method: "POST",
    body: arquivo,
  });
}

export function statusMercado(): Promise<StatusMercado> {
  return pedir("/api/mercado/status");
}

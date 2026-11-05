
export type Fonte = "ao_vivo" | "atrasado" | "fim_de_dia";

export type EntradaPerfil = { nome: string; pasta: string };

export type NomePreset = "conservador" | "moderado" | "arrojado";

/** Spread e piso em fração (0,2 = 20%); risco em reais, só nas estruturas sem ação. */
export type ValoresBook = {
  delta_min: number;
  delta_max: number;
  negocios_min: number;
  spread_max: number;
  risco_max: number;
  vencimentos: number;
  piso_protecao: number;
  perda_ilimitada: boolean;
};

export type PresetBook = ValoresBook & { preset: NomePreset };

/** `distancia_strike` em fração do strike (0,02 = 2%). */
export type LimitesAlertas = { dias_vencimento: number; distancia_strike: number };

export type Perfil = {
  nome: string;
  ativos: string[];
  cdi_anual: number;
  book: PresetBook;
  alertas: LimitesAlertas;
};

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
  cotahist: { de: string; ate: string; dias_uteis: number | null; velho: boolean } | null;
};

export type Trava = { pc: string; desde: string };

export type ImportacaoAutomatica = {
  pasta: string | null;
  eventos: { nome: string; quando: string; importado: boolean; detalhe: string }[];
};

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

export async function pedir<T>(caminho: string, init?: RequestInit): Promise<T> {
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

export function json(metodo: string, corpo: unknown): RequestInit {
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

// Abre a janela de escolha de pasta do sistema (o servidor é local); null se a pessoa cancelou.
export async function escolherPasta(): Promise<string | null> {
  const { pasta } = await pedir<{ pasta: string | null }>(
    "/api/perfis/escolher-pasta",
    json("POST", {}),
  );
  return pasta;
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

// Sem `valores`, a API grava os padrões do preset: é o "voltar ao padrão" e a troca de preset.
export function definirBook(preset: NomePreset, valores?: ValoresBook): Promise<Perfil> {
  return pedir("/api/perfil/book", json("PUT", valores === undefined ? { preset } : { preset, valores }));
}

export function definirLimitesAlertas(limites: LimitesAlertas): Promise<Perfil> {
  return pedir("/api/perfil/alertas", json("PUT", limites));
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

export function importacaoAutomatica(): Promise<ImportacaoAutomatica> {
  return pedir("/api/mercado/arquivos/automatico");
}

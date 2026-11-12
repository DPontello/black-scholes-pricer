// /api/versao: a versão nova do app, o início da atualização e o andamento dela.

import { json, pedir } from "./cliente";

export type VersaoNova = { versao: string; novidades: string[]; tamanho: number };

/** `nova` é null sem versão nova (ou fora do app instalado). */
export type InfoVersao = { atual: string; nova: VersaoNova | null };

export type FaseAtualizacao = "parado" | "baixando" | "instalando" | "erro";

/** `baixado` e `total` em bytes; `mensagem` só vem preenchida no erro. */
export type EstadoAtualizacao = {
  fase: FaseAtualizacao;
  baixado: number;
  total: number;
  mensagem: string;
};

export function conferirVersao(): Promise<InfoVersao> {
  return pedir("/api/versao");
}

export function iniciarAtualizacao(): Promise<EstadoAtualizacao> {
  return pedir("/api/versao/atualizar", json("POST", {}));
}

export function estadoAtualizacao(): Promise<EstadoAtualizacao> {
  return pedir("/api/versao/atualizar");
}

// O `?janela=1` avisa o servidor novo de que a janela antiga voltou a falar com ele.
export async function versaoNoAr(): Promise<string> {
  const { versao } = await pedir<{ versao: string }>("/api/saude?janela=1");
  return versao;
}

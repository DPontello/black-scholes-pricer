import { useState } from "react";

export const PREFERENCIA_COLUNAS = "montador.colunas-completas";
export const PREFERENCIA_DETALHES = "montador.detalhes";

// Sem o localStorage (janela anônima, por exemplo), a escolha vale só na memória e abre fechada.
export function usePreferencia(chave: string): [boolean, (valor: boolean) => void] {
  const [valor, setValor] = useState(() => {
    try {
      return localStorage.getItem(chave) === "1";
    } catch {
      return false;
    }
  });

  function escolher(novo: boolean) {
    setValor(novo);
    try {
      localStorage.setItem(chave, novo ? "1" : "0");
    } catch {
      // a escolha fica só na memória
    }
  }

  return [valor, escolher];
}

// WebSocket /api/ao-vivo. Ao reconectar, pede de novo a cadeia que estava aberta.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Fonte, StatusMercado } from "./cliente";

export type Cotacao = {
  ativo: string;
  ultimo: number | null;
  compra: number | null;
  venda: number | null;
  fechamento_anterior: number | null;
  /** Decimal: -0.0059 = -0,59%. */
  variacao_pct: number | null;
  negocios: number | null;
  volume: number | null;
  hora: string | null;
  fonte: Fonte | null;
  motivo: string | null;
};

export type Serie = {
  ticker: string;
  tipo: "call" | "put";
  strike: number;
  estilo: "american" | "european";
  compra: number | null;
  venda: number | null;
  ultimo: number | null;
  negocios: number;
  volume: number;
  iv: number | null;
  delta: number | null;
};

export type Vencimento = { data: string; dias_uteis: number; series: Serie[] };

export type Cadeia = {
  ativo: string;
  spot: number;
  fonte: Fonte;
  hora: string;
  vencimentos: Vencimento[];
  rejeitadas: { ticker: string; motivo: string }[];
};

export type CadeiaIndisponivel = { ativo: string; erro: string; mensagem: string };

export type EstadoAoVivo = {
  conectado: boolean;
  status: StatusMercado | null;
  cotacoes: Cotacao[];
  motivoCotacoes: string | null;
  cadeia: Cadeia | null;
  cadeiaIndisponivel: CadeiaIndisponivel | null;
};

type Mensagem =
  | ({ tipo: "status" } & StatusMercado)
  | { tipo: "cotacoes"; dados: Cotacao[]; motivo: string | null }
  | { tipo: "cadeia"; dados: Cadeia }
  | ({ tipo: "cadeia" } & CadeiaIndisponivel)
  | { tipo: "erro"; erro: string; mensagem: string };

const RECONEXAO_MS = 2000;

const INICIAL: EstadoAoVivo = {
  conectado: false,
  status: null,
  cotacoes: [],
  motivoCotacoes: null,
  cadeia: null,
  cadeiaIndisponivel: null,
};

export function aplicar(estado: EstadoAoVivo, mensagem: Mensagem): EstadoAoVivo {
  switch (mensagem.tipo) {
    case "status": {
      const { tipo: _tipo, ...status } = mensagem;
      return { ...estado, status };
    }
    case "cotacoes":
      return { ...estado, cotacoes: mensagem.dados, motivoCotacoes: mensagem.motivo };
    case "cadeia":
      return "dados" in mensagem
        ? { ...estado, cadeia: mensagem.dados, cadeiaIndisponivel: null }
        : {
            ...estado,
            cadeia: null,
            cadeiaIndisponivel: {
              ativo: mensagem.ativo,
              erro: mensagem.erro,
              mensagem: mensagem.mensagem,
            },
          };
    case "erro":
      return estado; // pedido inválido do próprio frontend: nada a mostrar ao usuário
  }
}

function urlAoVivo(): string {
  const protocolo = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocolo}://${window.location.host}/api/ao-vivo`;
}

export function useAoVivo(): EstadoAoVivo & {
  seguirCadeia: (ativo: string | null, vencimentos?: number) => void;
} {
  const [estado, setEstado] = useState<EstadoAoVivo>(INICIAL);
  const socket = useRef<WebSocket | null>(null);
  const pedidoCadeia = useRef<{ ativo: string | null; vencimentos: number }>({
    ativo: null,
    vencimentos: 2,
  });

  useEffect(() => {
    let encerrado = false;
    let espera: ReturnType<typeof setTimeout> | undefined;

    function conectar() {
      const ws = new WebSocket(urlAoVivo());
      socket.current = ws;
      ws.onopen = () => {
        setEstado((atual) => ({ ...atual, conectado: true }));
        if (pedidoCadeia.current.ativo !== null)
          ws.send(JSON.stringify({ tipo: "cadeia", ...pedidoCadeia.current }));
      };
      ws.onmessage = (evento: MessageEvent<string>) => {
        const mensagem = JSON.parse(evento.data) as Mensagem;
        setEstado((atual) => aplicar(atual, mensagem));
      };
      ws.onclose = () => {
        socket.current = null;
        setEstado((atual) => ({ ...atual, conectado: false }));
        if (!encerrado) espera = setTimeout(conectar, RECONEXAO_MS);
      };
    }

    conectar();
    return () => {
      encerrado = true;
      clearTimeout(espera);
      socket.current?.close();
    };
  }, []);

  const seguirCadeia = useCallback((ativo: string | null, vencimentos = 2) => {
    pedidoCadeia.current = { ativo, vencimentos };
    if (ativo === null) setEstado((atual) => ({ ...atual, cadeia: null, cadeiaIndisponivel: null }));
    const ws = socket.current;
    if (ws !== null && ws.readyState === WebSocket.OPEN)
      ws.send(JSON.stringify({ tipo: "cadeia", ativo, vencimentos }));
  }, []);

  return { ...estado, seguirCadeia };
}

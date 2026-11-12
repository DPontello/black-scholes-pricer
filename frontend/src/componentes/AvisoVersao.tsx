import { useEffect, useRef, useState } from "react";

import { ErroApi } from "../api/cliente";
import {
  conferirVersao,
  type EstadoAtualizacao,
  estadoAtualizacao,
  type InfoVersao,
  iniciarAtualizacao,
  versaoNoAr,
} from "../api/versao";

type Props = {
  intervaloMs?: number;
  limiteMs?: number;
  recarregar?: () => void;
};

type Fase = "fechado" | "aviso" | "baixando" | "instalando" | "demorou" | "erro";

const MAX_NOVIDADES = 5;
const ERROS_SEGUIDOS = 3;

function emMb(bytes: number): number {
  return Math.round(bytes / 1048576);
}

// Janela por cima de qualquer tela, aberta uma vez ao carregar a página se houver versão nova.
export function AvisoVersao({
  intervaloMs = 1000,
  limiteMs = 120_000,
  recarregar = () => window.location.reload(),
}: Props) {
  const [info, setInfo] = useState<InfoVersao | null>(null);
  const [fase, setFase] = useState<Fase>("fechado");
  const [estado, setEstado] = useState<EstadoAtualizacao | null>(null);
  const principal = useRef<HTMLButtonElement>(null);
  const janela = useRef<HTMLDivElement>(null);
  // Fora das dependências do efeito: a função padrão é nova a cada render e reiniciaria o relógio.
  const recarregarRef = useRef(recarregar);
  recarregarRef.current = recarregar;

  function aplicar(novo: EstadoAtualizacao) {
    setEstado(novo);
    setFase(novo.fase === "erro" ? "erro" : novo.fase === "instalando" ? "instalando" : "baixando");
  }

  // Sem conferência (rota ausente, sem rede, sem versão nova), a tela segue sem aviso.
  useEffect(() => {
    let cancelado = false;
    conferirVersao().then(
      (resposta) => {
        if (cancelado || resposta.nova === null) return;
        setInfo(resposta);
        setFase("aviso");
      },
      () => {},
    );
    return () => {
      cancelado = true;
    };
  }, []);

  // Se o servidor deixa de responder durante o andamento (falha de rede), é o instalador: ele o
  // encerra. Resposta de erro (ErroApi) é o servidor de pé com problema: tenta de novo e, depois
  // de ERROS_SEGUIDOS seguidos, mostra o erro.
  useEffect(() => {
    if (fase !== "baixando") return;
    let cancelado = false;
    let seguidos = 0;
    const id = setInterval(() => {
      estadoAtualizacao().then(
        (novo) => {
          if (cancelado) return;
          seguidos = 0;
          aplicar(novo);
        },
        (erro: unknown) => {
          if (cancelado) return;
          if (!(erro instanceof ErroApi)) {
            setFase("instalando");
            return;
          }
          seguidos += 1;
          if (seguidos < ERROS_SEGUIDOS) return;
          const motivo = erro.mensagem.replace(/\.$/, "");
          aplicar({ fase: "erro", baixado: 0, total: 0, mensagem: motivo });
        },
      );
    }, intervaloMs);
    return () => {
      cancelado = true;
      clearInterval(id);
    };
  }, [fase, intervaloMs]);

  // O app novo sobe na mesma porta: quando responde na versão nova, a página recarrega.
  const esperando = fase === "instalando" || fase === "demorou";
  const versaoNova = info?.nova?.versao;
  useEffect(() => {
    if (!esperando || versaoNova === undefined) return;
    let cancelado = false;
    const id = setInterval(() => {
      versaoNoAr().then(
        (versao) => {
          if (cancelado || versao !== versaoNova) return;
          cancelado = true;
          clearInterval(id);
          recarregarRef.current();
        },
        () => {},
      );
    }, intervaloMs);
    const demora = setTimeout(() => setFase("demorou"), limiteMs);
    return () => {
      cancelado = true;
      clearInterval(id);
      clearTimeout(demora);
    };
  }, [esperando, versaoNova, intervaloMs, limiteMs]);

  // Só o aviso e o erro se fecham: durante o download e a instalação não há o que cancelar.
  const fechavel = fase === "aviso" || fase === "erro";
  useEffect(() => {
    if (!fechavel) return;
    function aoTeclar(evento: KeyboardEvent) {
      if (evento.key === "Escape") setFase("fechado");
    }
    document.addEventListener("keydown", aoTeclar);
    return () => document.removeEventListener("keydown", aoTeclar);
  }, [fechavel]);

  useEffect(() => {
    (principal.current ?? janela.current)?.focus();
  }, [fase]);

  async function atualizar() {
    try {
      aplicar(await iniciarAtualizacao());
    } catch {
      aplicar({ fase: "erro", baixado: 0, total: 0, mensagem: "o app não respondeu" });
    }
  }

  if (fase === "fechado" || info === null || info.nova === null) return null;
  const { versao, novidades, tamanho } = info.nova;
  const mostradas = novidades.slice(0, MAX_NOVIDADES);
  const restantes = novidades.length - mostradas.length;
  const baixado = estado?.baixado ?? 0;
  const total = estado !== null && estado.total > 0 ? estado.total : tamanho;

  return (
    <div className="veu">
      <div
        ref={janela}
        role="dialog"
        aria-modal="true"
        aria-labelledby="aviso-versao-titulo"
        className="janela-aviso"
        tabIndex={-1}
      >
        <h2 id="aviso-versao-titulo">{`Versão nova do app: ${versao}`}</h2>
        {fase === "aviso" && (
          <>
            <p>{`Você está usando a ${info.atual}. O que mudou:`}</p>
            <ul>
              {mostradas.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
            {restantes > 0 && <p className="secundario">{`e mais ${restantes}`}</p>}
            <div className="acoes">
              <button
                type="button"
                ref={principal}
                className="botao-principal"
                onClick={() => void atualizar()}
              >
                Atualizar
              </button>
              <button type="button" onClick={() => setFase("fechado")}>
                Agora não
              </button>
            </div>
          </>
        )}
        {fase === "baixando" && (
          <>
            <p>{`Baixando a versão nova: ${emMb(baixado)} de ${emMb(total)} MB`}</p>
            <progress value={baixado} max={total} aria-label="Andamento do download" />
          </>
        )}
        {(fase === "instalando" || fase === "demorou") && (
          <p>Instalando. O app fecha e abre de novo sozinho, em menos de um minuto.</p>
        )}
        {fase === "demorou" && <p>Se o app não abrir sozinho, abra pelo atalho Painel de Opções.</p>}
        {fase === "erro" && (
          <>
            <p>
              {`Não deu para baixar a versão nova: ${estado?.mensagem ?? ""}. ` +
                `O app continua na versão ${info.atual}.`}
            </p>
            <div className="acoes">
              <button
                type="button"
                ref={principal}
                className="botao-principal"
                onClick={() => void atualizar()}
              >
                Tentar de novo
              </button>
              <button type="button" onClick={() => setFase("fechado")}>
                Fechar
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

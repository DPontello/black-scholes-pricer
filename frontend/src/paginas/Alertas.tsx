import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  type Alerta,
  type Alertas as AlertasDados,
  dispensarAlerta,
  lerAlertas,
  lerRolagem,
  restaurarAlertas,
} from "../api/alertas";
import type { EstadoAoVivo } from "../api/aoVivo";
import { definirLimitesAlertas, ErroApi, type Perfil } from "../api/cliente";
import { formatarData, formatarDiasUteis, formatarReais } from "../formatacao";

const FONTES = { ao_vivo: null, atrasado: "com preços atrasados", fim_de_dia: "pelo fim de dia (B3)" };

type Props = { aoVivo: EstadoAoVivo; perfil: Perfil; onPerfil: (perfil: Perfil) => void };

function mensagem(erro: unknown, padrao: string): string {
  return erro instanceof ErroApi ? erro.mensagem : padrao;
}

function prazo(dias: number | null): string {
  if (dias === null) return "";
  return dias === 0 ? "vence hoje" : `vence em ${formatarDiasUteis(dias)}`;
}

export function frase(alerta: Alerta): string {
  const serie = alerta.ticker ?? "";
  switch (alerta.tipo) {
    case "exercicio_a_registrar":
      return `${serie} venceu no dinheiro: registre o exercício ou a atribuição`;
    case "aguardando_fechamento":
      return `${serie} venceu: aguardando o fechamento do pregão (COTAHIST)`;
    case "vencimento_proximo":
      return `${serie} ${prazo(alerta.dias_uteis)} (${formatarData(alerta.vencimento ?? "")})`;
    case "risco_de_exercicio": {
      const onde = alerta.dentro_do_dinheiro ? "dentro do dinheiro" : "perto do strike";
      return `${serie} vendida ${onde}: risco de exercício, ${prazo(alerta.dias_uteis)}`;
    }
    case "stop":
      return `Stop: resultado ${formatarReais(alerta.total ?? 0)} (limite ${formatarReais(-(alerta.limite ?? 0))})`;
    case "alvo":
      return `Alvo: resultado ${formatarReais(alerta.total ?? 0)} (alvo ${formatarReais(alerta.limite ?? 0)})`;
  }
}

// Agrupa por operação, na ordem do primeiro alerta de cada uma (a lista já vem por gravidade).
function porOperacao(alertas: Alerta[]): Alerta[][] {
  const grupos = new Map<string, Alerta[]>();
  for (const alerta of alertas) grupos.set(alerta.operacao, [...(grupos.get(alerta.operacao) ?? []), alerta]);
  return [...grupos.values()];
}

export function Alertas({ aoVivo, perfil, onPerfil }: Props) {
  const navegar = useNavigate();
  const [dados, setDados] = useState<AlertasDados | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function recarregar() {
    lerAlertas()
      .then((novos) => {
        setDados(novos);
        setErro(null);
      })
      .catch((e: unknown) => setErro(mensagem(e, "Não foi possível ler os alertas.")));
  }

  useEffect(recarregar, []);

  // A mais recente vence, como na Carteira: a do WebSocket a cada mudança.
  useEffect(() => {
    if (aoVivo.alertas !== null) setDados(aoVivo.alertas);
  }, [aoVivo.alertas]);

  function dispensar(chave: string) {
    dispensarAlerta(chave)
      .then(recarregar)
      .catch((e: unknown) => setErro(mensagem(e, "Não foi possível dispensar o alerta.")));
  }

  function restaurar() {
    restaurarAlertas()
      .then(recarregar)
      .catch((e: unknown) => setErro(mensagem(e, "Não foi possível mostrar os dispensados.")));
  }

  function rolar(operacao: string) {
    lerRolagem(operacao)
      .then((rolagem) =>
        navegar(`/montador?ativo=${encodeURIComponent(rolagem.ativo)}`, {
          state: { pedido: rolagem.pedido ?? undefined, rolagem },
        }),
      )
      .catch((e: unknown) => setErro(mensagem(e, "Não foi possível montar a rolagem.")));
  }

  const indisponivel = aoVivo.alertasIndisponiveis?.mensagem ?? erro;
  const fonte = dados === null ? null : FONTES[dados.fonte];

  return (
    <section className="pagina-alertas">
      <h1>Alertas</h1>
      {fonte !== null && <p className="secundario">{fonte}</p>}
      {indisponivel !== null && (
        <p className="erro" role="alert">
          {indisponivel}
        </p>
      )}
      {dados !== null && dados.alertas.length === 0 && (
        <p className="secundario">Nenhum alerta agora.</p>
      )}
      {dados !== null &&
        porOperacao(dados.alertas).map((grupo) => {
          const primeiro = grupo[0] as Alerta;
          return (
            <article key={primeiro.operacao} className="grupo-alertas" aria-label={primeiro.nome}>
              <h2>
                {primeiro.nome} <span className="secundario">{primeiro.ativo}</span>
              </h2>
              <ul>
                {grupo.map((alerta) => (
                  <li key={alerta.chave} className={`alerta ${alerta.tipo}`}>
                    <span>{frase(alerta)}</span>
                    <button type="button" onClick={() => dispensar(alerta.chave)}>
                      Dispensar
                    </button>
                  </li>
                ))}
              </ul>
              <div className="acoes-alerta">
                <button
                  type="button"
                  onClick={() => navegar(`/carteira?operacao=${encodeURIComponent(primeiro.operacao)}`)}
                >
                  Abrir na Carteira
                </button>
                {grupo.some((a) => a.pode_rolar) && (
                  <button type="button" onClick={() => rolar(primeiro.operacao)}>
                    Rolar
                  </button>
                )}
              </div>
            </article>
          );
        })}
      {dados !== null && dados.dispensados > 0 && (
        <button type="button" className="link" onClick={restaurar}>
          Mostrar dispensados ({dados.dispensados})
        </button>
      )}
      <Ajustes perfil={perfil} onPerfil={onPerfil} />
    </section>
  );
}

function Ajustes({ perfil, onPerfil }: { perfil: Perfil; onPerfil: (perfil: Perfil) => void }) {
  const [dias, setDias] = useState(String(perfil.alertas.dias_vencimento));
  // Na tela em %, na API em fração: 2 ↔ 0,02.
  const [distancia, setDistancia] = useState(String(perfil.alertas.distancia_strike * 100));
  const [estado, setEstado] = useState<string | null>(null);

  function gravar(evento: React.FormEvent) {
    evento.preventDefault();
    definirLimitesAlertas({ dias_vencimento: Number(dias), distancia_strike: Number(distancia) / 100 })
      .then((novo) => {
        onPerfil(novo);
        setEstado("Limites gravados no perfil.");
      })
      .catch((e: unknown) => setEstado(mensagem(e, "Não foi possível gravar os limites.")));
  }

  return (
    <form className="ajustes-alertas" onSubmit={gravar} aria-label="Limites dos alertas">
      <h2>Limites</h2>
      <label>
        Avisar o vencimento a
        <input
          type="number"
          min={0}
          max={60}
          step={1}
          value={dias}
          onChange={(e) => setDias(e.target.value)}
        />
        dias úteis ou menos
      </label>
      <label>
        Risco de exercício a menos de
        <input
          type="number"
          min={0}
          max={20}
          step={0.5}
          value={distancia}
          onChange={(e) => setDistancia(e.target.value)}
        />
        % do strike
      </label>
      <button type="submit">Gravar</button>
      {estado !== null && <p className="secundario">{estado}</p>}
    </form>
  );
}

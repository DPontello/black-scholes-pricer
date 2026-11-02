import { Fragment, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import type { EstadoAoVivo } from "../api/aoVivo";
import {
  type AvisoVencimento,
  type Carteira as CarteiraDados,
  type Evento,
  lerCarteira,
  lerHistorico,
  type Marca,
  type OperacaoCarteira,
  type PernaCarteira,
  type RascunhoOperacao,
  rascunhoVazio,
} from "../api/carteira";
import { ErroApi } from "../api/cliente";
import { AdicionarAcoes } from "../componentes/AdicionarAcoes";
import { DialogoEncerrar } from "../componentes/DialogoEncerrar";
import { DialogoExercicio } from "../componentes/DialogoExercicio";
import { FormOperacao } from "../componentes/FormOperacao";
import { formatarData, formatarPreco, hojeNaB3 } from "../formatacao";

const FONTES = { ao_vivo: "ao vivo (Tryd)", atrasado: "atrasado", fim_de_dia: "fim de dia (B3)" };
const EVENTOS: Record<Evento["tipo"], string> = {
  abertura: "abertura",
  encerramento: "encerramento",
  exercicio: "exercício",
  atribuicao: "atribuição",
  po: "virou pó",
  transferencia: "ações usadas por outra operação",
};

type Painel =
  | { tipo: "registrar"; inicial: RascunhoOperacao }
  | { tipo: "acoes" }
  | { tipo: "encerrar"; operacao: OperacaoCarteira }
  | { tipo: "exercicio"; operacao: OperacaoCarteira; perna?: number }
  | null;

type Props = { aoVivo: EstadoAoVivo };

function sinal(valor: number | null): string {
  if (valor === null) return "";
  return valor > 0 ? "alta" : valor < 0 ? "baixa" : "";
}

function descricao(perna: PernaCarteira): string {
  if (perna.tipo === "acao") return perna.origem === "carteira" ? "ação da carteira" : "ação";
  const estilo = perna.estilo === "american" ? " · americana" : "";
  return `${perna.tipo} ${formatarPreco(perna.strike)} · vence ${formatarData(perna.vencimento ?? "")}${estilo}`;
}

export function PrecoDeZerar({ marca }: { marca: Marca | null }) {
  if (marca === null) return <>—</>;
  if (marca.preco !== null) return <>{formatarPreco(marca.preco)}</>;
  return (
    <span title={marca.motivo ?? undefined}>
      —{" "}
      {marca.teorico !== null && (
        <span className="teorico">teórico {formatarPreco(marca.teorico)}</span>
      )}{" "}
      <span className="secundario">{marca.motivo}</span>
    </span>
  );
}

function Pernas({ operacao }: { operacao: OperacaoCarteira }) {
  return (
    <table className="tabela-pernas-carteira">
      <thead>
        <tr>
          <th>Perna</th>
          <th>Lado</th>
          <th className="num">Quantidade</th>
          <th className="num">Preço médio</th>
          <th className="num">Preço de zerar</th>
          <th className="num">Não realizado</th>
          <th className="num">Realizado</th>
        </tr>
      </thead>
      <tbody>
        {operacao.pernas.map((perna) => (
          <tr key={perna.indice}>
            <td>
              {perna.ticker} <span className="secundario">{descricao(perna)}</span>
            </td>
            <td className={perna.lado ?? ""}>{perna.lado ?? "zerada"}</td>
            <td className="num">{perna.quantidade}</td>
            <td className="num">{perna.quantidade > 0 ? formatarPreco(perna.preco_medio) : "—"}</td>
            <td className="num">
              <PrecoDeZerar marca={perna.marca} />
            </td>
            <td className={`num ${sinal(perna.marca?.nao_realizado ?? null)}`}>
              {formatarPreco(perna.marca?.nao_realizado ?? null)}
            </td>
            <td className={`num ${sinal(perna.realizado)}`}>{formatarPreco(perna.realizado)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Eventos({ operacao }: { operacao: OperacaoCarteira }) {
  return (
    <ol className="eventos">
      {operacao.eventos.map((evento, i) => (
        <li key={i}>
          {formatarData(evento.data)} · {EVENTOS[evento.tipo]} · {operacao.pernas[evento.perna]?.ticker}
          {evento.lado !== null && ` · ${evento.lado}`}
          {evento.quantidade !== null && ` · ${evento.quantidade}`}
          {evento.preco !== null && ` a ${formatarPreco(evento.preco)}`}
          {evento.custo_medio !== null && ` (custo médio ${formatarPreco(evento.custo_medio)})`}
        </li>
      ))}
    </ol>
  );
}

function Aviso({
  aviso,
  onRegistrar,
}: {
  aviso: AvisoVencimento;
  onRegistrar: () => void;
}) {
  const quando = formatarData(aviso.vencimento);
  if (aviso.situacao === "aguardando_fechamento")
    return (
      <li className="aviso">
        {aviso.ticker} venceu em {quando}: aguardando o fechamento do pregão (importe o COTAHIST do
        dia).
      </li>
    );
  return (
    <li className="aviso">
      {aviso.ticker} venceu em {quando} no dinheiro ou dentro: registre o exercício ou a atribuição.{" "}
      <button type="button" onClick={onRegistrar}>
        Registrar
      </button>
    </li>
  );
}

function Totais({ carteira }: { carteira: CarteiraDados }) {
  const marcados = carteira.totais.filter((t) => t.marca.nao_realizado !== null);
  const total = marcados.reduce((soma, t) => soma + (t.marca.nao_realizado ?? 0), 0);
  const semPreco = carteira.totais.length - marcados.length;
  return (
    <table className="tabela-totais">
      <caption>Total por ativo</caption>
      <thead>
        <tr>
          <th>Ativo</th>
          <th>Lado</th>
          <th className="num">Quantidade</th>
          <th className="num">Preço médio</th>
          <th className="num">Preço de zerar</th>
          <th className="num">Não realizado</th>
        </tr>
      </thead>
      <tbody>
        {carteira.totais.map((t) => (
          <tr key={`${t.ticker}-${t.lado}`}>
            <td>{t.ticker}</td>
            <td className={t.lado}>{t.lado}</td>
            <td className="num">{t.quantidade}</td>
            <td className="num">{formatarPreco(t.preco_medio)}</td>
            <td className="num">
              <PrecoDeZerar marca={t.marca} />
            </td>
            <td className={`num ${sinal(t.marca.nao_realizado)}`}>
              {formatarPreco(t.marca.nao_realizado)}
            </td>
          </tr>
        ))}
      </tbody>
      <tfoot>
        <tr>
          <th colSpan={5}>
            Total executável
            {semPreco > 0 && (
              <span className="secundario"> · {semPreco} sem preço de zerar, fora do total</span>
            )}
          </th>
          <td className={`num ${sinal(total)}`}>{formatarPreco(total)}</td>
        </tr>
      </tfoot>
    </table>
  );
}

export function Carteira({ aoVivo }: Props) {
  const local = useLocation();
  const navegar = useNavigate();
  const doMontador = (local.state as { registro?: RascunhoOperacao } | null)?.registro;
  const [carteira, setCarteira] = useState<CarteiraDados | null>(null);
  const [historico, setHistorico] = useState<OperacaoCarteira[] | null>(null);
  const [aba, setAba] = useState<"abertas" | "historico">("abertas");
  const [painel, setPainel] = useState<Painel>(
    doMontador === undefined ? null : { tipo: "registrar", inicial: doMontador },
  );
  const [abertas, setAbertas] = useState<ReadonlySet<string>>(new Set());
  const [comEventos, setComEventos] = useState<ReadonlySet<string>>(new Set());
  const [erro, setErro] = useState<string | null>(null);

  function recarregar() {
    lerCarteira()
      .then((nova) => {
        setCarteira(nova);
        setErro(null);
      })
      .catch((e: unknown) =>
        setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível ler a carteira."),
      );
    if (aba === "historico") lerHistorico().then(setHistorico).catch(() => setHistorico(null));
  }

  useEffect(recarregar, []);

  // A mais recente vence: a do WebSocket a cada mudança, a da API depois de uma gravação.
  useEffect(() => {
    if (aoVivo.carteira !== null) setCarteira(aoVivo.carteira);
  }, [aoVivo.carteira]);

  useEffect(() => {
    if (aba === "historico") lerHistorico().then(setHistorico).catch(() => setHistorico(null));
  }, [aba]);

  function feito() {
    setPainel(null);
    if (doMontador !== undefined) navegar(".", { replace: true, state: null });
    recarregar();
  }

  function alternar(conjunto: ReadonlySet<string>, id: string): ReadonlySet<string> {
    const novo = new Set(conjunto);
    if (novo.has(id)) novo.delete(id);
    else novo.add(id);
    return novo;
  }

  const indisponivel = aoVivo.carteiraIndisponivel?.mensagem ?? erro;
  const porId = new Map((carteira?.operacoes ?? []).map((o) => [o.id, o]));

  return (
    <section className="pagina-carteira">
      <h1>Carteira</h1>
      <div className="acoes-montador">
        <button
          type="button"
          onClick={() => setPainel({ tipo: "registrar", inicial: rascunhoVazio(hojeNaB3()) })}
        >
          Registrar operação
        </button>
        <button type="button" onClick={() => setPainel({ tipo: "acoes" })}>
          Adicionar ações
        </button>
        {carteira !== null && (
          <span className="secundario">preços de zerar {FONTES[carteira.fonte]}</span>
        )}
      </div>
      {painel?.tipo === "registrar" && (
        <FormOperacao inicial={painel.inicial} onRegistrada={feito} onCancelar={feito} />
      )}
      {painel?.tipo === "acoes" && <AdicionarAcoes onFeito={feito} onCancelar={() => setPainel(null)} />}
      {painel?.tipo === "encerrar" && (
        <DialogoEncerrar operacao={painel.operacao} onFeito={feito} onCancelar={() => setPainel(null)} />
      )}
      {painel?.tipo === "exercicio" && (
        <DialogoExercicio
          operacao={painel.operacao}
          perna={painel.perna}
          onFeito={feito}
          onCancelar={() => setPainel(null)}
        />
      )}
      {indisponivel !== null && carteira === null && (
        <p className="erro" role="alert">
          {indisponivel}
        </p>
      )}
      {carteira !== null && carteira.avisos.length > 0 && (
        <ul className="avisos" aria-label="Avisos de vencimento">
          {carteira.avisos.map((aviso) => {
            const operacao = porId.get(aviso.operacao);
            return (
              <Aviso
                key={`${aviso.operacao}-${aviso.perna}`}
                aviso={aviso}
                onRegistrar={() =>
                  operacao !== undefined &&
                  setPainel({ tipo: "exercicio", operacao, perna: aviso.perna })
                }
              />
            );
          })}
        </ul>
      )}
      {carteira !== null && carteira.ilegiveis.length > 0 && (
        <ul className="avisos">
          {carteira.ilegiveis.map((i) => (
            <li key={i.arquivo} className="erro">
              Arquivo ilegível, não apagado nem sobrescrito: {i.arquivo} ({i.motivo})
            </li>
          ))}
        </ul>
      )}
      <div className="abas" role="tablist">
        <button type="button" role="tab" aria-selected={aba === "abertas"} onClick={() => setAba("abertas")}>
          Abertas
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={aba === "historico"}
          onClick={() => setAba("historico")}
        >
          Histórico
        </button>
      </div>
      {aba === "abertas" && carteira !== null && (
        <>
          {carteira.operacoes.length === 0 ? (
            <p className="secundario">Nenhuma operação aberta neste perfil.</p>
          ) : (
            <table className="tabela-operacoes">
              <thead>
                <tr>
                  <th>Operação</th>
                  <th>Desde</th>
                  <th className="num">Realizado</th>
                  <th className="num">Não realizado</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {carteira.operacoes.map((operacao) => {
                  const aberta = abertas.has(operacao.id);
                  const temOpcao = operacao.pernas.some((p) => p.tipo !== "acao" && p.quantidade > 0);
                  return (
                    <Fragment key={operacao.id}>
                      <tr>
                        <td>
                          <button
                            type="button"
                            className="link"
                            aria-expanded={aberta}
                            onClick={() => setAbertas(alternar(abertas, operacao.id))}
                          >
                            {aberta ? "▾" : "▸"} {operacao.nome}
                          </button>{" "}
                          <span className="secundario">{operacao.ativo}</span>
                        </td>
                        <td>{formatarData(operacao.criada_em)}</td>
                        <td className={`num ${sinal(operacao.realizado)}`}>
                          {formatarPreco(operacao.realizado)}
                        </td>
                        <td className={`num ${sinal(operacao.nao_realizado)}`}>
                          {operacao.nao_realizado === null ? (
                            <span className="secundario">sem preço de zerar</span>
                          ) : (
                            formatarPreco(operacao.nao_realizado)
                          )}
                        </td>
                        <td className="acoes-operacao">
                          <button type="button" onClick={() => setPainel({ tipo: "encerrar", operacao })}>
                            Encerrar
                          </button>
                          {temOpcao && (
                            <button
                              type="button"
                              onClick={() => setPainel({ tipo: "exercicio", operacao })}
                            >
                              Exercício
                            </button>
                          )}
                          <button
                            type="button"
                            aria-pressed={comEventos.has(operacao.id)}
                            onClick={() => setComEventos(alternar(comEventos, operacao.id))}
                          >
                            Eventos
                          </button>
                        </td>
                      </tr>
                      {(aberta || comEventos.has(operacao.id)) && (
                        <tr className="detalhe-operacao">
                          <td colSpan={5}>
                            {aberta && <Pernas operacao={operacao} />}
                            {comEventos.has(operacao.id) && <Eventos operacao={operacao} />}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          )}
          {carteira.totais.length > 0 && <Totais carteira={carteira} />}
        </>
      )}
      {aba === "historico" &&
        (historico === null || historico.length === 0 ? (
          <p className="secundario">Nenhuma operação encerrada.</p>
        ) : (
          <table className="tabela-operacoes">
            <thead>
              <tr>
                <th>Operação</th>
                <th>Desde</th>
                <th className="num">Resultado realizado</th>
              </tr>
            </thead>
            <tbody>
              {historico.map((operacao) => (
                <tr key={operacao.id}>
                  <td>
                    {operacao.nome} <span className="secundario">{operacao.ativo}</span>
                    <Eventos operacao={operacao} />
                  </td>
                  <td>{formatarData(operacao.criada_em)}</td>
                  <td className={`num ${sinal(operacao.realizado)}`}>
                    {formatarPreco(operacao.realizado)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ))}
    </section>
  );
}

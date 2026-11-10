import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import type { Rolagem } from "../api/alertas";
import type { EstadoAoVivo, SeguirCadeia, Serie } from "../api/aoVivo";
import { rascunhoDaAnalise } from "../api/carteira";
import { ErroApi } from "../api/cliente";
import {
  type Analise,
  analisar,
  apagarSimulacao,
  listarModelos,
  listarSimulacoes,
  type Modelo,
  type PedidoAnalise,
  salvarSimulacao,
  type Simulacao,
  sugerir,
} from "../api/montador";
import { CartaoResultado } from "../componentes/CartaoResultado";
import { FaixaRolagem } from "../componentes/FaixaRolagem";
import { TabelaCadeia } from "../componentes/TabelaCadeia";
import { TabelaPernas } from "../componentes/TabelaPernas";
import { formatarData, formatarInstante, hojeNaB3 } from "../formatacao";

const FAMILIAS: Record<Modelo["familia"], string> = {
  renda: "Renda",
  direcionais: "Direcionais",
  volatilidade: "Volatilidade",
  protecao: "Proteção",
};
// Espera a digitação parar antes de pedir a análise de novo.
const ESPERA_MS = 300;

type Props = { aoVivo: EstadoAoVivo; seguirCadeia: SeguirCadeia };

function vazio(ativo: string | null): PedidoAnalise {
  return { ativo: ativo ?? "", pernas: [], acao: null, modelo: null };
}

function mensagem(erro: unknown, padrao: string): string {
  return erro instanceof ErroApi ? erro.mensagem : padrao;
}

export function Montador({ aoVivo, seguirCadeia }: Props) {
  const [busca, setBusca] = useSearchParams();
  const navegar = useNavigate();
  const ativo = busca.get("ativo") ?? aoVivo.cotacoes[0]?.ativo ?? null;
  // O book (e a rolagem dos Alertas) abre um item aqui pelo estado da rota; o montador reprecifica
  // pela cadeia do momento.
  const estadoDaRota = useLocation().state as {
    pedido?: PedidoAnalise;
    vencimento?: string;
    rolagem?: Rolagem;
  } | null;
  const doBook = estadoDaRota?.pedido ?? null;
  const [rolagem, setRolagem] = useState<Rolagem | null>(estadoDaRota?.rolagem ?? null);
  // Ticker → vencimento das séries que a cadeia do ativo já trouxe.
  const [datasDasSeries, setDatasDasSeries] = useState<Map<string, string>>(() => new Map());
  const [pedido, setPedido] = useState<PedidoAnalise>(doBook ?? vazio(ativo));
  const [analise, setAnalise] = useState<Analise | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [simulacoes, setSimulacoes] = useState<Simulacao[]>([]);
  const [nome, setNome] = useState("");
  const pendente = useRef<PedidoAnalise | null>(doBook);
  const resultado = useRef<HTMLDivElement>(null);
  // De fora da cadeia (book, modelo pronto, simulação salva); o + e a tabela de pernas não contam.
  const [chegadas, setChegadas] = useState(0);
  const [respostas, setRespostas] = useState(0);
  const rolarPara = useRef<PedidoAnalise | null>(null);
  // O Aprender abre o Montador com `?modelo=`: o modelo entra uma vez só, quando a cadeia chega.
  const [modeloDoEndereco, setModeloDoEndereco] = useState(busca.get("modelo"));

  useEffect(() => {
    if (pendente.current !== null) setChegadas((n) => n + 1);
    setPedido(pendente.current ?? vazio(ativo));
    pendente.current = null;
    setDatasDasSeries(new Map());
    setAnalise(null);
  }, [ativo]);

  useEffect(() => () => seguirCadeia(null), [seguirCadeia]);

  function recarregarSimulacoes() {
    listarSimulacoes()
      .then((lista) => setSimulacoes(lista.simulacoes))
      .catch(() => setSimulacoes([]));
  }

  useEffect(() => {
    listarModelos()
      .then(setModelos)
      .catch(() => setModelos([]));
    recarregarSimulacoes();
  }, []);

  // Cada chegada marca o pedido novo; a rolagem espera a análise dele (ou o erro), com a página já alta.
  useEffect(() => {
    if (chegadas > 0) rolarPara.current = pedido;
  }, [chegadas]);

  // Abaixo de 1280 px o resultado fica sob a cadeia, e o clique pareceria não fazer nada.
  useEffect(() => {
    if (rolarPara.current !== pedido || resultado.current === null) return;
    rolarPara.current = null;
    if (resultado.current.getBoundingClientRect().top > window.innerHeight / 2)
      resultado.current.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [respostas]);

  const horaDaCadeia = aoVivo.cadeia?.hora;
  useEffect(() => {
    if (pedido.pernas.length === 0 && pedido.acao === null) {
      setAnalise(null);
      return;
    }
    let cancelado = false;
    const espera = setTimeout(() => {
      analisar(pedido)
        .then((nova) => {
          if (cancelado) return;
          setAnalise(nova);
          setErro(null);
          setRespostas((n) => n + 1);
        })
        .catch((e: unknown) => {
          if (cancelado) return;
          setAnalise(null);
          setErro(mensagem(e, "Não foi possível analisar a estrutura."));
          setRespostas((n) => n + 1);
        });
    }, ESPERA_MS);
    return () => {
      cancelado = true;
      clearTimeout(espera);
    };
  }, [pedido, horaDaCadeia]);

  const cadeiaDoAtivo = aoVivo.cadeia?.ativo === ativo ? aoVivo.cadeia : null;
  const disponiveis = cadeiaDoAtivo?.disponiveis ?? [];
  const [vencimentoEscolhido, setVencimentoEscolhido] = useState<string | null>(
    estadoDaRota?.vencimento ?? estadoDaRota?.rolagem?.vencimento_novo ?? null,
  );
  // Sem escolha, o primeiro mensal: a semanal de poucos dias raramente é o que o modelo quer.
  const vencimento =
    vencimentoEscolhido !== null && disponiveis.some((d) => d.data === vencimentoEscolhido)
      ? vencimentoEscolhido
      : (disponiveis.find((d) => d.semanal === false) ?? disponiveis[0])?.data;
  // O vencimento escolhido pode ainda não ter chegado na cadeia, ou ter chegado sem séries enquanto o
  // Tryd carrega: o backend responderia "sem séries".
  const vencimentoNaCadeia =
    cadeiaDoAtivo?.vencimentos.some((v) => v.data === vencimento && v.series.length > 0) ?? false;

  useEffect(() => {
    if (cadeiaDoAtivo === null) return;
    setDatasDasSeries((atual) => {
      const novas = cadeiaDoAtivo.vencimentos.flatMap((v) =>
        v.series.filter((s) => !atual.has(s.ticker)).map((s) => [s.ticker, v.data] as const),
      );
      return novas.length === 0 ? atual : new Map([...atual, ...novas]);
    });
  }, [cadeiaDoAtivo]);

  // O Tryd só assina as séries dos vencimentos pedidos: o das pernas postas segue junto com o do seletor.
  const acompanhados =
    vencimento === undefined
      ? null
      : [
          ...new Set([vencimento, ...pedido.pernas.flatMap((p) => datasDasSeries.get(p.ticker) ?? [])]),
        ].sort();
  const chaveAcompanhados = acompanhados?.join(",");
  useEffect(() => {
    seguirCadeia(ativo, acompanhados);
  }, [ativo, chaveAcompanhados, seguirCadeia]);

  const nomeDoModeloDoEndereco = modelos.find((m) => m.chave === modeloDoEndereco)?.nome;

  useEffect(() => {
    if (modeloDoEndereco === null || modelos.length === 0) return;
    const conhecido = modelos.some((m) => m.chave === modeloDoEndereco);
    if (conhecido && (ativo === null || !vencimentoNaCadeia)) return;
    setModeloDoEndereco(null);
    setBusca(
      (atual) => {
        const nova = new URLSearchParams(atual);
        nova.delete("modelo");
        return nova;
      },
      { replace: true },
    );
    if (conhecido) void escolherModelo(modeloDoEndereco);
  }, [modeloDoEndereco, modelos, ativo, vencimento, vencimentoNaCadeia]);

  async function escolherModelo(chave: string) {
    if (ativo === null || vencimento === undefined || !vencimentoNaCadeia) return;
    try {
      setPedido(await sugerir(ativo, chave, vencimento));
      setChegadas((n) => n + 1);
      setErro(null);
    } catch (e) {
      setErro(mensagem(e, "Não foi possível montar o modelo com esta cadeia."));
    }
  }

  function porSerie(serie: Serie) {
    setPedido((atual) => ({
      ...atual,
      modelo: null,
      pernas: [...atual.pernas, { ticker: serie.ticker, lado: "compra", quantidade: 100, preco: null }],
    }));
  }

  async function salvar() {
    try {
      await salvarSimulacao(nome, pedido);
      setNome("");
      recarregarSimulacoes();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível salvar a simulação."));
    }
  }

  function abrir(simulacao: Simulacao) {
    if (simulacao.pedido.ativo === ativo) {
      // Cópia: o mesmo objeto já carregado faria o React ignorar o set, sem análise nem rolagem.
      setPedido({ ...simulacao.pedido });
      setChegadas((n) => n + 1);
      return;
    }
    pendente.current = simulacao.pedido;
    setBusca({ ativo: simulacao.pedido.ativo });
  }

  async function apagar(simulacao: Simulacao) {
    if (!window.confirm(`Apagar a simulação "${simulacao.nome}"?`)) return;
    try {
      await apagarSimulacao(simulacao.id);
      recarregarSimulacoes();
    } catch (e) {
      setErro(mensagem(e, "Não foi possível apagar a simulação."));
    }
  }

  const ativos = [...new Set([...(ativo === null ? [] : [ativo]), ...aoVivo.cotacoes.map((c) => c.ativo)])];
  const vazia = pedido.pernas.length === 0 && pedido.acao === null;

  return (
    <section className="pagina-montador">
      <h1>Montador</h1>
      {rolagem !== null && (
        <FaixaRolagem rolagem={rolagem} analise={analise} onFechar={() => setRolagem(null)} />
      )}
      <div className="montador-topo">
        <label>
          Ativo{" "}
          <select
            value={ativo ?? ""}
            onChange={(e) => setBusca({ ativo: e.target.value })}
            aria-label="Ativo do montador"
          >
            {ativos.length === 0 && <option value="">adicione ativos no Mercado</option>}
            {ativos.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </select>
        </label>
        <label>
          Vencimento{" "}
          <select
            aria-label="Vencimento"
            value={vencimento ?? ""}
            disabled={disponiveis.length === 0}
            onChange={(e) => setVencimentoEscolhido(e.target.value)}
          >
            {disponiveis.map((d) => (
              <option key={d.data} value={d.data}>
                {`${formatarData(d.data).slice(0, 5)}${d.semanal ? " S" : ""}`}
              </option>
            ))}
          </select>
        </label>
        <label>
          Modelo pronto{" "}
          <select
            aria-label="Modelo pronto"
            value=""
            disabled={!vencimentoNaCadeia}
            onChange={(e) => void escolherModelo(e.target.value)}
          >
            <option value="">{vencimentoNaCadeia ? "escolha" : "aguardando a cadeia"}</option>
            {Object.entries(FAMILIAS).map(([familia, rotulo]) => (
              <optgroup key={familia} label={rotulo}>
                {modelos
                  .filter((m) => m.familia === familia)
                  .map((m) => (
                    <option key={m.chave} value={m.chave}>
                      {m.nome}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={pedido.acao !== null || ativo === null}
          onClick={() =>
            setPedido((atual) => ({
              ...atual,
              acao: { lado: "compra", quantidade: 100, origem: "compra", preco: null },
            }))
          }
        >
          + ação
        </button>
        <button type="button" disabled={vazia} onClick={() => setPedido(vazio(ativo))}>
          Limpar
        </button>
      </div>
      {nomeDoModeloDoEndereco !== undefined && (
        <p className="secundario" role="status">
          {nomeDoModeloDoEndereco}: aguardando a cadeia…
        </p>
      )}
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}{" "}
          {pedido.modelo !== null && (
            <button type="button" onClick={() => setPedido({ ...pedido, modelo: null })}>
              Montar sem o modelo
            </button>
          )}
        </p>
      )}
      <div className="montador-corpo">
        <div className="cartao montador-cadeia">
          <TabelaCadeia
            ativo={ativo}
            cadeia={aoVivo.cadeia}
            indisponivel={aoVivo.cadeiaIndisponivel}
            enxuta
            vencimento={vencimento}
            onEscolherSerie={porSerie}
          />
        </div>
        <div className="montador-resultado" ref={resultado}>
          {analise !== null && <CartaoResultado analise={analise} />}
          <section className="cartao cartao-pernas">
            <TabelaPernas pedido={pedido} analise={analise} onMudar={setPedido} />
            <div className="acoes-montador">
              <button
                type="button"
                className="botao-principal"
                disabled={vazia}
                onClick={() =>
                  navegar("/carteira", {
                    state: { registro: rascunhoDaAnalise(pedido, analise, hojeNaB3()) },
                  })
                }
              >
                Registrar como executada
              </button>
              <input
                aria-label="Nome da simulação"
                placeholder="nome da simulação"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
              />
              <button type="button" disabled={vazia || nome.trim() === ""} onClick={() => void salvar()}>
                Salvar simulação
              </button>
            </div>
          </section>
          {simulacoes.length > 0 && (
            <details className="simulacoes">
              <summary>{simulacoes.length} simulação(ões) salva(s)</summary>
              <ul>
                {simulacoes.map((s) => (
                  <li key={s.id}>
                    <button type="button" className="link" onClick={() => abrir(s)}>
                      {s.nome}
                    </button>{" "}
                    <span className="secundario">
                      {s.pedido.ativo} · {formatarInstante(s.criada_em)}
                    </span>{" "}
                    <button type="button" aria-label={`Apagar ${s.nome}`} onClick={() => void apagar(s)}>
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </section>
  );
}

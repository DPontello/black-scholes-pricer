import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { EstadoAoVivo, SeguirCadeia, Serie } from "../api/aoVivo";
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
import { GradeCenarios } from "../componentes/GradeCenarios";
import { GraficoPayoff } from "../componentes/GraficoPayoff";
import { ResumoEstrutura } from "../componentes/ResumoEstrutura";
import { TabelaCadeia } from "../componentes/TabelaCadeia";
import { TabelaPernas } from "../componentes/TabelaPernas";
import { formatarData, formatarInstante } from "../formatacao";

const FAMILIAS: Record<Modelo["familia"], string> = {
  renda: "Renda",
  direcionais: "Direcionais",
  volatilidade: "Volatilidade",
  protecao: "Proteção",
};
const FONTES = { ao_vivo: "ao vivo (Tryd)", atrasado: "atrasado", fim_de_dia: "fim de dia (B3)" };
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
  const ativo = busca.get("ativo") ?? aoVivo.cotacoes[0]?.ativo ?? null;
  const [vencimentos, setVencimentos] = useState<string[] | null>(null);
  const [pedido, setPedido] = useState<PedidoAnalise>(vazio(ativo));
  const [analise, setAnalise] = useState<Analise | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [simulacoes, setSimulacoes] = useState<Simulacao[]>([]);
  const [nome, setNome] = useState("");
  const pendente = useRef<PedidoAnalise | null>(null);

  useEffect(() => {
    setPedido(pendente.current ?? vazio(ativo));
    pendente.current = null;
    setVencimentos(null);
    setAnalise(null);
  }, [ativo]);

  useEffect(() => {
    seguirCadeia(ativo, vencimentos);
  }, [ativo, vencimentos, seguirCadeia]);
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
        })
        .catch((e: unknown) => {
          if (cancelado) return;
          setAnalise(null);
          setErro(mensagem(e, "Não foi possível analisar a estrutura."));
        });
    }, ESPERA_MS);
    return () => {
      cancelado = true;
      clearTimeout(espera);
    };
  }, [pedido, horaDaCadeia]);

  const cadeiaDoAtivo = aoVivo.cadeia?.ativo === ativo ? aoVivo.cadeia : null;
  const blocos = cadeiaDoAtivo?.vencimentos.map((v) => v.data) ?? [];
  const [vencimentoEscolhido, setVencimentoEscolhido] = useState<string | null>(null);
  // Sem escolha, o primeiro mensal: a semanal de poucos dias raramente é o que o modelo quer.
  const mensal = blocos.find(
    (data) => cadeiaDoAtivo?.disponiveis.find((d) => d.data === data)?.semanal === false,
  );
  const vencimentoDoModelo =
    vencimentoEscolhido !== null && blocos.includes(vencimentoEscolhido)
      ? vencimentoEscolhido
      : (mensal ?? blocos[0]);

  async function escolherModelo(chave: string) {
    if (ativo === null || vencimentoDoModelo === undefined) return;
    try {
      setPedido(await sugerir(ativo, chave, vencimentoDoModelo));
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
      setPedido(simulacao.pedido);
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
            aria-label="Vencimento do modelo"
            value={vencimentoDoModelo ?? ""}
            disabled={blocos.length === 0}
            onChange={(e) => setVencimentoEscolhido(e.target.value)}
          >
            {blocos.map((data) => (
              <option key={data} value={data}>
                {formatarData(data).slice(0, 5)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Modelo pronto{" "}
          <select
            aria-label="Modelo pronto"
            value=""
            disabled={vencimentoDoModelo === undefined}
            onChange={(e) => void escolherModelo(e.target.value)}
          >
            <option value="">
              {vencimentoDoModelo === undefined ? "aguardando a cadeia" : "escolha"}
            </option>
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
        <div className="montador-cadeia">
          <TabelaCadeia
            ativo={ativo}
            cadeia={aoVivo.cadeia}
            indisponivel={aoVivo.cadeiaIndisponivel}
            onVencimentos={setVencimentos}
            onEscolherSerie={porSerie}
          />
        </div>
        <div className="montador-resultado">
          <TabelaPernas pedido={pedido} analise={analise} onMudar={setPedido} />
          {analise !== null && (
            <>
              <h2>
                {analise.nome}{" "}
                <span className="secundario">
                  vence {formatarData(analise.vencimento)} · preços {FONTES[analise.fonte]}
                </span>
              </h2>
              <ResumoEstrutura analise={analise} />
              <GraficoPayoff analise={analise} />
              {analise.hoje !== null && <GradeCenarios grade={analise.hoje.grade} />}
            </>
          )}
          <div className="acoes-montador">
            <input
              aria-label="Nome da simulação"
              placeholder="nome da simulação"
              value={nome}
              onChange={(e) => setNome(e.target.value)}
            />
            <button type="button" disabled={vazia || nome.trim() === ""} onClick={() => void salvar()}>
              Salvar simulação
            </button>
            <button type="button" disabled title="Chega com a Carteira, na segunda metade da semana">
              Registrar como executada
            </button>
          </div>
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

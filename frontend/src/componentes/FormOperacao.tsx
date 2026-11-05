import { useState } from "react";

import {
  type ExecucaoRascunho,
  type RascunhoOperacao,
  registrarOperacao,
} from "../api/carteira";
import { ErroApi } from "../api/cliente";
import type { Lado, OrigemAcao } from "../api/montador";
import { CampoPreco } from "./CampoPreco";

type Props = {
  inicial: RascunhoOperacao;
  onRegistrada: (id: string) => void;
  onCancelar: () => void;
};

const NOVA_EXECUCAO: ExecucaoRascunho = { quantidade: 100, preco: null, custos: null };

function Execucoes({
  rotulo,
  execucoes,
  onMudar,
}: {
  rotulo: string;
  execucoes: ExecucaoRascunho[];
  onMudar: (execucoes: ExecucaoRascunho[]) => void;
}) {
  function mudar(i: number, parcial: Partial<ExecucaoRascunho>) {
    onMudar(execucoes.map((e, j) => (j === i ? { ...e, ...parcial } : e)));
  }
  return (
    <div className="execucoes">
      {execucoes.map((execucao, i) => (
        <span key={i} className="execucao">
          <input
            aria-label={`Quantidade de ${rotulo} (${i + 1})`}
            type="number"
            min={1}
            value={execucao.quantidade}
            onChange={(e) => mudar(i, { quantidade: Number(e.target.value) })}
          />
          <CampoPreco
            rotulo={`Preço de ${rotulo} (${i + 1})`}
            valor={execucao.preco}
            placeholder="preço"
            onMudar={(preco) => mudar(i, { preco })}
          />
          <CampoPreco
            rotulo={`Custos de ${rotulo} (${i + 1})`}
            valor={execucao.custos}
            placeholder="custos"
            onMudar={(custos) => mudar(i, { custos })}
          />
          {execucoes.length > 1 && (
            <button
              type="button"
              aria-label={`Tirar a execução ${i + 1} de ${rotulo}`}
              onClick={() => onMudar(execucoes.filter((_, j) => j !== i))}
            >
              ×
            </button>
          )}
        </span>
      ))}
      <button type="button" onClick={() => onMudar([...execucoes, NOVA_EXECUCAO])}>
        + execução
      </button>
    </div>
  );
}

function faltando(rascunho: RascunhoOperacao): string | null {
  if (rascunho.ativo.trim() === "") return "Informe o ativo.";
  if (rascunho.nome.trim() === "") return "Dê um nome à operação.";
  if (rascunho.pernas.length === 0 && rascunho.acao === null) return "Ponha ao menos uma perna.";
  for (const perna of rascunho.pernas) {
    if (perna.ticker.trim() === "") return "Informe o ticker de cada perna.";
    if (perna.execucoes.some((e) => e.preco === null)) return `Preencha o preço de ${perna.ticker}.`;
  }
  if (rascunho.acao?.origem === "compra" && rascunho.acao.execucoes.some((e) => e.preco === null))
    return "Preencha o preço da ação.";
  if ((rascunho.stop ?? 1) <= 0 || (rascunho.alvo ?? 1) <= 0)
    return "Stop e alvo são valores em R$ maiores que zero (ou em branco).";
  return null;
}

export function FormOperacao({ inicial, onRegistrada, onCancelar }: Props) {
  const [rascunho, setRascunho] = useState(inicial);
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  function mudarPerna(i: number, parcial: Partial<RascunhoOperacao["pernas"][number]>) {
    setRascunho((atual) => ({
      ...atual,
      pernas: atual.pernas.map((p, j) => (j === i ? { ...p, ...parcial } : p)),
    }));
  }

  function mudarOrigem(origem: OrigemAcao | "") {
    setRascunho((atual) => ({
      ...atual,
      acao:
        origem === ""
          ? null
          : {
              lado: "compra",
              origem,
              execucoes: origem === "carteira" ? [] : (atual.acao?.execucoes ?? [NOVA_EXECUCAO]),
            },
    }));
  }

  async function enviar() {
    const motivo = faltando(rascunho);
    if (motivo !== null) {
      setErro(motivo);
      return;
    }
    setEnviando(true);
    try {
      const { id } = await registrarOperacao(rascunho);
      onRegistrada(id);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível registrar a operação.");
    } finally {
      setEnviando(false);
    }
  }

  const acao = rascunho.acao;
  return (
    <form
      className="painel-carteira"
      aria-label="Registrar operação"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h2>Registrar operação</h2>
      <p className="secundario">
        Confira com a nota da corretora. Custos em branco são estimados pela tabela da B3.
      </p>
      <div className="campos">
        <label>
          Ativo{" "}
          <input
            aria-label="Ativo da operação"
            value={rascunho.ativo}
            onChange={(e) => setRascunho({ ...rascunho, ativo: e.target.value })}
          />
        </label>
        <label>
          Nome{" "}
          <input
            aria-label="Nome da operação"
            value={rascunho.nome}
            onChange={(e) => setRascunho({ ...rascunho, nome: e.target.value })}
          />
        </label>
        <label>
          Data{" "}
          <input
            aria-label="Data da operação"
            type="date"
            value={rascunho.data}
            onChange={(e) => setRascunho({ ...rascunho, data: e.target.value })}
          />
        </label>
      </div>
      <table className="tabela-registro">
        <thead>
          <tr>
            <th>Série</th>
            <th>Lado</th>
            <th>Execuções (quantidade, preço, custos)</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {rascunho.pernas.map((perna, i) => (
            <tr key={i}>
              <td>
                <input
                  className="campo-ticker"
                  aria-label={`Ticker da perna ${i + 1}`}
                  value={perna.ticker}
                  onChange={(e) => mudarPerna(i, { ticker: e.target.value.toUpperCase() })}
                />
              </td>
              <td>
                <select
                  aria-label={`Lado da perna ${i + 1}`}
                  value={perna.lado}
                  onChange={(e) => mudarPerna(i, { lado: e.target.value as Lado })}
                >
                  <option value="compra">compra</option>
                  <option value="venda">venda</option>
                </select>
              </td>
              <td>
                <Execucoes
                  rotulo={perna.ticker || `perna ${i + 1}`}
                  execucoes={perna.execucoes}
                  onMudar={(execucoes) => mudarPerna(i, { execucoes })}
                />
              </td>
              <td>
                <button
                  type="button"
                  aria-label={`Tirar a perna ${i + 1}`}
                  onClick={() =>
                    setRascunho((atual) => ({
                      ...atual,
                      pernas: atual.pernas.filter((_, j) => j !== i),
                    }))
                  }
                >
                  ×
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        type="button"
        onClick={() =>
          setRascunho((atual) => ({
            ...atual,
            pernas: [...atual.pernas, { ticker: "", lado: "venda", execucoes: [NOVA_EXECUCAO] }],
          }))
        }
      >
        + perna
      </button>
      <div className="campos">
        <label>
          Ação{" "}
          <select
            aria-label="Ação da operação"
            value={acao?.origem ?? ""}
            onChange={(e) => mudarOrigem(e.target.value as OrigemAcao | "")}
          >
            <option value="">sem ação</option>
            <option value="compra">comprada junto</option>
            <option value="carteira">da carteira (ações que já tenho)</option>
          </select>
        </label>
        {acao?.origem === "compra" && (
          <Execucoes
            rotulo={`ação ${rascunho.ativo}`}
            execucoes={acao.execucoes}
            onMudar={(execucoes) => setRascunho({ ...rascunho, acao: { ...acao, execucoes } })}
          />
        )}
        {acao?.origem === "carteira" && (
          <span className="secundario">usa as ações livres do perfil, pelo preço médio</span>
        )}
      </div>
      <div className="campos">
        <label>
          Stop (perda em R$){" "}
          <CampoPreco
            rotulo="Stop da operação"
            valor={rascunho.stop ?? null}
            placeholder="opcional"
            onMudar={(stop) => setRascunho((atual) => ({ ...atual, stop }))}
          />
        </label>
        <label>
          Alvo (ganho em R$){" "}
          <CampoPreco
            rotulo="Alvo da operação"
            valor={rascunho.alvo ?? null}
            placeholder="opcional"
            onMudar={(alvo) => setRascunho((atual) => ({ ...atual, alvo }))}
          />
        </label>
      </div>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      <div className="acoes-montador">
        <button type="submit" disabled={enviando}>
          Registrar
        </button>
        <button type="button" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

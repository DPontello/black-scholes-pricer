import { useState } from "react";

import { atribuir, exercer, type OperacaoCarteira } from "../api/carteira";
import { ErroApi } from "../api/cliente";
import { formatarPreco, hojeNaB3 } from "../formatacao";
import { CampoPreco } from "./CampoPreco";

type Props = {
  operacao: OperacaoCarteira;
  perna?: number;
  onFeito: () => void;
  onCancelar: () => void;
};

// Comprada é exercício (o usuário exerce); vendida é atribuição (exercem contra ele).
export function DialogoExercicio({ operacao, perna: inicial, onFeito, onCancelar }: Props) {
  const opcoes = operacao.pernas.filter((p) => p.tipo !== "acao" && p.quantidade > 0);
  const [indice, setIndice] = useState(
    opcoes.find((p) => p.indice === inicial)?.indice ?? opcoes[0]?.indice ?? 0,
  );
  const perna = opcoes.find((p) => p.indice === indice);
  const [quantidade, setQuantidade] = useState(perna?.quantidade ?? 0);
  const [data, setData] = useState(perna?.vencimento ?? hojeNaB3());
  const [custos, setCustos] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const exercicio = perna?.lado === "compra";

  function escolher(novo: number) {
    const escolhida = opcoes.find((p) => p.indice === novo);
    setIndice(novo);
    setQuantidade(escolhida?.quantidade ?? 0);
    setData(escolhida?.vencimento ?? hojeNaB3());
  }

  async function enviar() {
    const registrar = exercicio ? exercer : atribuir;
    try {
      await registrar(operacao.id, { perna: indice, quantidade, data, custos });
      onFeito();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível registrar.");
    }
  }

  return (
    <form
      className="painel-carteira"
      aria-label={`Exercício ou atribuição em ${operacao.nome}`}
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h2>Exercício ou atribuição: {operacao.nome}</h2>
      <div className="campos">
        <label>
          Perna{" "}
          <select
            aria-label="Perna exercida"
            value={indice}
            onChange={(e) => escolher(Number(e.target.value))}
          >
            {opcoes.map((p) => (
              <option key={p.indice} value={p.indice}>
                {p.ticker} · {p.tipo} {formatarPreco(p.strike)} · {p.lado} {p.quantidade}
              </option>
            ))}
          </select>
        </label>
        <label>
          Quantidade{" "}
          <input
            aria-label="Quantidade exercida"
            type="number"
            min={1}
            max={perna?.quantidade}
            value={quantidade}
            onChange={(e) => setQuantidade(Number(e.target.value))}
          />
        </label>
        <label>
          Custos{" "}
          <CampoPreco rotulo="Custos do exercício" valor={custos} placeholder="estimados" onMudar={setCustos} />
        </label>
        <label>
          Data{" "}
          <input
            aria-label="Data do exercício"
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
          />
        </label>
      </div>
      <p className="secundario">
        {exercicio ? "Você exerceu a opção." : "Exerceram a opção contra você."} A ação entra ou sai
        pelo strike, com o prêmio no preço (IN RFB 1.585/2015, art. 60).
      </p>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      <div className="acoes-montador">
        <button type="submit" disabled={perna === undefined}>
          {exercicio ? "Registrar exercício" : "Registrar atribuição"}
        </button>
        <button type="button" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

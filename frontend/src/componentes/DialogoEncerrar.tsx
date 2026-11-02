import { useState } from "react";

import { encerrar, type OperacaoCarteira } from "../api/carteira";
import { ErroApi } from "../api/cliente";
import { hojeNaB3 } from "../formatacao";
import { CampoPreco } from "./CampoPreco";

type Props = {
  operacao: OperacaoCarteira;
  onFeito: () => void;
  onCancelar: () => void;
};

export function DialogoEncerrar({ operacao, onFeito, onCancelar }: Props) {
  // A ação "da carteira" nunca tem posição própria: sai pela atribuição, não por aqui.
  const abertas = operacao.pernas.filter((p) => p.quantidade > 0);
  const [indice, setIndice] = useState(abertas[0]?.indice ?? 0);
  const perna = abertas.find((p) => p.indice === indice);
  const [quantidade, setQuantidade] = useState(perna?.quantidade ?? 0);
  const [preco, setPreco] = useState<number | null>(perna?.marca?.preco ?? null);
  const [custos, setCustos] = useState<number | null>(null);
  const [data, setData] = useState(hojeNaB3());
  const [erro, setErro] = useState<string | null>(null);

  function escolher(novo: number) {
    const escolhida = abertas.find((p) => p.indice === novo);
    setIndice(novo);
    setQuantidade(escolhida?.quantidade ?? 0);
    setPreco(escolhida?.marca?.preco ?? null);
  }

  async function enviar() {
    if (preco === null) {
      setErro("Informe o preço do encerramento.");
      return;
    }
    try {
      await encerrar(operacao.id, { perna: indice, quantidade, preco, data, custos });
      onFeito();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível encerrar.");
    }
  }

  return (
    <form
      className="painel-carteira"
      aria-label={`Encerrar ${operacao.nome}`}
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h2>Encerrar: {operacao.nome}</h2>
      <div className="campos">
        <label>
          Perna{" "}
          <select
            aria-label="Perna a encerrar"
            value={indice}
            onChange={(e) => escolher(Number(e.target.value))}
          >
            {abertas.map((p) => (
              <option key={p.indice} value={p.indice}>
                {p.ticker} · {p.lado} {p.quantidade}
              </option>
            ))}
          </select>
        </label>
        <label>
          Quantidade{" "}
          <input
            aria-label="Quantidade a encerrar"
            type="number"
            min={1}
            max={perna?.quantidade}
            value={quantidade}
            onChange={(e) => setQuantidade(Number(e.target.value))}
          />
        </label>
        <label>
          Preço <CampoPreco rotulo="Preço do encerramento" valor={preco} placeholder="preço" onMudar={setPreco} />
        </label>
        <label>
          Custos{" "}
          <CampoPreco
            rotulo="Custos do encerramento"
            valor={custos}
            placeholder="estimados"
            onMudar={setCustos}
          />
        </label>
        <label>
          Data{" "}
          <input
            aria-label="Data do encerramento"
            type="date"
            value={data}
            onChange={(e) => setData(e.target.value)}
          />
        </label>
      </div>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      <div className="acoes-montador">
        <button type="submit" disabled={perna === undefined}>
          Encerrar
        </button>
        <button type="button" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

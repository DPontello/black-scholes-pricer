import { useState } from "react";

import { adicionarAcoes } from "../api/carteira";
import { ErroApi } from "../api/cliente";
import { hojeNaB3 } from "../formatacao";
import { CampoPreco } from "./CampoPreco";

type Props = { onFeito: () => void; onCancelar: () => void };

export function AdicionarAcoes({ onFeito, onCancelar }: Props) {
  const [ativo, setAtivo] = useState("");
  const [quantidade, setQuantidade] = useState(100);
  const [precoMedio, setPrecoMedio] = useState<number | null>(null);
  const [data, setData] = useState(hojeNaB3());
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    if (ativo.trim() === "" || precoMedio === null) {
      setErro("Informe o ativo e o preço médio.");
      return;
    }
    try {
      await adicionarAcoes({ ativo, quantidade, preco_medio: precoMedio, data });
      onFeito();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível adicionar as ações.");
    }
  }

  return (
    <form
      className="painel-carteira"
      aria-label="Adicionar ações"
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h2>Adicionar ações que já tenho</h2>
      <p className="secundario">Pelo preço médio da corretora: a compra é de antes do app.</p>
      <div className="campos">
        <label>
          Ativo{" "}
          <input aria-label="Ativo das ações" value={ativo} onChange={(e) => setAtivo(e.target.value)} />
        </label>
        <label>
          Quantidade{" "}
          <input
            aria-label="Quantidade de ações"
            type="number"
            min={1}
            value={quantidade}
            onChange={(e) => setQuantidade(Number(e.target.value))}
          />
        </label>
        <label>
          Preço médio{" "}
          <CampoPreco rotulo="Preço médio" valor={precoMedio} placeholder="preço médio" onMudar={setPrecoMedio} />
        </label>
        <label>
          Data{" "}
          <input aria-label="Data das ações" type="date" value={data} onChange={(e) => setData(e.target.value)} />
        </label>
      </div>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      <div className="acoes-montador">
        <button type="submit">Adicionar</button>
        <button type="button" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

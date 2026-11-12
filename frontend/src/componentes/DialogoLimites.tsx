import { useState } from "react";

import { definirLimites, type OperacaoCarteira } from "../api/carteira";
import { ErroApi } from "../api/cliente";
import { Ajuda } from "./Ajuda";
import { CampoPreco } from "./CampoPreco";

type Props = {
  operacao: OperacaoCarteira;
  onFeito: () => void;
  onCancelar: () => void;
};

export function DialogoLimites({ operacao, onFeito, onCancelar }: Props) {
  const [stop, setStop] = useState<number | null>(operacao.stop);
  const [alvo, setAlvo] = useState<number | null>(operacao.alvo);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    if ((stop ?? 1) <= 0 || (alvo ?? 1) <= 0) {
      setErro("Stop e alvo são valores em R$ maiores que zero (ou em branco).");
      return;
    }
    try {
      await definirLimites(operacao.id, { stop, alvo });
      onFeito();
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível gravar o stop e o alvo.");
    }
  }

  return (
    <form
      className="painel-carteira"
      aria-label={`Stop e alvo de ${operacao.nome}`}
      onSubmit={(e) => {
        e.preventDefault();
        void enviar();
      }}
    >
      <h2>
        Stop e alvo: {operacao.nome} <Ajuda id="stop-e-alvo" />
      </h2>
      <p className="secundario">
        Em reais, pelo resultado total da operação (realizado + não realizado pelo preço de zerar). Em
        branco, sem alerta.
      </p>
      <div className="campos">
        <label>
          Stop (perda em R$){" "}
          <CampoPreco rotulo="Stop da operação" valor={stop} placeholder="sem stop" onMudar={setStop} />
        </label>
        <label>
          Alvo (ganho em R$){" "}
          <CampoPreco rotulo="Alvo da operação" valor={alvo} placeholder="sem alvo" onMudar={setAlvo} />
        </label>
      </div>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      <div className="acoes-montador">
        <button type="submit">Gravar</button>
        <button type="button" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  );
}

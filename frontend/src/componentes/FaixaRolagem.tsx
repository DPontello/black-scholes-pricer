import type { Rolagem } from "../api/alertas";
import type { Analise } from "../api/montador";
import { formatarData, formatarReais } from "../formatacao";
import { Ajuda } from "./Ajuda";

function caixa(valor: number): string {
  return valor >= 0 ? `recebe ${formatarReais(valor)}` : `paga ${formatarReais(-valor)}`;
}

// O Montador não junta dois vencimentos numa estrutura: a rolagem mostra aqui o lado de zerar.
export function FaixaRolagem({
  rolagem,
  analise,
  onFechar,
}: {
  rolagem: Rolagem;
  analise: Analise | null;
  onFechar: () => void;
}) {
  const atual = formatarData(rolagem.vencimento_atual);
  const zerar =
    rolagem.caixa_de_zerar === null
      ? `Zerar as pernas atuais (vencimento ${atual}): sem preço de zerar agora.`
      : `Zerar as pernas atuais (vencimento ${atual}) ${caixa(rolagem.caixa_de_zerar)} pelo preço de zerar.`;
  let nova: string;
  if (rolagem.vencimento_novo === null) nova = `A cadeia não tem vencimento depois de ${atual}.`;
  else if (rolagem.pedido === null)
    nova = `A operação não veio de um modelo: monte a estrutura nova pela cadeia, em ${formatarData(rolagem.vencimento_novo)}.`;
  else nova = `Abaixo, a mesma estrutura em ${formatarData(rolagem.vencimento_novo)}.`;
  const novaCaixa = rolagem.pedido === null ? null : (analise?.no_vencimento?.caixa ?? null);
  const liquido =
    rolagem.caixa_de_zerar === null || novaCaixa === null
      ? null
      : `Caixa líquido da rolagem: ${caixa(rolagem.caixa_de_zerar + novaCaixa)}.`;

  return (
    <aside className="faixa-rolagem" aria-label="Rolagem">
      <p>
        <strong>Rolagem de {rolagem.nome}</strong> <Ajuda id="rolagem" />
      </p>
      <p>{zerar}</p>
      <p>{nova}</p>
      {liquido !== null && <p>{liquido}</p>}
      <p className="secundario">
        Nada é enviado: encerre as pernas atuais pela Carteira e registre a nova depois de executar.
      </p>
      <button type="button" onClick={onFechar}>
        Fechar a faixa
      </button>
    </aside>
  );
}

import { useNavigate } from "react-router-dom";

import type { Familia, ItemBook } from "../api/book";
import { formatarData, formatarDiasUteis } from "../formatacao";
import { Ajuda } from "./Ajuda";
import { LinhaPernas } from "./LinhaPernas";

type Props = {
  familia: Familia;
  rotulo: string;
  item: ItemBook | null;
  motivoVazio: string;
  // Só o cartão vazio usa: leva à aba da família, onde estão as referências e as exclusões.
  onVerFamilia?: () => void;
};

// O termo do glossário que explica o critério de cada família; critério sem termo fica sem "?".
export const TERMO_DO_CRITERIO: Record<string, string> = {
  anual: "anualizado",
  retorno_risco: "retorno-sobre-risco",
  ganho_risco: "ganho-perda-maximos",
  dist_be: "empate",
  desconto_vol: "vol-cara-barata",
};

type NumeroProps = { rotulo: string; texto: string; termo: string; classe?: string };

function Numero({ rotulo, texto, termo, classe }: NumeroProps) {
  return (
    <div className="resultado-numero">
      <span className="secundario">
        {rotulo} <Ajuda id={termo} />
      </span>{" "}
      <strong className={classe}>{texto}</strong>
    </div>
  );
}

export function CartaoDestaque({ familia, rotulo, item, motivoVazio, onVerFamilia }: Props) {
  const navegar = useNavigate();
  const idRotulo = `destaque-${familia}`;

  function abrir(destaque: ItemBook) {
    navegar(`/montador?ativo=${encodeURIComponent(destaque.ativo)}`, {
      state: { pedido: destaque.pedido, vencimento: destaque.vencimento },
    });
  }

  return (
    <article className="cartao-destaque" aria-labelledby={idRotulo}>
      <p className="familia-destaque" id={idRotulo}>
        {rotulo}
      </p>
      {item === null ? (
        <>
          <h3>Nada hoje em {rotulo}</h3>
          <p className="secundario">{motivoVazio}</p>
          {onVerFamilia !== undefined && (
            <button type="button" className="link" onClick={onVerFamilia}>
              ver a aba {rotulo}
            </button>
          )}
        </>
      ) : (
        <>
          <h3>
            {item.nome} · {item.ativo} · vence {formatarData(item.vencimento)} (
            {formatarDiasUteis(item.dias_uteis)})
          </h3>
          <LinhaPernas item={item} />
          <p className="numero-grande">
            <strong className="alta">{item.criterio.texto}</strong>{" "}
            <span className="secundario">{item.criterio.rotulo}</span>
            {TERMO_DO_CRITERIO[item.criterio.chave] !== undefined && (
              <>
                {" "}
                <Ajuda id={TERMO_DO_CRITERIO[item.criterio.chave] as string} />
              </>
            )}
          </p>
          <div className="resultado-curto">
            <Numero
              rotulo="ganha até"
              texto={item.resultado?.ganha_ate_texto ?? "—"}
              termo="ganho-perda-maximos"
            />
            <Numero
              rotulo="perde até"
              texto={item.resultado?.perde_ate_texto ?? "—"}
              termo="ganho-perda-maximos"
              classe={item.resultado === null ? undefined : "baixa"}
            />
            <Numero
              rotulo="chance de lucro"
              texto={item.resultado?.chance_texto ?? "—"}
              termo="chance-de-lucro"
            />
          </div>
          <p className="porque-curto">{item.porque_curto}</p>
          {item.rotulos.length > 0 && (
            <ul className="rotulos">
              {item.rotulos.map((r) => (
                <li key={r.chave}>{r.texto}</li>
              ))}
            </ul>
          )}
          <button type="button" onClick={() => abrir(item)}>
            Abrir no montador
          </button>
        </>
      )}
    </article>
  );
}

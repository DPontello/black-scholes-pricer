import type { Fonte, StatusMercado } from "../api/cliente";

const ROTULOS: Record<Fonte, { texto: string; classe: string }> = {
  ao_vivo: { texto: "Ao vivo (Tryd)", classe: "fonte-ao-vivo" },
  atrasado: { texto: "Atrasado", classe: "fonte-atrasado" },
  fim_de_dia: { texto: "Fim de dia (B3)", classe: "fonte-fim-de-dia" },
};

type Props = {
  status: StatusMercado | null;
  /** Falso enquanto o app não responde ao WebSocket. */
  conectado?: boolean;
};

/** De onde vêm os números agora, sempre visível; e o aviso de cadastro velho. */
export function BarraStatus({ status, conectado = true }: Props) {
  if (!conectado || status === null) {
    return (
      <span className="barra-status fonte-fim-de-dia" role="status">
        Conectando ao app…
      </span>
    );
  }
  const rotulo = ROTULOS[status.fonte];
  const cadastro = status.cadastro;
  return (
    <span className="barra-status" role="status">
      <span className={`selo-fonte ${rotulo.classe}`}>● {rotulo.texto}</span>
      {cadastro?.velho === true && (
        <span className="aviso">
          {" "}
          Cadastro com {cadastro.dias_uteis} dias úteis: séries novas podem estar faltando
        </span>
      )}
    </span>
  );
}

import type { Analise } from "../api/montador";
import { formatarData } from "../formatacao";
import { PREFERENCIA_DETALHES, usePreferencia } from "../preferencias";
import { GraficoPayoff } from "./GraficoPayoff";
import { AvisosEstrutura, DetalhesEstrutura, ResumoEstrutura } from "./ResumoEstrutura";

const FONTES = { ao_vivo: "ao vivo (Tryd)", atrasado: "atrasado", fim_de_dia: "fim de dia (B3)" };

export function CartaoResultado({ analise }: { analise: Analise }) {
  const [aberto, setAberto] = usePreferencia(PREFERENCIA_DETALHES);
  return (
    <section className="cartao cartao-resultado">
      <h2>
        {analise.nome}{" "}
        <span className="secundario">
          vence {formatarData(analise.vencimento)} · preços {FONTES[analise.fonte]}
        </span>
      </h2>
      <ResumoEstrutura analise={analise} />
      <GraficoPayoff analise={analise} />
      <AvisosEstrutura analise={analise} />
      <button type="button" className="link" aria-expanded={aberto} onClick={() => setAberto(!aberto)}>
        {aberto ? "▾ esconder detalhes" : "▸ ver detalhes"}
      </button>
      {aberto && <DetalhesEstrutura analise={analise} />}
    </section>
  );
}

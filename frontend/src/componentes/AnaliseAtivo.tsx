import { useEffect, useState } from "react";

import { type AnaliseMercado, analisarAtivo } from "../api/analise";
import { ErroApi } from "../api/cliente";
import { formatarData, formatarHora, formatarVol } from "../formatacao";
import { GraficoSmile, GraficoTermo } from "./GraficoSmile";
import { GraficoVol } from "./GraficoVol";

const FONTES = { ao_vivo: "ao vivo (Tryd)", atrasado: "atrasado", fim_de_dia: "fim de dia (B3)" };
const CURTO = "histórico curto";

export function AnaliseAtivo({ ativo }: { ativo: string }) {
  const [analise, setAnalise] = useState<AnaliseMercado | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [vencimento, setVencimento] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    setAnalise(null);
    setVencimento(null);
    analisarAtivo(ativo)
      .then((nova) => {
        if (cancelado) return;
        setAnalise(nova);
        setErro(null);
      })
      .catch((e: unknown) => {
        if (!cancelado)
          setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível analisar o ativo.");
      });
    return () => {
      cancelado = true;
    };
  }, [ativo]);

  if (erro !== null)
    return (
      <p className="erro" role="alert">
        {erro}
      </p>
    );
  if (analise === null) return <p className="secundario">Analisando {ativo}…</p>;

  const hoje = analise.hoje;
  const smile = analise.smiles.find((s) => s.vencimento === vencimento) ?? analise.smiles[0];
  return (
    <section className="analise-ativo" aria-label={`Análise de ${ativo}`}>
      <p className="secundario">
        Hoje pela cadeia {FONTES[analise.fonte]} ({formatarHora(analise.hora)}); histórico de fim de
        dia dos COTAHIST. Taxa: o CDI do perfil ({formatarVol(analise.cdi_anual)} a.a.), constante em
        todo o histórico, uma aproximação.
      </p>
      {hoje === null ? (
        <p className="aviso">{analise.hoje_motivo}</p>
      ) : (
        <div className="cartoes">
          <Cartao rotulo="IV 30 hoje" valor={formatarVol(hoje.iv30) + (hoje.extrapolada ? " (extrapolada)" : "")} />
          <Cartao rotulo="HV 21" valor={formatarVol(hoje.hv21)} />
          <Cartao rotulo="IV rank" valor={hoje.iv_rank === null ? CURTO : formatarVol(hoje.iv_rank)} />
          <Cartao
            rotulo="Percentil"
            valor={hoje.iv_percentil === null ? CURTO : formatarVol(hoje.iv_percentil)}
          />
          <Cartao
            rotulo="Regime de vol"
            valor={hoje.regime + (hoje.regime_pela_hv ? " (pela HV)" : "")}
          />
        </div>
      )}
      {analise.historico_motivo !== null ? (
        <p className="aviso">{analise.historico_motivo}</p>
      ) : (
        <GraficoVol ativo={ativo} historico={analise.historico} />
      )}
      {smile === undefined ? (
        <p className="aviso">Sem smile: nenhum vencimento com séries na cadeia.</p>
      ) : (
        <>
          <h2>Smile</h2>
          <div className="vencimentos" role="group" aria-label="Vencimento do smile">
            {analise.smiles.map((s) => (
              <button
                key={s.vencimento}
                type="button"
                aria-pressed={s.vencimento === smile.vencimento}
                onClick={() => setVencimento(s.vencimento)}
              >
                {formatarData(s.vencimento)} ({s.dias_uteis} du)
              </button>
            ))}
          </div>
          <GraficoSmile smile={smile} spot={analise.spot} />
          <h2>Estrutura a termo</h2>
          <GraficoTermo estrutura={analise.estrutura} />
        </>
      )}
    </section>
  );
}

function Cartao({ rotulo, valor }: { rotulo: string; valor: string }) {
  return (
    <div className="cartao">
      <span className="secundario">{rotulo}</span>
      <strong>{valor}</strong>
    </div>
  );
}

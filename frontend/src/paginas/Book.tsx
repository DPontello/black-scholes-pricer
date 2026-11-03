import { useEffect, useState } from "react";

import {
  type Book as Resposta,
  carregarBook,
  type ContextoVol,
  direcional,
  type Familia,
  type FamiliaBook,
} from "../api/book";
import { ErroApi, type Perfil } from "../api/cliente";
import { CartaoDestaque } from "../componentes/CartaoDestaque";
import { EditorPreset } from "../componentes/EditorPreset";
import { motivoVazio, TabelaFamilia } from "../componentes/TabelaFamilia";
import { Termo } from "../componentes/Termo";
import { formatarData, formatarVol } from "../formatacao";

const FAMILIAS: [Familia, string][] = [
  ["renda", "Renda"],
  ["volatilidade", "Volatilidade"],
  ["direcionais", "Direcionais"],
  ["protecao", "Proteção"],
];

const REGIME = { baixa: "barata", neutra: "normal", alta: "cara" };

type Props = { perfil: Perfil; onPerfil: (perfil: Perfil) => void };

function mensagem(erro: unknown, padrao: string): string {
  return erro instanceof ErroApi ? erro.mensagem : padrao;
}

export function Book({ perfil, onPerfil }: Props) {
  const [book, setBook] = useState<Resposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<Familia>("renda");
  const [ajustando, setAjustando] = useState(false);

  // O preset e a lista vêm do perfil: mudou um dos dois, o book é varrido de novo.
  useEffect(() => {
    let cancelado = false;
    setBook(null);
    carregarBook()
      .then((novo) => {
        if (cancelado) return;
        setBook(novo);
        setErro(null);
      })
      .catch((e: unknown) => {
        if (!cancelado) setErro(mensagem(e, "Não foi possível montar o book."));
      });
    return () => {
      cancelado = true;
    };
  }, [perfil.book, perfil.ativos]);

  return (
    <section className="pagina-book">
      <header className="cabecalho-book">
        <h1>Melhores operações de hoje</h1>
        {book !== null && (
          <p className="selo-fonte fonte-fim-de-dia">
            {book.pregao === null
              ? "Sem pregão de fim de dia: importe um COTAHIST em Arquivos B3."
              : `pregão de ${formatarData(book.pregao)} · fim de dia (B3)`}
          </p>
        )}
        <p className="criterios">
          Critérios: <strong>{capitalizar(perfil.book.preset)}</strong> ·{" "}
          <button
            type="button"
            className="link"
            aria-expanded={ajustando}
            onClick={() => setAjustando(!ajustando)}
          >
            ajustar <span aria-hidden="true">{ajustando ? "▾" : "▸"}</span>
          </button>
        </p>
      </header>
      {ajustando && <EditorPreset preset={perfil.book} onSalvo={onPerfil} />}
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      {book === null && erro === null && <p className="secundario">Varrendo o fim de dia…</p>}
      {book !== null && (
        <>
          <EtiquetasVol contextos={book.contextos} />
          {book.pregao !== null && (
            <>
              <h2>O melhor de cada família</h2>
              <div className="cartoes-destaque">
                {FAMILIAS.map(([chave, rotulo]) => (
                  <CartaoDestaque
                    key={chave}
                    familia={chave}
                    rotulo={rotulo}
                    item={book.familias[chave].itens[0] ?? null}
                    motivoVazio={motivoVazio(book.familias[chave])}
                    onVerFamilia={() => setAba(chave)}
                  />
                ))}
              </div>
              <div className="abas" role="tablist">
                {FAMILIAS.map(([chave, rotulo]) => (
                  <button
                    key={chave}
                    type="button"
                    role="tab"
                    aria-selected={aba === chave}
                    onClick={() => setAba(chave)}
                  >
                    {rotulo} ({book.familias[chave].itens.length})
                  </button>
                ))}
              </div>
              <div role="tabpanel">
                {aba === "direcionais" && <ComVisao ativos={perfil.ativos} />}
                <TabelaFamilia key={aba} familia={book.familias[aba]} />
              </div>
            </>
          )}
          {book.indisponiveis.length > 0 && (
            <details className="indisponiveis">
              <summary>Ativos indisponíveis ({book.indisponiveis.length})</summary>
              <ul>
                {book.indisponiveis.map((e) => (
                  <li key={e.simbolo}>{comAtivo(e.simbolo, e.motivo, ": ")}</li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </section>
  );
}

// Alguns motivos já trazem o ticker na frente ("PETR4: sem histórico de IV"), outros não.
function comAtivo(ativo: string, motivo: string, separador: string): string {
  return motivo.startsWith(`${ativo}:`) ? motivo : `${ativo}${separador}${motivo}`;
}

function capitalizar(texto: string): string {
  return texto.charAt(0).toUpperCase() + texto.slice(1);
}

function dicaVol(c: ContextoVol): string {
  return [
    `IV 30: ${formatarVol(c.iv30)}${c.extrapolada ? " (extrapolada)" : ""}`,
    `HV 21: ${formatarVol(c.hv21)}`,
    `IV rank: ${formatarVol(c.iv_rank)}`,
    `percentil: ${formatarVol(c.iv_percentil)}`,
  ].join(" · ");
}

function EtiquetasVol({ contextos }: { contextos: ContextoVol[] }) {
  if (contextos.length === 0) return null;
  return (
    <div className="vol-dos-ativos">
      <ul className="etiquetas-vol" aria-label="Vol de cada ativo">
        {contextos.map((c) =>
          c.motivo !== null ? (
            <li className="etiqueta-vol secundario" key={c.ativo}>
              {comAtivo(c.ativo, c.motivo, " · ")}
            </li>
          ) : (
            <li className="etiqueta-vol" key={c.ativo} title={dicaVol(c)}>
              {c.ativo}
              {c.regime !== null && (
                <>
                  {" "}
                  · vol <strong>{REGIME[c.regime]}</strong>
                  {c.regime_pela_hv && " (pela HV)"}
                </>
              )}
            </li>
          ),
        )}
      </ul>
      <Termo id="vol-cara-barata">o que é vol barata ou cara?</Termo>
    </div>
  );
}

function ComVisao({ ativos }: { ativos: string[] }) {
  const [ativo, setAtivo] = useState(ativos[0] ?? "");
  const [direcao, setDirecao] = useState<"alta" | "baixa">("alta");
  const [alvo, setAlvo] = useState("");
  const [vencimento, setVencimento] = useState("");
  const [resultado, setResultado] = useState<FamiliaBook | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  async function enviar() {
    try {
      setResultado(await direcional({ ativo, direcao, alvo: Number(alvo), vencimento }));
      setErro(null);
    } catch (e) {
      setResultado(null);
      setErro(mensagem(e, "Não foi possível montar as Direcionais com visão."));
    }
  }

  return (
    <section className="com-visao" aria-label="Com visão">
      <h2>Com visão</h2>
      <form
        className="campos"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
      >
        <label>
          Ativo
          <select value={ativo} onChange={(e) => setAtivo(e.target.value)}>
            {ativos.map((a) => (
              <option key={a}>{a}</option>
            ))}
          </select>
        </label>
        <label>
          Direção
          <select value={direcao} onChange={(e) => setDirecao(e.target.value as "alta" | "baixa")}>
            <option value="alta">alta</option>
            <option value="baixa">baixa</option>
          </select>
        </label>
        <label>
          Preço-alvo
          <input
            type="number"
            step="0.01"
            min="0"
            required
            value={alvo}
            onChange={(e) => setAlvo(e.target.value)}
          />
        </label>
        <label>
          Vencimento
          <input
            type="date"
            required
            value={vencimento}
            onChange={(e) => setVencimento(e.target.value)}
          />
        </label>
        <button type="submit">Ver as operações</button>
      </form>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      {resultado !== null && <TabelaFamilia familia={resultado} />}
      <h2>Sem visão: opções baratas pela vol</h2>
    </section>
  );
}

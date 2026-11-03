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
import { EditorPreset } from "../componentes/EditorPreset";
import { ItemBook } from "../componentes/ItemBook";
import { formatarData, formatarVol } from "../formatacao";

const FAMILIAS: [Familia, string][] = [
  ["renda", "Renda"],
  ["volatilidade", "Volatilidade"],
  ["direcionais", "Direcionais"],
  ["protecao", "Proteção"],
];

type Props = { perfil: Perfil; onPerfil: (perfil: Perfil) => void };

function mensagem(erro: unknown, padrao: string): string {
  return erro instanceof ErroApi ? erro.mensagem : padrao;
}

export function Book({ perfil, onPerfil }: Props) {
  const [book, setBook] = useState<Resposta | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [aba, setAba] = useState<Familia>("renda");

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
      <h1>Book</h1>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      {book === null && erro === null && <p className="secundario">Varrendo o fim de dia…</p>}
      {book !== null && (
        <>
          <p className="selo-fonte fonte-fim-de-dia">
            {book.pregao === null
              ? "Sem pregão de fim de dia: importe um COTAHIST em Arquivos B3."
              : `fim de dia (B3) do pregão ${formatarData(book.pregao)}`}
          </p>
          {book.indisponiveis.map((e) => (
            <p className="aviso" key={e.simbolo}>
              {e.simbolo}: {e.motivo}
            </p>
          ))}
          <ContextosVol contextos={book.contextos} />
        </>
      )}
      <EditorPreset preset={perfil.book} onSalvo={onPerfil} />
      <div className="abas" role="tablist">
        {FAMILIAS.map(([chave, rotulo]) => (
          <button
            key={chave}
            type="button"
            role="tab"
            aria-selected={aba === chave}
            onClick={() => setAba(chave)}
          >
            {rotulo}
          </button>
        ))}
      </div>
      {aba === "direcionais" && <ComVisao ativos={perfil.ativos} />}
      {book !== null && <PainelFamilia familia={book.familias[aba]} />}
    </section>
  );
}

function ContextosVol({ contextos }: { contextos: ContextoVol[] }) {
  if (contextos.length === 0) return null;
  return (
    <table className="contextos-vol">
      <caption>Vol de cada ativo no fim de dia</caption>
      <thead>
        <tr>
          <th>Ativo</th>
          <th className="num">IV 30</th>
          <th className="num">HV 21</th>
          <th className="num">IV rank</th>
          <th className="num">Percentil</th>
          <th>Regime</th>
        </tr>
      </thead>
      <tbody>
        {contextos.map((c) =>
          c.motivo !== null ? (
            <tr key={c.ativo}>
              <td>{c.ativo}</td>
              <td colSpan={5} className="secundario">
                {c.motivo}
              </td>
            </tr>
          ) : (
            <tr key={c.ativo}>
              <td>{c.ativo}</td>
              <td className="num">
                {formatarVol(c.iv30)}
                {c.extrapolada && " (extrapolada)"}
              </td>
              <td className="num">{formatarVol(c.hv21)}</td>
              <td className="num">{formatarVol(c.iv_rank)}</td>
              <td className="num">{formatarVol(c.iv_percentil)}</td>
              <td>
                {c.regime}
                {c.regime_pela_hv && " (pela HV: histórico curto)"}
              </td>
            </tr>
          ),
        )}
      </tbody>
    </table>
  );
}

function PainelFamilia({ familia }: { familia: FamiliaBook }) {
  return (
    <div className="painel-familia" role="tabpanel">
      {familia.itens.length === 0 ? (
        <p className="secundario">Nada passou nos filtros do preset nesta família.</p>
      ) : (
        <div className="lista-book">
          {familia.itens.map((item) => (
            <ItemBook key={item.pedido.pernas.map((p) => p.ticker).join("/")} item={item} />
          ))}
        </div>
      )}
      {familia.referencias.length > 0 && (
        <section className="referencias" aria-label="Referências">
          <h2>Referências (sem preço executável em alguma perna)</h2>
          <div className="lista-book">
            {familia.referencias.map((item) => (
              <ItemBook key={item.pedido.pernas.map((p) => p.ticker).join("/")} item={item} />
            ))}
          </div>
        </section>
      )}
      {familia.exclusoes.length > 0 && (
        <details className="exclusoes">
          <summary>Fora do book por dado ruim ({familia.exclusoes.length})</summary>
          <ul>
            {familia.exclusoes.map((e) => (
              <li key={`${e.simbolo}:${e.motivo}`}>
                {e.simbolo}: {e.motivo}
              </li>
            ))}
          </ul>
        </details>
      )}
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
      {resultado !== null && <PainelFamilia familia={resultado} />}
      <h2>Sem visão: opções baratas pela vol</h2>
    </section>
  );
}

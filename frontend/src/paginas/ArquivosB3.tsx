import { type DragEvent, useCallback, useEffect, useState } from "react";

import {
  type ArquivoB3,
  enviarArquivo,
  ErroApi,
  importacaoAutomatica,
  type ImportacaoAutomatica,
  listarArquivos,
  statusMercado,
  type StatusMercado,
} from "../api/cliente";
import { formatarData, formatarInstante } from "../formatacao";

// Download à mão: os termos da B3 proíbem coleta automática (ADR-0006).
const LINK_COTAHIST =
  "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/";
const LINK_CADASTRO =
  "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/boletins-diarios/pesquisa-por-pregao/";

const TIPOS: Record<ArquivoB3["tipo"], string> = {
  cotahist: "COTAHIST (histórico)",
  cadastro: "Cadastro de Instrumentos",
};

type Pregao = { data: string; diasUteis: number | null; velho: boolean };

// O estado vem escrito ("em dia", "hora de baixar"): a cor só reforça.
function EstadoDoPasso({ pregao, motivo }: { pregao: Pregao | null; motivo: string | null }) {
  if (pregao === null) {
    return motivo !== null ? (
      <p>{motivo}</p>
    ) : (
      <p>
        <strong className="estado-ausente">ainda não baixado</strong>
      </p>
    );
  }
  const quando = `pregão de ${formatarData(pregao.data)}`;
  if (pregao.diasUteis === null) return <p>{quando}</p>;
  if (pregao.velho)
    return (
      <p>
        <strong className="estado-velho">hora de baixar</strong> · {quando}, há {pregao.diasUteis}{" "}
        dias úteis
      </p>
    );
  return (
    <p>
      <strong className="estado-em-dia">em dia</strong> · {quando}
    </p>
  );
}

export function ArquivosB3() {
  const [arquivos, setArquivos] = useState<ArquivoB3[]>([]);
  const [status, setStatus] = useState<StatusMercado | null>(null);
  const [mensagem, setMensagem] = useState<{ texto: string; erro: boolean } | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [automatico, setAutomatico] = useState<ImportacaoAutomatica | null>(null);

  const carregar = useCallback(() => {
    listarArquivos()
      .then(setArquivos)
      .catch(() => setMensagem({ texto: "Não foi possível ler a lista de arquivos.", erro: true }));
    statusMercado()
      .then(setStatus)
      .catch(() => setStatus(null));
    importacaoAutomatica()
      .then(setAutomatico)
      .catch(() => setAutomatico(null));
  }, []);

  useEffect(() => {
    carregar();
    const intervalo = setInterval(carregar, 10_000);
    return () => clearInterval(intervalo);
  }, [carregar]);

  async function enviar(lista: FileList | null) {
    if (lista === null || lista.length === 0) return;
    setEnviando(true);
    setMensagem(null);
    try {
      const nomes: string[] = [];
      for (const arquivo of Array.from(lista)) {
        const guardado = await enviarArquivo(arquivo);
        nomes.push(guardado.nome);
      }
      setMensagem({ texto: `Importado: ${nomes.join(", ")}.`, erro: false });
    } catch (e) {
      const texto =
        e instanceof ErroApi ? e.mensagem : "Não foi possível enviar o arquivo. O app está aberto?";
      setMensagem({ texto, erro: true });
    } finally {
      setEnviando(false);
      carregar();
    }
  }

  function soltar(evento: DragEvent<HTMLDivElement>) {
    evento.preventDefault();
    void enviar(evento.dataTransfer.files);
  }

  const cadastro = status?.cadastro ?? null;
  const cotahist = status?.cotahist ?? null;
  const anoCorrente = new Date().getFullYear();

  return (
    <section className="pagina-arquivos">
      <h1>Arquivos da B3</h1>
      <div className="rotina-semana">
        <h2>Rotina da semana</h2>
        <ol>
          <li>
            <a href={LINK_CADASTRO} target="_blank" rel="noreferrer">
              Cadastro de Instrumentos — Pesquisa por pregão
            </a>
            <p className="secundario">
              Escolha o último pregão e o Cadastro de Instrumentos. O arquivo se chama{" "}
              <strong>pesquisa-pregao.zip</strong>.
            </p>
            {status !== null && (
              <EstadoDoPasso
                pregao={
                  cadastro === null
                    ? null
                    : { data: cadastro.data, diasUteis: cadastro.dias_uteis, velho: cadastro.velho }
                }
                motivo={status.cadastro_motivo}
              />
            )}
          </li>
          <li>
            <a href={LINK_COTAHIST} target="_blank" rel="noreferrer">
              COTAHIST anual — Cotações Históricas
            </a>
            <p className="secundario">
              Baixe a série anual do ano corrente. O arquivo se chama{" "}
              <strong>{`COTAHIST_A${anoCorrente}.zip`}</strong>.
            </p>
            {status !== null && (
              <EstadoDoPasso
                pregao={
                  cotahist === null
                    ? null
                    : { data: cotahist.ate, diasUteis: cotahist.dias_uteis, velho: cotahist.velho }
                }
                motivo={null}
              />
            )}
          </li>
        </ol>
        <p className="secundario">
          O diário não é preciso: o anual baixado no dia já traz o último pregão.
        </p>
      </div>
      <p className="secundario">
        A cadeia de opções precisa do Cadastro de Instrumentos (séries e estilo de exercício). O
        COTAHIST é opcional: serve para o fim de dia, quando o Tryd está fechado, e para o
        histórico.
      </p>
      {automatico?.pasta && (
        <p className="secundario">
          Os arquivos da B3 que você baixar para <strong>{automatico.pasta}</strong> entram sozinhos.
        </p>
      )}
      {automatico !== null && automatico.eventos.length > 0 && (
        <ul className="eventos-automaticos">
          {automatico.eventos.slice(0, 5).map((evento) => (
            <li key={`${evento.nome}-${evento.quando}`} className={evento.importado ? "" : "erro"}>
              {formatarInstante(evento.quando)} {evento.nome}:{" "}
              {evento.importado ? `importado (${evento.detalhe})` : evento.detalhe}
            </li>
          ))}
        </ul>
      )}
      {cadastro?.velho === true && (
        <p className="aviso" role="status">
          Cadastro com {cadastro.dias_uteis} dias úteis: séries novas podem estar faltando
        </p>
      )}
      <div className="area-soltar" onDragOver={(evento) => evento.preventDefault()} onDrop={soltar}>
        <p>
          Arraste aqui o COTAHIST (.zip ou .txt) ou o Cadastro de Instrumentos (.csv ou o
          pesquisa-pregao.zip).
        </p>
        <label className="botao-arquivo">
          Escolher arquivo
          <input
            type="file"
            accept=".zip,.txt,.csv"
            multiple
            disabled={enviando}
            onChange={(evento) => void enviar(evento.target.files)}
          />
        </label>
      </div>
      {mensagem !== null && (
        <p className={mensagem.erro ? "erro" : "secundario"} role={mensagem.erro ? "alert" : "status"}>
          {mensagem.texto}
        </p>
      )}
      <table>
        <thead>
          <tr>
            <th>Arquivo</th>
            <th>Tipo</th>
            <th>Data</th>
            <th>Importado em</th>
          </tr>
        </thead>
        <tbody>
          {arquivos.map((arquivo) => (
            <tr key={`${arquivo.tipo}/${arquivo.nome}`}>
              <td>{arquivo.nome}</td>
              <td>{TIPOS[arquivo.tipo]}</td>
              <td>{arquivo.data === null ? "—" : formatarData(arquivo.data)}</td>
              <td className="secundario">
                {arquivo.importado_em === undefined ? "—" : formatarInstante(arquivo.importado_em)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {arquivos.length === 0 && <p className="secundario">Nenhum arquivo importado ainda.</p>}
    </section>
  );
}

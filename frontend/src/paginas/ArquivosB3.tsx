import { type DragEvent, useCallback, useEffect, useState } from "react";

import {
  type ArquivoB3,
  enviarArquivo,
  ErroApi,
  listarArquivos,
  statusMercado,
  type StatusMercado,
} from "../api/cliente";
import { formatarData, formatarInstante } from "../formatacao";

// Download à mão: os termos da B3 proíbem coleta automática (ADR-0006).
const LINK_COTAHIST =
  "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/";
const LINK_BOLETIM =
  "https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/consultas/boletim-diario/";

const TIPOS: Record<ArquivoB3["tipo"], string> = {
  cotahist: "COTAHIST (histórico)",
  cadastro: "Cadastro de Instrumentos",
};

export function ArquivosB3() {
  const [arquivos, setArquivos] = useState<ArquivoB3[]>([]);
  const [status, setStatus] = useState<StatusMercado | null>(null);
  const [mensagem, setMensagem] = useState<{ texto: string; erro: boolean } | null>(null);
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(() => {
    listarArquivos()
      .then(setArquivos)
      .catch(() => setMensagem({ texto: "Não foi possível ler a lista de arquivos.", erro: true }));
    statusMercado()
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  useEffect(carregar, [carregar]);

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

  return (
    <section className="pagina-arquivos">
      <h1>Arquivos da B3</h1>
      {cadastro?.velho === true && (
        <p className="aviso" role="status">
          Cadastro com {cadastro.dias_uteis} dias úteis: séries novas podem estar faltando
        </p>
      )}
      {status !== null && status.cadastro === null && status.cadastro_motivo !== null && (
        <p className="aviso" role="status">
          {status.cadastro_motivo}
        </p>
      )}
      <div className="area-soltar" onDragOver={(evento) => evento.preventDefault()} onDrop={soltar}>
        <p>Arraste aqui o COTAHIST (.zip ou .txt) ou o Cadastro de Instrumentos (.csv).</p>
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
      <h2>Onde baixar</h2>
      <ul>
        <li>
          <a href={LINK_COTAHIST} target="_blank" rel="noreferrer">
            COTAHIST — Cotações Históricas da B3
          </a>{" "}
          <span className="secundario">(o anual, e o diário do último pregão)</span>
        </li>
        <li>
          <a href={LINK_BOLETIM} target="_blank" rel="noreferrer">
            Cadastro de Instrumentos — Boletim Diário da B3
          </a>{" "}
          <span className="secundario">
            (em "Pesquisa por pregão", o Cadastro de Instrumentos do mesmo pregão)
          </span>
        </li>
      </ul>
    </section>
  );
}

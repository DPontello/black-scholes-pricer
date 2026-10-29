import { type FormEvent, useCallback, useEffect, useState } from "react";

import {
  abrirPerfil,
  criarPerfil,
  type EntradaPerfil,
  ErroApi,
  listarPerfis,
  type Perfil,
  type Trava,
} from "../api/cliente";
import { formatarHora } from "../formatacao";

type Props = {
  onAberto: (perfil: Perfil) => void;
};

type Confirmacao = { nome: string; trava: Trava };

export function Perfis({ onAberto }: Props) {
  const [perfis, setPerfis] = useState<EntradaPerfil[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [confirmacao, setConfirmacao] = useState<Confirmacao | null>(null);
  const [criando, setCriando] = useState(false);
  const [nome, setNome] = useState("");
  const [pasta, setPasta] = useState("");

  const carregar = useCallback(() => {
    listarPerfis()
      .then(setPerfis)
      .catch((e: unknown) => setErro(mensagemDe(e)));
  }, []);

  useEffect(carregar, [carregar]);

  async function abrir(nomePerfil: string, forcar: boolean) {
    setErro(null);
    try {
      const perfil = await abrirPerfil(nomePerfil, forcar);
      setConfirmacao(null);
      onAberto(perfil);
    } catch (e) {
      if (e instanceof ErroApi && e.status === 409 && e.trava !== undefined) {
        setConfirmacao({ nome: nomePerfil, trava: e.trava });
      } else {
        setErro(mensagemDe(e));
      }
    }
  }

  async function criar(evento: FormEvent) {
    evento.preventDefault();
    setErro(null);
    try {
      await criarPerfil(nome.trim(), pasta.trim());
      setCriando(false);
      setNome("");
      setPasta("");
      carregar();
    } catch (e) {
      setErro(mensagemDe(e));
    }
  }

  return (
    <section className="pagina-perfis">
      <h1>Quem está usando?</h1>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      {confirmacao !== null && (
        <div className="confirmacao" role="alertdialog" aria-label="Perfil aberto em outro PC">
          <p>
            Este perfil está aberto no PC {confirmacao.trava.pc} desde{" "}
            {formatarHora(confirmacao.trava.desde)}. Abrir mesmo assim?
          </p>
          <button type="button" onClick={() => void abrir(confirmacao.nome, true)}>
            Abrir mesmo assim
          </button>{" "}
          <button type="button" onClick={() => setConfirmacao(null)}>
            Cancelar
          </button>
        </div>
      )}
      <div className="cartoes">
        {perfis?.map((perfil) => (
          <div className="cartao" key={perfil.nome}>
            <strong>{perfil.nome}</strong>
            <span className="secundario">{perfil.pasta}</span>
            <button
              type="button"
              aria-label={`Abrir ${perfil.nome}`}
              onClick={() => void abrir(perfil.nome, false)}
            >
              Abrir
            </button>
          </div>
        ))}
        {perfis?.length === 0 && <p className="secundario">Nenhum perfil neste PC ainda.</p>}
      </div>
      {criando ? (
        <form className="novo-perfil" onSubmit={(evento) => void criar(evento)}>
          <label>
            Nome
            <input value={nome} onChange={(e) => setNome(e.target.value)} required maxLength={40} />
          </label>
          <label>
            Pasta de dados
            <input value={pasta} onChange={(e) => setPasta(e.target.value)} required />
          </label>
          <button type="submit">Criar perfil</button>{" "}
          <button type="button" onClick={() => setCriando(false)}>
            Cancelar
          </button>
        </form>
      ) : (
        <button type="button" onClick={() => setCriando(true)}>
          Novo perfil
        </button>
      )}
      <p className="dica secundario">
        Use uma pasta da sua nuvem (Google Drive, OneDrive, Dropbox) para ver a carteira em
        qualquer PC.
      </p>
    </section>
  );
}

function mensagemDe(erro: unknown): string {
  if (erro instanceof ErroApi) return erro.mensagem;
  return "Não foi possível falar com o app. Ele ainda está aberto?";
}

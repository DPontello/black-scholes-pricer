import { useEffect, useState } from "react";

import type { EstadoAoVivo, SeguirCadeia } from "../api/aoVivo";
import { definirAtivos, ErroApi, type Perfil } from "../api/cliente";
import { ListaAtivos } from "../componentes/ListaAtivos";
import { TabelaCadeia } from "../componentes/TabelaCadeia";

type Props = {
  aoVivo: EstadoAoVivo;
  seguirCadeia: SeguirCadeia;
  onPerfil: (perfil: Perfil) => void;
};

export function Mercado({ aoVivo, seguirCadeia, onPerfil }: Props) {
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [vencimentos, setVencimentos] = useState<string[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // Só assina a cadeia com a tela aberta: os termos do Tryd vedam "flood".
  useEffect(() => {
    seguirCadeia(selecionado, vencimentos);
  }, [selecionado, vencimentos, seguirCadeia]);
  useEffect(() => () => seguirCadeia(null), [seguirCadeia]);

  function escolherAtivo(ativo: string | null) {
    setSelecionado(ativo);
    setVencimentos(null);
  }

  async function gravarAtivos(ativos: string[]) {
    setErro(null);
    try {
      onPerfil(await definirAtivos(ativos));
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível gravar a lista de ativos.");
    }
  }

  return (
    <section className="pagina-mercado">
      <h1>Mercado</h1>
      {aoVivo.motivoCotacoes !== null && <p className="aviso">{aoVivo.motivoCotacoes}</p>}
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
      <ListaAtivos
        cotacoes={aoVivo.cotacoes}
        selecionado={selecionado}
        onEscolher={escolherAtivo}
        onDefinirAtivos={(ativos) => void gravarAtivos(ativos)}
      />
      <TabelaCadeia
        ativo={selecionado}
        cadeia={aoVivo.cadeia}
        indisponivel={aoVivo.cadeiaIndisponivel}
        onVencimentos={setVencimentos}
      />
    </section>
  );
}

import { useEffect, useState } from "react";

import type { EstadoAoVivo } from "../api/aoVivo";
import { definirAtivos, ErroApi, type Perfil } from "../api/cliente";
import { ListaAtivos } from "../componentes/ListaAtivos";
import { TabelaCadeia } from "../componentes/TabelaCadeia";

type Props = {
  aoVivo: EstadoAoVivo;
  seguirCadeia: (ativo: string | null, vencimentos?: number) => void;
  onPerfil: (perfil: Perfil) => void;
};

/** Mercado ao vivo: a lista de ativos do perfil e a cadeia do ativo escolhido. */
export function Mercado({ aoVivo, seguirCadeia, onPerfil }: Props) {
  const [selecionado, setSelecionado] = useState<string | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  // A cadeia só fica assinada enquanto a tela está aberta (termos do Tryd: nada de "flood").
  useEffect(() => {
    seguirCadeia(selecionado);
  }, [selecionado, seguirCadeia]);
  useEffect(() => () => seguirCadeia(null), [seguirCadeia]);

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
        onEscolher={setSelecionado}
        onDefinirAtivos={(ativos) => void gravarAtivos(ativos)}
      />
      <TabelaCadeia
        ativo={selecionado}
        cadeia={aoVivo.cadeia}
        indisponivel={aoVivo.cadeiaIndisponivel}
      />
    </section>
  );
}

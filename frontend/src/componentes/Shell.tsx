import type { ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

export const AREAS: ReadonlyArray<{ caminho: string; nome: string }> = [
  { caminho: "/mercado", nome: "Mercado" },
  { caminho: "/montador", nome: "Montador" },
  { caminho: "/book", nome: "Book" },
  { caminho: "/carteira", nome: "Carteira" },
  { caminho: "/alertas", nome: "Alertas" },
  { caminho: "/arquivos", nome: "Arquivos B3" },
];

type Props = {
  status: ReactNode;
  perfil?: string | null;
  children: ReactNode;
};

export function Shell({ status, perfil = null, children }: Props) {
  return (
    <div className="shell">
      <header className="barra-superior">
        <span className="nome-app">Painel de Opções</span>
        <div className="espaco-status">{status}</div>
        <Link className="perfil-ativo" to="/perfis" title="Trocar de perfil">
          {perfil === null ? "Escolher perfil" : `Perfil: ${perfil}`}
        </Link>
      </header>
      <nav className="menu-lateral" aria-label="Áreas do app">
        {AREAS.map((area) => (
          <NavLink key={area.caminho} to={area.caminho}>
            {area.nome}
          </NavLink>
        ))}
      </nav>
      <main className="conteudo">{children}</main>
    </div>
  );
}

import { Link, NavLink, Navigate, Route, Routes } from "react-router-dom";

import { Comece } from "../aprender/Comece";
import { Operacoes } from "../aprender/Operacoes";
import { Telas } from "../aprender/Telas";
import { Termos } from "../aprender/Termos";

const SUB_ABAS: ReadonlyArray<{ caminho: string; nome: string }> = [
  { caminho: "/aprender/comece", nome: "Comece aqui" },
  { caminho: "/aprender/operacoes", nome: "Operações" },
  { caminho: "/aprender/termos", nome: "Termos" },
  { caminho: "/aprender/telas", nome: "Telas do app" },
];

type Props = {
  comPerfil: boolean;
};

export function Aprender({ comPerfil }: Props) {
  return (
    <section className="pagina-aprender">
      <header className="cabecalho-aprender">
        <h1>Aprender</h1>
        {!comPerfil && <Link to="/perfis">voltar aos perfis</Link>}
      </header>
      <nav className="sub-abas" aria-label="Seções de Aprender">
        {SUB_ABAS.map((aba) => (
          <NavLink key={aba.caminho} to={aba.caminho}>
            {aba.nome}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to="/aprender/comece" replace />} />
        <Route path="comece" element={<Comece comPerfil={comPerfil} />} />
        <Route path="operacoes" element={<Operacoes comPerfil={comPerfil} />} />
        <Route path="operacoes/:modelo" element={<Operacoes comPerfil={comPerfil} />} />
        <Route path="termos" element={<Termos />} />
        <Route path="telas" element={<Telas />} />
        <Route path="*" element={<Navigate to="/aprender/comece" replace />} />
      </Routes>
    </section>
  );
}

import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { type Perfil, perfilAtivo } from "./api/cliente";
import { Shell } from "./componentes/Shell";
import { ArquivosB3 } from "./paginas/ArquivosB3";
import { EmBreve } from "./paginas/EmBreve";
import { Perfis } from "./paginas/Perfis";

/** Rotas do app. Sem perfil aberto, toda rota leva à escolha de perfil. */
export function App() {
  // undefined: ainda perguntando à API se há perfil aberto; null: nenhum.
  const [perfil, setPerfil] = useState<Perfil | null | undefined>(undefined);
  const navegar = useNavigate();

  useEffect(() => {
    perfilAtivo()
      .then(setPerfil)
      .catch(() => setPerfil(null));
  }, []);

  if (perfil === undefined) {
    return <p className="secundario carregando">Abrindo o Painel de Opções…</p>;
  }

  function aberto(novo: Perfil) {
    setPerfil(novo);
    navegar("/mercado");
  }

  return (
    <Shell status={null} perfil={perfil?.nome ?? null}>
      <Routes>
        <Route path="/perfis" element={<Perfis onAberto={aberto} />} />
        {perfil === null ? (
          <Route path="*" element={<Navigate to="/perfis" replace />} />
        ) : (
          <>
            <Route path="/" element={<Navigate to="/mercado" replace />} />
            <Route path="/mercado" element={<EmBreve titulo="Mercado" semana={1} />} />
            <Route path="/arquivos" element={<ArquivosB3 />} />
            <Route path="/montador" element={<EmBreve titulo="Montador" semana={2} />} />
            <Route path="/book" element={<EmBreve titulo="Book" semana={3} />} />
            <Route path="/carteira" element={<EmBreve titulo="Carteira" semana={2} />} />
            <Route path="/alertas" element={<EmBreve titulo="Alertas" semana={4} />} />
            <Route path="*" element={<Navigate to="/mercado" replace />} />
          </>
        )}
      </Routes>
    </Shell>
  );
}

import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { useAoVivo } from "./api/aoVivo";
import { type Perfil, perfilAtivo } from "./api/cliente";
import { BarraStatus } from "./componentes/BarraStatus";
import { Shell } from "./componentes/Shell";
import { ArquivosB3 } from "./paginas/ArquivosB3";
import { EmBreve } from "./paginas/EmBreve";
import { Mercado } from "./paginas/Mercado";
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

  if (perfil === null) {
    return (
      <Shell status={null} perfil={null}>
        <Routes>
          <Route path="/perfis" element={<Perfis onAberto={aberto} />} />
          <Route path="*" element={<Navigate to="/perfis" replace />} />
        </Routes>
      </Shell>
    );
  }
  return <ComPerfil perfil={perfil} onPerfil={setPerfil} onAberto={aberto} />;
}

type ComPerfilProps = {
  perfil: Perfil;
  onPerfil: (perfil: Perfil) => void;
  onAberto: (perfil: Perfil) => void;
};

/** O app com um perfil aberto: o WebSocket ao vivo só existe aqui dentro. */
function ComPerfil({ perfil, onPerfil, onAberto }: ComPerfilProps) {
  const { seguirCadeia, ...aoVivo } = useAoVivo();
  return (
    <Shell status={<BarraStatus status={aoVivo.status} conectado={aoVivo.conectado} />} perfil={perfil.nome}>
      <Routes>
        <Route path="/perfis" element={<Perfis onAberto={onAberto} />} />
        <Route path="/" element={<Navigate to="/mercado" replace />} />
        <Route
          path="/mercado"
          element={<Mercado aoVivo={aoVivo} seguirCadeia={seguirCadeia} onPerfil={onPerfil} />}
        />
        <Route path="/arquivos" element={<ArquivosB3 />} />
        <Route path="/montador" element={<EmBreve titulo="Montador" semana={2} />} />
        <Route path="/book" element={<EmBreve titulo="Book" semana={3} />} />
        <Route path="/carteira" element={<EmBreve titulo="Carteira" semana={2} />} />
        <Route path="/alertas" element={<EmBreve titulo="Alertas" semana={4} />} />
        <Route path="*" element={<Navigate to="/mercado" replace />} />
      </Routes>
    </Shell>
  );
}

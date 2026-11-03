import { useEffect, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";

import { useAoVivo } from "./api/aoVivo";
import { type Perfil, perfilAtivo } from "./api/cliente";
import { BarraStatus } from "./componentes/BarraStatus";
import { Shell } from "./componentes/Shell";
import { Carteira } from "./paginas/Carteira";
import { Aprender } from "./paginas/Aprender";
import { ArquivosB3 } from "./paginas/ArquivosB3";
import { Book } from "./paginas/Book";
import { EmBreve } from "./paginas/EmBreve";
import { Mercado } from "./paginas/Mercado";
import { Montador } from "./paginas/Montador";
import { Perfis } from "./paginas/Perfis";

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
          <Route path="/aprender/*" element={<Aprender comPerfil={false} />} />
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
        <Route
          path="/montador"
          element={<Montador aoVivo={aoVivo} seguirCadeia={seguirCadeia} />}
        />
        <Route path="/book" element={<Book perfil={perfil} onPerfil={onPerfil} />} />
        <Route path="/carteira" element={<Carteira aoVivo={aoVivo} />} />
        <Route path="/aprender/*" element={<Aprender comPerfil />} />
        <Route path="/alertas" element={<EmBreve titulo="Alertas" semana={4} />} />
        <Route path="*" element={<Navigate to="/mercado" replace />} />
      </Routes>
    </Shell>
  );
}

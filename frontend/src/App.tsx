import { Navigate, Route, Routes } from "react-router-dom";

import { Shell } from "./componentes/Shell";
import { EmBreve } from "./paginas/EmBreve";

/** Rotas do app. Perfis, arquivos e mercado chegam nas Tasks 16 e 17 da semana 1. */
export function App() {
  return (
    <Shell status={null}>
      <Routes>
        <Route path="/" element={<Navigate to="/mercado" replace />} />
        <Route path="/mercado" element={<EmBreve titulo="Mercado" semana={1} />} />
        <Route path="/perfis" element={<EmBreve titulo="Perfis" semana={1} />} />
        <Route path="/arquivos" element={<EmBreve titulo="Arquivos B3" semana={1} />} />
        <Route path="/montador" element={<EmBreve titulo="Montador" semana={2} />} />
        <Route path="/book" element={<EmBreve titulo="Book" semana={3} />} />
        <Route path="/carteira" element={<EmBreve titulo="Carteira" semana={2} />} />
        <Route path="/alertas" element={<EmBreve titulo="Alertas" semana={4} />} />
        <Route path="*" element={<Navigate to="/mercado" replace />} />
      </Routes>
    </Shell>
  );
}

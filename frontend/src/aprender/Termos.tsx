import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";

import { ComTermos, semMarcas } from "../componentes/Termo";
import { TERMOS, type TermoGlossario } from "./glossario";

// A busca ignora acento e maiúsculas: "exercicio" acha "Exercício".
function normalizar(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

const EM_ORDEM = [...TERMOS].sort((a, b) => a.titulo.localeCompare(b.titulo, "pt-BR"));

function acha(termo: TermoGlossario, busca: string): boolean {
  return normalizar(`${termo.titulo} ${semMarcas(termo.texto)}`).includes(busca);
}

export function Termos() {
  const alvo = decodeURIComponent(useLocation().hash.replace(/^#/, ""));
  // A busca vale só para o termo em que foi digitada: um "?" ou um link novo mostra a lista inteira,
  // para o termo pedido estar nela.
  const [busca, setBusca] = useState({ texto: "", alvo });
  const texto = busca.alvo === alvo ? busca.texto : "";
  const procurado = normalizar(texto.trim());
  const visiveis = EM_ORDEM.filter((termo) => acha(termo, procurado));

  useEffect(() => {
    if (alvo !== "") document.getElementById(alvo)?.scrollIntoView?.({ block: "start" });
  }, [alvo]);

  return (
    <div className="corpo-aprender termos">
      <h2>Termos</h2>
      <input
        type="search"
        className="busca-termos"
        aria-label="Buscar termo"
        placeholder="buscar termo (ex.: delta, vol, exercício)"
        value={texto}
        onChange={(e) => setBusca({ texto: e.target.value, alvo })}
      />
      {visiveis.length === 0 ? (
        <p className="secundario">Nenhum termo encontrado.</p>
      ) : (
        <div className="lista-termos">
          {visiveis.map((termo) => (
            <article
              key={termo.id}
              id={termo.id}
              className={termo.id === alvo ? "termo-glossario termo-alvo" : "termo-glossario"}
              aria-labelledby={`${termo.id}-titulo`}
              aria-current={termo.id === alvo ? "true" : undefined}
            >
              <h3 id={`${termo.id}-titulo`}>{termo.titulo}</h3>
              <p>
                <ComTermos texto={termo.texto} />
              </p>
              <p>
                <strong>Exemplo:</strong> <ComTermos texto={termo.exemplo} />
              </p>
              <p className="secundario">
                <strong>No app:</strong> <ComTermos texto={termo.onde} />
              </p>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

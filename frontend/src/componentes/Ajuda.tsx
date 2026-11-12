import { Link } from "react-router-dom";

import { termoPorId } from "../aprender/glossario";
import { enderecoDoTermo } from "./Termo";

// Um "?" pequeno ao lado de um rótulo, que abre o termo na aba Aprender.
export function Ajuda({ id }: { id: string }) {
  const titulo = termoPorId(id)?.titulo ?? id;
  return (
    <Link
      className="ajuda"
      to={enderecoDoTermo(id)}
      aria-label={`O que é ${titulo}?`}
      title={`O que é ${titulo}?`}
      onClick={(e) => e.stopPropagation()}
    >
      ?
    </Link>
  );
}

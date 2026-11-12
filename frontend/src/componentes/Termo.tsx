import { Fragment, type ReactNode } from "react";
import { Link } from "react-router-dom";

// `[palavra](id)`: a palavra do texto vira um link para o termo `id` do glossário.
const MARCA = /\[([^\]]+)\]\(([a-z0-9-]+)\)/g;

export function enderecoDoTermo(id: string): string {
  return `/aprender/termos#${id}`;
}

export function Termo({ id, children }: { id: string; children: ReactNode }) {
  return (
    <Link className="termo" to={enderecoDoTermo(id)}>
      {children}
    </Link>
  );
}

export function ComTermos({ texto }: { texto: string }) {
  const partes: ReactNode[] = [];
  let depois = 0;
  for (const marca of texto.matchAll(MARCA)) {
    const [inteira, palavra, id] = marca;
    const inicio = marca.index;
    partes.push(texto.slice(depois, inicio));
    partes.push(
      <Termo key={inicio} id={id as string}>
        {palavra}
      </Termo>,
    );
    depois = inicio + inteira.length;
  }
  partes.push(texto.slice(depois));
  return (
    <>
      {partes.map((parte, i) => (
        <Fragment key={i}>{parte}</Fragment>
      ))}
    </>
  );
}

// O texto como a pessoa lê, sem as marcas dos links.
export function semMarcas(texto: string): string {
  return texto.replace(MARCA, "$1");
}

export function termosCitados(texto: string): string[] {
  return [...texto.matchAll(MARCA)].map((marca) => marca[2] as string);
}

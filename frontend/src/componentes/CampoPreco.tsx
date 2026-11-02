import { useEffect, useState } from "react";

export function numero(texto: string): number | null {
  const valor = Number(texto.replace(",", "."));
  return texto.trim() === "" || !Number.isFinite(valor) ? null : valor;
}

export function emTexto(valor: number | null): string {
  return valor === null ? "" : String(valor).replace(".", ",");
}

// Guarda o texto digitado: "1," ainda não é número, e o campo não pode engolir a vírgula.
export function CampoPreco({
  rotulo,
  valor,
  placeholder,
  onMudar,
}: {
  rotulo: string;
  valor: number | null;
  placeholder: string;
  onMudar: (v: number | null) => void;
}) {
  const [texto, setTexto] = useState(emTexto(valor));
  useEffect(() => {
    setTexto((atual) => (numero(atual) === valor ? atual : emTexto(valor)));
  }, [valor]);
  return (
    <input
      aria-label={rotulo}
      inputMode="decimal"
      placeholder={placeholder}
      value={texto}
      onChange={(e) => {
        setTexto(e.target.value);
        onMudar(numero(e.target.value));
      }}
    />
  );
}

import { useEffect, useState } from "react";

// Lê o que se digita no Brasil: "1,30", "R$ 1.000,50" e também "1.30". Ponto seguido de
// exatamente três dígitos é milhar ("1.000" é mil), salvo se o primeiro grupo começar em 0
// ("0.500" é meio); com um ou dois dígitos é decimal.
export function numero(texto: string): number | null {
  const limpo = texto.replace(/\s/g, "").replace(/^r\$/i, "");
  const milhar = /^-?[1-9]\d{0,2}(\.\d{3})+(,\d+)?$/.test(limpo);
  if (!milhar && !/^-?\d*,\d+$|^-?\d+$|^-?\d*\.\d+$/.test(limpo)) return null;
  const valor = Number((milhar ? limpo.replace(/\./g, "") : limpo).replace(",", "."));
  return Number.isFinite(valor) ? valor : null;
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

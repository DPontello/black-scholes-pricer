import { useEffect, useState } from "react";

import {
  definirBook,
  ErroApi,
  type NomePreset,
  type Perfil,
  type PresetBook,
  type ValoresBook,
} from "../api/cliente";

const PRESETS: [NomePreset, string][] = [
  ["conservador", "Conservador"],
  ["moderado", "Moderado"],
  ["arrojado", "Arrojado"],
];

type CampoNumero = {
  chave: keyof Omit<ValoresBook, "perda_ilimitada">;
  rotulo: string;
  passo: number;
  // Spread e piso vão em fração para a API e aparecem em % na tela.
  percentual?: boolean;
};

const CAMPOS: CampoNumero[] = [
  { chave: "delta_min", rotulo: "Delta mínimo", passo: 0.01 },
  { chave: "delta_max", rotulo: "Delta máximo", passo: 0.01 },
  { chave: "negocios_min", rotulo: "Negócios mínimos por perna", passo: 1 },
  { chave: "spread_max", rotulo: "Spread máximo (%)", passo: 1, percentual: true },
  { chave: "risco_max", rotulo: "Risco máximo sem ação (R$)", passo: 100 },
  { chave: "vencimentos", rotulo: "Vencimentos varridos", passo: 1 },
  { chave: "piso_protecao", rotulo: "Piso da proteção (% do spot)", passo: 1, percentual: true },
];

type Props = { preset: PresetBook; onSalvo: (perfil: Perfil) => void };

export function EditorPreset({ preset, onSalvo }: Props) {
  const [valores, setValores] = useState<PresetBook>(preset);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => setValores(preset), [preset]);

  async function salvar(nome: NomePreset, novos?: ValoresBook) {
    try {
      onSalvo(await definirBook(nome, novos));
      setErro(null);
    } catch (e) {
      setErro(e instanceof ErroApi ? e.mensagem : "Não foi possível salvar o preset.");
    }
  }

  function mudar(campo: CampoNumero, texto: string) {
    const numero = Number(texto);
    setValores({ ...valores, [campo.chave]: campo.percentual ? numero / 100 : numero });
  }

  const { preset: nome, ...semPreset } = valores;
  return (
    <form
      className="editor-preset"
      aria-label="Preset do book"
      onSubmit={(e) => {
        e.preventDefault();
        void salvar(nome, semPreset);
      }}
    >
      <label>
        Preset
        <select
          value={nome}
          onChange={(e) => void salvar(e.target.value as NomePreset)}
        >
          {PRESETS.map(([chave, rotulo]) => (
            <option key={chave} value={chave}>
              {rotulo}
            </option>
          ))}
        </select>
      </label>
      {CAMPOS.map((campo) => (
        <label key={campo.chave}>
          {campo.rotulo}
          <input
            type="number"
            step={campo.passo}
            value={campo.percentual ? Math.round(valores[campo.chave] * 10000) / 100 : valores[campo.chave]}
            onChange={(e) => mudar(campo, e.target.value)}
          />
        </label>
      ))}
      <label className="marcar">
        <input
          type="checkbox"
          checked={valores.perda_ilimitada}
          onChange={(e) => setValores({ ...valores, perda_ilimitada: e.target.checked })}
        />
        Aceitar perda ilimitada (strangle vendido)
      </label>
      <div className="acoes-preset">
        <button type="submit">Salvar valores</button>
        <button type="button" onClick={() => void salvar(nome)}>
          Voltar ao padrão
        </button>
      </div>
      {erro !== null && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}
    </form>
  );
}

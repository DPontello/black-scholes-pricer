import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import type { Fonte, StatusMercado } from "../api/cliente";
import { BarraStatus } from "./BarraStatus";

function status(fonte: Fonte, velho = false): StatusMercado {
  return {
    fonte,
    cadastro: { data: "2026-10-20", dias_uteis: velho ? 6 : 2, velho },
    cadastro_motivo: null,
    cotahist: null,
  };
}

test.each([
  ["ao_vivo", "Ao vivo (Tryd)", "fonte-ao-vivo"],
  ["atrasado", "Atrasado", "fonte-atrasado"],
  ["fim_de_dia", "Fim de dia (B3)", "fonte-fim-de-dia"],
] as const)("fonte %s vira o rótulo %s", (fonte, texto, classe) => {
  render(<BarraStatus status={status(fonte)} />);
  const selo = screen.getByText(new RegExp(texto.replace(/[()]/g, "\\$&")));
  expect(selo.className).toContain(classe);
});

test("cadastro velho aparece na barra", () => {
  render(<BarraStatus status={status("ao_vivo", true)} />);
  expect(screen.getByText(/Cadastro com 6 dias úteis/)).toBeTruthy();
});

test("sem conexão com o app não finge fonte nenhuma", () => {
  render(<BarraStatus status={status("ao_vivo")} conectado={false} />);
  expect(screen.getByText("Conectando ao app…")).toBeTruthy();
  expect(screen.queryByText(/Ao vivo/)).toBeNull();
});

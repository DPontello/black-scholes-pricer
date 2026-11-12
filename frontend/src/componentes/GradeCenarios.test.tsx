import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { analiseCoberta } from "../testes/analise";
import { GradeCenarios } from "./GradeCenarios";

test("grade com os choques nas bordas e — onde a vol chocada zera", () => {
  render(<GradeCenarios grade={analiseCoberta().hoje!.grade} />);
  expect(screen.getByText("-10 pts")).toBeTruthy();
  expect(screen.getByText("+10 pts")).toBeTruthy();
  expect(screen.getByText("—")).toBeTruthy();
  expect(screen.getByText("-12,00").className).toContain("baixa");
});

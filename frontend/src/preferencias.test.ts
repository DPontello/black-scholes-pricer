import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { usePreferencia } from "./preferencias";

test("sem nada guardado começa falso, e o que se grava volta ao montar de novo", () => {
  const primeira = renderHook(() => usePreferencia("x"));
  expect(primeira.result.current[0]).toBe(false);
  act(() => primeira.result.current[1](true));
  expect(primeira.result.current[0]).toBe(true);
  primeira.unmount();
  expect(renderHook(() => usePreferencia("x")).result.current[0]).toBe(true);
});

test("com o localStorage bloqueado, começa falso e muda só na memória, sem erro", () => {
  const erro = () => {
    throw new DOMException("bloqueado", "SecurityError");
  };
  const ler = vi.spyOn(Storage.prototype, "getItem").mockImplementation(erro);
  const gravar = vi.spyOn(Storage.prototype, "setItem").mockImplementation(erro);
  const { result } = renderHook(() => usePreferencia("x"));
  expect(result.current[0]).toBe(false);
  act(() => result.current[1](true));
  expect(result.current[0]).toBe(true);
  ler.mockRestore();
  gravar.mockRestore();
});

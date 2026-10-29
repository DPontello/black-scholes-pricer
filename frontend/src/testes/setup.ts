// Sem os globais do Vitest, o Testing Library não desmonta sozinho entre um teste e outro.
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

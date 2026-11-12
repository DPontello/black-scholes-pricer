import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Em desenvolvimento (`npm run dev`), a API e o WebSocket vão para o app Python na 8765.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8765", ws: true },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/testes/setup.ts"],
  },
});

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": env.VITE_API_PROXY_TARGET ?? "http://127.0.0.1:8000"
      }
    },
    test: {
      environment: "jsdom",
      exclude: ["**/node_modules/**", "**/dist/**", "**/._*"],
      globals: true,
      setupFiles: "./src/test/setup.ts"
    }
  };
});

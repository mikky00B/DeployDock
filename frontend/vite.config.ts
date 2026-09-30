/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    // Dev proxy: the dashboard calls the API same-origin so the browser never
    // has to reach the backend directly (no CORS preflights, no hard failure
    // while `uvicorn --reload` restarts). Production nginx/Docker builds keep
    // using VITE_API_BASE_URL instead.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      "/health": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});

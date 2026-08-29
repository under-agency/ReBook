import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Прокси /api → бэкенд: cookie работают как same-origin, CORS не нужен
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});

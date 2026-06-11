import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During local dev, proxy API calls to the FastAPI backend so the frontend can
// use same-origin relative URLs. In production the API base is set via
// VITE_API_BASE at build time.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});

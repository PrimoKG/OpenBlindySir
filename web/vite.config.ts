import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // HTTP + WebSocket (/api/ws) to the local DEV_MODE=1 server.
      "/api": { target: "http://127.0.0.1:8000", ws: true, changeOrigin: false },
      "/healthz": { target: "http://127.0.0.1:8000" },
    },
  },
  // No inlined data: URLs, which the CSP (spec §12) would block.
  build: { outDir: "dist", sourcemap: false, assetsInlineLimit: 0 },
});

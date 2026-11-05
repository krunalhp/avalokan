import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// The UI always talks to the API on the same origin (/v1, /docs).
// During `npm --prefix web run dev`, proxy those paths to the backend.
// Override the target with AVALOKAN_API (default http://127.0.0.1:8000).
const api = process.env.AVALOKAN_API ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [preact()],
  server: {
    proxy: {
      "/v1": { target: api, changeOrigin: false },
      "/docs": { target: api, changeOrigin: false },
      "/openapi.json": { target: api, changeOrigin: false },
      "/health": { target: api, changeOrigin: false },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = fileURLToPath(new URL(".", import.meta.url));
const djangoDevOrigin =
  globalThis.process?.env?.DJANGO_DEV_ORIGIN || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  base: "/static/frontend/",
  publicDir: false,
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
      "/backend": {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
      "/auth": {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
      "/admin-qweasd123": {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: resolve(rootDir, "../projects/static/frontend"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        entryFileNames: "board.js",
        chunkFileNames: "chunks/[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name?.endsWith(".css")) {
            return "board.css";
          }
          return "assets/[name][extname]";
        },
      },
    },
  },
});

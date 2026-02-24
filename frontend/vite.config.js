import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const djangoDevOrigin =
  globalThis.process?.env?.DJANGO_DEV_ORIGIN || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
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
});

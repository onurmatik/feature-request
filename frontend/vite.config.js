import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const djangoDevOrigin =
  globalThis.process?.env?.DJANGO_DEV_ORIGIN || "http://127.0.0.1:8000";
const adminPathSegment =
  (globalThis.process?.env?.ADMIN_URL || "/admin/")
    .trim()
    .replace(/^\/+|\/+$/g, "") || "admin";
const adminUrl = `/${adminPathSegment}`;
const allowedHosts =
  (globalThis.process?.env?.VITE_ALLOWED_HOSTS ||
    "featurerequest.io,www.featurerequest.io,localhost,127.0.0.1")
    .split(",")
    .map((host) => host.trim())
    .filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    allowedHosts,
    proxy: {
      "/api": {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
      "/auth": {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
      [adminUrl]: {
        target: djangoDevOrigin,
        changeOrigin: true,
        secure: false,
      },
    },
  },
  preview: {
    allowedHosts,
  },
});

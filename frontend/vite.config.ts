import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, "");

  // A production bundle built without VITE_API_URL silently falls back to
  // http://localhost:8000 (src/lib/axios.ts) — every API call then targets the
  // visitor's own machine. Fail the build instead of shipping that.
  if (mode === "production" && !env.VITE_API_URL) {
    throw new Error(
      "VITE_API_URL must be set for production builds " +
        "(e.g. VITE_API_URL=https://yourdomain.com in .env.production or the environment)."
    );
  }

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      host: "0.0.0.0",
      port: 5173,
      proxy: {
        // Server-side proxy target must use the Docker network service name,
        // not VITE_API_URL (which is a browser-facing, host-mapped URL).
        "/api": {
          target: "http://web:8000",
          changeOrigin: true,
        },
      },
    },
  };
});

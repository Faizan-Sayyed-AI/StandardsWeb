import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vite";

export default defineConfig({
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
});

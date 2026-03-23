import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const devProxyTarget = env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8012";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: devProxyTarget,
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});

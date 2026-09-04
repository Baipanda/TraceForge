import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5177,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18081",
        changeOrigin: true,
      },
    },
  },
});

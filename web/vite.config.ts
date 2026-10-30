import { defineConfig, Plugin } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

function landingPagePlugin(): Plugin {
  return {
    name: "landing-page-router",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const rawUrl = req.url || "/";
        const [pathname, search] = rawUrl.split("?");
        // If visiting root "/" with no search parameters, or "/landing", serve landing.html
        if ((pathname === "/" && !search) || pathname === "/landing") {
          req.url = "/landing.html" + (search ? "?" + search : "");
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), landingPagePlugin()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, "index.html"),
        landing: path.resolve(__dirname, "landing.html"),
      },
    },
  },
});

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// No dev proxy. The API is called at its real origin and the backend already
// allows http://localhost:5173 through CORS, so development and production
// exercise the same code path — a proxy that rewrites paths in development
// only is a class of bug that surfaces on the first real deployment.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    strictPort: true,
  },
  build: {
    // Roughly 170 kB gzipped, most of it recharts. This application is served
    // from localhost to one person, so splitting it into lazy chunks would
    // buy nothing measurable and cost a Suspense boundary on every view. The
    // limit is raised deliberately rather than the warning ignored — if this
    // is ever served over a network, revisit it.
    chunkSizeWarningLimit: 700,
  },
});

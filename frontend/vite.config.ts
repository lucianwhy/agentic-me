import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Backend (uvicorn) that the dev server proxies API calls to.
const BACKEND = process.env.VITE_BACKEND_URL ?? 'http://127.0.0.1:8000'

// Every backend path the React app (or a user clicking a link) needs during `npm run dev`.
const proxied = ['/chat', '/summary', '/job-match', '/models', '/auth', '/api', '/static', '/data', '/health', '/admin']

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(import.meta.dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(proxied.map((p) => [p, { target: BACKEND, changeOrigin: false }])),
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // Single-page app: one ~160 kB gzip bundle (React + Radix + react-markdown) is fine.
    chunkSizeWarningLimit: 700,
  },
})

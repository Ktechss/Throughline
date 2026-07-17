import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// /api proxies to uvicorn so the app is same-origin in dev — no CORS juggling
// and no absolute URLs in the client.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true } },
  },
})

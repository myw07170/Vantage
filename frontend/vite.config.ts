import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('framer-motion')) return 'motion'
          if (/node_modules[/\\\\](react|react-dom|react-router)/.test(id)) return 'react'
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: process.env.VANTAGE_API_PROXY_TARGET || 'http://127.0.0.1:8010', changeOrigin: true } },
  },
})

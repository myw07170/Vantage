import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    // The echarts chunk is ~1.1MB and always will be. It is deliberately
    // isolated and lazily loaded, so warning about it on every build only
    // teaches people to ignore build warnings. The limit is still low enough
    // to catch the entry chunk regaining weight.
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // Charting is the bulk of the bundle and is only reached from the
        // report, dashboard and graph routes. Splitting it out means a visitor
        // who never opens one never downloads it, and the vendor chunks stay
        // cached across deploys that only touch app code.
        //
        // Order matters: `echarts-for-react` would otherwise fall into the
        // react bucket and drag ECharts back into the entry chunk with it.
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('echarts')) return 'echarts'
          if (/node_modules[/\\]d3(-|[/\\])/.test(id)) return 'd3'
          if (id.includes('framer-motion')) return 'motion'
          if (/node_modules[/\\](react|react-dom|react-router)/.test(id))
            return 'react'
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      // The backend runs on 8010; see docs/DEPLOYMENT.md.
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})

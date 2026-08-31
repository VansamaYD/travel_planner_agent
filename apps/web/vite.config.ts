import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: '旅行规划助手',
        short_name: '旅行助手',
        description: '自托管智能旅游规划助手',
        lang: 'zh-CN',
        start_url: '/',
        display: 'standalone',
        background_color: '#f3f5ef',
        theme_color: '#12372a',
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//, /^\/health\//],
      },
    }),
  ],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'node',
  },
})

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'node:path'

const devApiUrl = process.env.REPORT_DEV_API_URL || 'http://127.0.0.1:8010'

export default defineConfig({
  plugins: [vue()],
  build: {
    rollupOptions: {
      input: {
        report: resolve(__dirname, 'index.html'),
        admin: resolve(__dirname, 'admin/index.html'),
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': devApiUrl,
      '/health': devApiUrl,
    },
  },
})

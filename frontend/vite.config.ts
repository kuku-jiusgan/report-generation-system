import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

const devApiUrl = process.env.REPORT_DEV_API_URL || 'http://127.0.0.1:8010'

export default defineConfig({
  plugins: [vue()],
  build: {
    // Element Plus 全量样式与组件约 915 KB，独立 vendor 后可长期缓存。
    // 阈值略高于该稳定第三方包，避免将其误报为业务代码膨胀。
    chunkSizeWarningLimit: 1024,
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue'],
          'element-vendor': ['element-plus', '@element-plus/icons-vue'],
          'http-vendor': ['axios'],
        },
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

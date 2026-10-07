import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// dev 模式：/api 代理到本机 FastAPI，避免跨域。
// 端口钉死 5173——main.py 的 DEV_URL 与此约定，改这里必须同步改那边。
export default defineConfig({
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

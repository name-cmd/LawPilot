import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'

// 开发时资源用根路径 /（dev server 自己提供页面）
// 生产时后端把前端挂在 /ui 下，资源必须带 /ui/ 前缀，否则构建产物 404
// 这个路径由 .env.development / .env.production 中的 VITE_BASE 控制
export default defineConfig(({ mode }) => {
  const base = loadEnv(mode, process.cwd()).VITE_BASE || '/'
  return {
    plugins: [vue(), tailwindcss()],
    resolve: {
      // @ 别名 → src 目录，import 时写 '@/stores/xxx' 即可
      alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
    },
    base,
    server: {
      port: 5173,
      // 开发时把 /api、/ws、/figure 转发到 FastAPI 后端（6006），前端始终同源调用
      proxy: {
        '/api': { target: 'http://localhost:6006', changeOrigin: true },
        '/ws': { target: 'ws://localhost:6006', ws: true },
        '/figure': { target: 'http://localhost:6006', changeOrigin: true },
      },
    },
  }
})

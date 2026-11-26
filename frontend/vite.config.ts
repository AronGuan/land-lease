import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 开发期直连后端，避免 CORS 与硬编码 baseURL
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
});

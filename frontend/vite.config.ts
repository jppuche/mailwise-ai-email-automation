import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// https://vite.dev/config/
const isDocker = process.env.DOCKER === '1'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: isDocker ? '0.0.0.0' : 'localhost',
    port: 5173,
    proxy: {
      '/api': {
        target: isDocker ? 'http://api:8000' : 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by the STEM_LearnLK FastAPI app under /adaptive-quiz (see backend/main.py).
// https://vite.dev/config/
export default defineConfig({
  base: '/adaptive-quiz/',
  plugins: [react()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  // `npm run dev`: forward API + emotion calls to the FastAPI app on :8000
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})

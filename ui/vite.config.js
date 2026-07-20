import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/ws' : { target: 'ws://localhost:8000', ws: true },
    },
  },
  build: {
    outDir: '../server/static',  // 빌드 결과를 FastAPI가 읽는 폴더로 직접 출력
    emptyOutDir: true,
  },
})
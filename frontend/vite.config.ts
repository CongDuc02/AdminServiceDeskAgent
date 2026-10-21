// Vite + Vitest dùng chung một cấu hình (ADR-042). Build ra `dist/` — Dockerfile chép vào /app/static (06-structure.md mục 10.4).
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  // Chạy `npm run dev` cạnh `api` ở cổng 8000: mọi /api đi qua proxy, nên cookie bo19_session cùng origin như khi deploy (ADR-013).
  server: { proxy: { '/api': 'http://localhost:8000' } },
  build: { outDir: 'dist', sourcemap: false },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    restoreMocks: true,
    testTimeout: 20_000, // ESLint khởi động chậm ở lần gọi đầu của src/test/eslint-boundaries.test.ts
    include: ['src/**/*.test.{ts,tsx}'],
  },
})

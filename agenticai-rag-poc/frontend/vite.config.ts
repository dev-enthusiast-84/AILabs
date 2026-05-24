import { defineConfig, createLogger } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Suppress the noisy ECONNREFUSED proxy error log that fires when the backend
// is not running during E2E tests. The tests don't need the backend — they
// inject auth via sessionStorage and assert on UI structure only.
const logger = createLogger()
const originalLoggerError = logger.error.bind(logger)
logger.error = (msg, options) => {
  if (msg.includes('http proxy error')) return
  originalLoggerError(msg, options)
}

export default defineConfig({
  customLogger: logger,
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  // Expose Vercel's build-time VERCEL=1 flag so the frontend can apply the
  // 4 MB upload cap that matches the serverless function body size limit.
  define: {
    __IS_VERCEL__: JSON.stringify(process.env.VERCEL === '1'),
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        configure: (proxy) => {
          // When the backend is not running (e.g., during E2E tests that rely on
          // sessionStorage auth injection), Vite emits noisy ECONNREFUSED logs.
          // Intercept those errors: send a clean 503 JSON response so the browser
          // receives a real HTTP response and the axios 401 interceptor is NOT
          // triggered (503 ≠ 401, so auth state is not cleared).
          proxy.on('error', (_err, _req, res) => {
            if ('writeHead' in res && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'application/json' })
              res.end(JSON.stringify({ detail: 'Backend not available' }))
            }
          })
        },
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Split vendor and UI icon chunks for better browser caching.
        // Hashed filenames mean clients re-fetch only what changed.
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          ui: ['@heroicons/react/24/outline'],
          state: ['zustand', 'axios'],
        },
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
    exclude: ['tests/e2e/**', 'node_modules/**'],
    // vmThreads shares the process with worker threads — faster than the default
    // forks pool for jsdom tests because there's no per-file process spawn cost.
    pool: 'vmThreads',
    poolOptions: {
      vmThreads: {
        // Cap at 8 to avoid memory pressure; CI runners typically have 4 vCPUs.
        maxThreads: 8,
        minThreads: 2,
      },
    },
    // Only flag tests that genuinely block the suite (> 2 s), not fast ones.
    slowTestThreshold: 2000,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      reportsDirectory: '../test-reports/frontend-coverage',
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/main.tsx',
        'src/vite-env.d.ts',
        'src/types/**',
        'src/**/*.d.ts',
        'tests/**',
        '**/*.config.{ts,js}',
        '**/coverage/**',
        '**/dist/**',
        '**/playwright-report/**',
        '**/test-results/**',
      ],
      thresholds: {
        statements: 50,
        branches: 50,
        functions: 45,
        lines: 50,
      },
    },
  },
})

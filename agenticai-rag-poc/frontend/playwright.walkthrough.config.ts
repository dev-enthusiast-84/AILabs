import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.WALKTHROUGH_BASE_URL ?? 'http://localhost:5173'

// Inherit env label from record-walkthrough.sh; fall back to URL-based detection.
function resolveEnv(): 'local' | 'remote' {
  const explicit = process.env.WALKTHROUGH_ENV
  if (explicit === 'local' || explicit === 'remote') return explicit
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/.test(baseURL)
    ? 'local'
    : 'remote'
}

const walkthroughEnv = resolveEnv()
const isLocal = walkthroughEnv === 'local'

export default defineConfig({
  testDir: './tests/walkthrough',
  timeout: 480_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: `../artifacts/walkthrough/${walkthroughEnv}/report`, open: 'never' }],
  ],
  outputDir: `../artifacts/walkthrough/${walkthroughEnv}/results`,
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    viewport: { width: 1440, height: 800 },
    launchOptions: { slowMo: Number(process.env.WALKTHROUGH_SLOW_MO_MS ?? 250) },
    screenshot: 'on',
    trace: 'retain-on-failure',
    video: {
      mode: 'on',
      size: { width: 1440, height: 800 },
    },
  },
  // Auto-start the Vite dev server for local recordings so the walkthrough
  // works without requiring the user to start the server separately.
  // Remote URLs (Vercel) have no server to start — skip the webServer block.
  ...(isLocal && {
    webServer: {
      command: 'npm run dev',
      url: baseURL,
      reuseExistingServer: true,
      timeout: 60_000,
    },
  }),
})

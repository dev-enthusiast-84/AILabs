import { defineConfig, devices } from '@playwright/test'

const baseURL = process.env.WALKTHROUGH_BASE_URL ?? 'http://localhost:5173'

export default defineConfig({
  testDir: './tests/walkthrough',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: '../artifacts/walkthrough/report', open: 'never' }],
  ],
  outputDir: '../artifacts/walkthrough/results',
  use: {
    ...devices['Desktop Chrome'],
    baseURL,
    viewport: { width: 1440, height: 960 },
    launchOptions: { slowMo: Number(process.env.WALKTHROUGH_SLOW_MO_MS ?? 250) },
    screenshot: 'on',
    trace: 'retain-on-failure',
    video: {
      mode: 'on',
      size: { width: 1440, height: 960 },
    },
  },
})

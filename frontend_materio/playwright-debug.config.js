import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './src/__tests__',
  testMatch: '**/e2e-visual-bandeja.spec.js',
  timeout: 120 * 1000,
  expect: { timeout: 15 * 1000 },
  retries: 0,
  use: {
    baseURL: 'http://localhost:5177',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5177',
    reuseExistingServer: true,
  },
  projects: [
    {
      name: 'chromium',
      use: {
        ...devices['Desktop Chrome'],
        storageState: '.auth.json',
      },
    },
  ],

  globalSetup: './playwright-auth-debug.js',
})

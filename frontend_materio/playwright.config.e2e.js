import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './src/__tests__',
  testMatch: '**/e2e-visual-bandeja.spec.js',
  timeout: 90 * 1000,
  expect: { timeout: 10 * 1000 },
  retries: 0,
  use: {
    baseURL: 'http://localhost:5177',
    trace: 'on-first-retry',
    // Reuse storageState for authenticated sessions
    storageState: './auth.json',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5177',
    reuseExistingServer: true,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Global setup for authentication
  globalSetup: './playwright-global-setup.js',
})

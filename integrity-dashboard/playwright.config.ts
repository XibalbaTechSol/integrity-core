import { defineConfig, devices } from '@playwright/test';

// Runs against a real dev server hitting the real oracle/bcc_middleware/chain stack —
// no mocked fetch/route interception anywhere in this suite (matches integrity-dashboard's
// e2e convention). Requires `make up` (or equivalent) running locally so ORACLE_URL/
// BCC_MIDDLEWARE_URL in .env resolve to something real; specs degrade to real empty
// states rather than asserting fake data when the stack has no seeded agents.
export default defineConfig({
  testDir: './e2e',
  timeout: 60000,
  expect: {
    timeout: 10000,
  },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:5189',
    trace: 'on-first-retry',
    headless: true,
  },
  webServer: {
    command: 'npm run dev -- --port 5189',
    url: 'http://127.0.0.1:5189',
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: 'desktop',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
});

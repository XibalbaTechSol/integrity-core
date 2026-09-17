import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.DASHBOARD_BASE_URL || 'http://127.0.0.1:5189';
const allBrowsers = process.env.VALIDATE_ALL_BROWSERS === 'true';
const authState = process.env.E2E_AUTH_STORAGE_STATE;
const restrictedState = process.env.E2E_RESTRICTED_STORAGE_STATE;

export default defineConfig({
  testDir: './e2e',
  testMatch: /validation\.spec\.ts$/,
  outputDir: 'test-results/artifacts',
  timeout: 60_000,
  expect: { timeout: 12_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [
    ['list'],
    ['html', { outputFolder: 'test-results/reports/html', open: 'never' }],
    ['json', { outputFile: 'test-results/reports/playwright.json' }],
    ['junit', { outputFile: 'test-results/reports/junit.xml' }],
  ],
  use: {
    baseURL,
    headless: true,
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'only-on-failure',
    serviceWorkers: 'block',
  },
  webServer: {
    command: 'VITE_ALLOW_UNSCOPED_AGENT_DIRECTORY=true VITE_GRAPH_MEMORY_URL=http://127.0.0.1:8420 npm run dev -- --host 127.0.0.1 --port 5189',
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    { name: 'desktop-chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'tablet-chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 834, height: 1194 } } },
    { name: 'mobile-chromium', use: { ...devices['Pixel 5'], viewport: { width: 390, height: 844 } } },
    ...(authState ? [{ name: 'authorized-agent', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, storageState: authState } }] : []),
    ...(restrictedState ? [{ name: 'restricted-agent', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, storageState: restrictedState } }] : []),
    ...(allBrowsers ? [
      { name: 'desktop-firefox', use: { ...devices['Desktop Firefox'], viewport: { width: 1440, height: 900 } } },
      { name: 'desktop-webkit', use: { ...devices['Desktop Safari'], viewport: { width: 1440, height: 900 } } },
    ] : []),
  ],
});

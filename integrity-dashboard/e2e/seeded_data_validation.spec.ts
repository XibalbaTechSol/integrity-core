import { test, expect, Page } from '@playwright/test';
import { navigateTab, ensureVisible } from './test-utils';

test.describe('Seeded Data Validation', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
    page.on('pageerror', err => console.log('BROWSER ERROR:', err.message));
    page.on('requestfailed', request => console.log('REQUEST FAILED:', request.url(), request.failure()?.errorText));

    await page.goto('/integrity/#/integrity');
    // Wait for the app shell to load
    await page.waitForSelector('.app-shell', { timeout: 30000 });
  });

  test('Identity page displays seeded agents', async ({ page }) => {
    await navigateTab(page, 'identity');
    await page.waitForTimeout(2000); 

    // Specifically check for seeded agents using ensureVisible to handle collapsed sidebars
    const sidebar = page.locator('.sidebar-content');
    await ensureVisible(page, sidebar.locator('text=Institutional_Ironclad'));
    await ensureVisible(page, sidebar.locator('text=Cyber_Sentinel'));
  });

  test('Ledger page displays transactions', async ({ page }) => {
    await navigateTab(page, 'ledger');
    await page.waitForTimeout(3000);

    // Ledger should have log entries with links to Basescan
    const links = page.locator('a[href*="basescan.org/tx/"]');
    const count = await links.count();
    expect(count).toBeGreaterThan(0); 
  });

  test('Telemetry page displays performance metrics', async ({ page }) => {
    await navigateTab(page, 'telemetry');
    await page.waitForTimeout(3000);

    // Check for chart elements (Radar chart)
    await expect(page.locator('.recharts-wrapper').first()).toBeVisible({ timeout: 15000 });
  });

  test('Stability Hub displays benchmarks', async ({ page }) => {
    await navigateTab(page, 'stability');
    await page.waitForTimeout(3000);

    // We seeded stability benchmarks: GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro
    await expect(page.locator('text=GPT-4o')).toBeVisible();
    await expect(page.locator('text=Claude 3.5 Sonnet')).toBeVisible();
  });

  test('Wallet page displays balances', async ({ page }) => {
    await navigateTab(page, 'wallet');
    await page.waitForTimeout(5000);
    
    const content = await page.content();
    console.log("WALLET PAGE CONTENT SNAPSHOT (partial):", content.substring(0, 1000));
    console.log("PAGE HAS 'ITK Balance':", content.includes('ITK Balance'));

    // Wallet should be visible - look for the ITK label
    await expect(page.getByText(/ITK Balance/i).first()).toBeVisible({ timeout: 20000 });
  });
});

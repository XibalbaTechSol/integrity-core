import { test, expect } from '@playwright/test';
import { collectPageErrors } from './test-utils';

// /prediction-markets renders ActuarialHub mode="markets" directly (src/App.tsx) — the
// same component FinancialsPage mounts under its Markets tab. No route/fetch mocking:
// markets come from a real oracle.listMarkets() call, and every write (deploy market,
// enter position, resolve, claim) routes through a real SovereignAgent.execute call that
// needs an injected wallet — absent in headless Chromium, so "Connect Wallet" is the
// correct, honest state to assert for the write paths.

test.describe('/prediction-markets (ActuarialHub markets mode)', () => {
  test('loads with no uncaught JS errors', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/prediction-markets');
    await page.waitForLoadState('networkidle');
    expect(errors, `Uncaught errors: ${errors.map(e => e.message).join('; ')}`).toEqual([]);
  });

  test('Deploy a Market panel: form fields render with real defaults, Connect Wallet gates deployment', async ({ page }) => {
    await page.goto('/prediction-markets');
    await expect(page.getByText('Deploy a Market')).toBeVisible();
    await expect(page.getByLabel('Question')).toBeVisible();
    await expect(page.getByLabel('Outcomes')).toHaveValue('2');
    await expect(page.getByLabel('Min AIS to Enter')).toHaveValue('500');
    await expect(page.getByLabel('Resolve Deadline (hours from now)')).toHaveValue('72');
    // No wallet extension in headless Chromium — real gated state, not a fabricated
    // "Deploy Market" enabled button.
    await expect(page.getByRole('button', { name: 'Connect Wallet' })).toBeVisible();
  });

  test('Protocol Logs panel starts with the real "awaiting activity" empty state', async ({ page }) => {
    await page.goto('/prediction-markets');
    await expect(page.getByText('Protocol Logs')).toBeVisible();
    await expect(page.getByText('Awaiting market activity…')).toBeVisible();
  });

  test('Live Markets table shows real deployed markets or the honest empty state', async ({ page }) => {
    await page.goto('/prediction-markets');
    await page.waitForLoadState('networkidle');
    await expect(page.getByText('Live Markets')).toBeVisible();
    const noMarkets = page.getByText('No markets deployed yet.');
    const marketRows = page.locator('table tbody tr');
    await expect(noMarkets.or(marketRows.first())).toBeVisible();
  });

  test('Live Markets deadline column renders a real date, never "Invalid Date"', async ({ page }) => {
    // Regression test for a real bug: resolve_deadline is a real ISO 8601 string from
    // the oracle (confirmed live: "2026-07-09T19:22:04Z"), but ActuarialHub parsed it
    // with `Number(m.resolve_deadline) * 1000` — NaN for an ISO string — so every
    // deployed market's Deadline column rendered the literal text "Invalid Date", and
    // the derived `past` flag was permanently false (silently breaking the
    // creator-resolve button gate for markets actually past deadline).
    await page.goto('/prediction-markets');
    await page.waitForLoadState('networkidle');
    const rows = page.locator('table tbody tr');
    const count = await rows.count();
    test.skip(count === 0, 'no markets deployed on this stack to check a deadline cell on');
    await expect(page.getByText('Invalid Date')).toHaveCount(0);
  });

  test('refresh button on Live Markets re-fetches without crashing', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/prediction-markets');
    await page.waitForLoadState('networkidle');
    await page.locator('.btn-icon').first().click();
    await page.waitForTimeout(500);
    expect(errors).toEqual([]);
  });

  test('screenshot confirms final rendered state', async ({ page }) => {
    const errors = collectPageErrors(page);
    await page.goto('/prediction-markets');
    await page.waitForLoadState('networkidle');
    expect(errors).toEqual([]);
    await page.screenshot({ path: 'e2e/screenshots/prediction-markets.png', fullPage: true });
  });
});
